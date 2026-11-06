"""Full-cap native layout must preserve reader intent across every batch."""

from itertools import pairwise
from time import monotonic

import pytest
import shiboken6
from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QPointF,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionSlider,
    QStyleOptionViewItem,
)
from pytestqt.qtbot import QtBot

from ctstudio.core.build.events import LogLine
from ctstudio.gui.build_log_model import BuildLogModel
from ctstudio.gui.views.build_log import BuildLogPanel

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


class MeasuringDelegate(QStyledItemDelegate):
    def __init__(self, panel: BuildLogPanel) -> None:
        super().__init__(panel.view)
        self.seen: set[int] = set()

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        self.seen.add(index.row())
        return super().sizeHint(option, index)


def drain(panel: BuildLogPanel, delegate: MeasuringDelegate) -> None:
    deadline = monotonic() + 12
    count = panel.model.rowCount()
    complete = False
    while monotonic() < deadline:
        QApplication.processEvents()
        bar = panel.view.verticalScrollBar()
        last = panel.view.visualRect(panel.model.index(count - 1))
        complete = (
            len(delegate.seen) >= count
            and not any(t.isActive() for t in panel.findChildren(QTimer) if t.isSingleShot())
            and last.isValid()
            and last.bottom() + bar.value() + 1 - panel.view.viewport().height() == bar.maximum()
        )
        if complete:
            break
    assert complete, f"native layout incomplete: measured {len(delegate.seen)}/{count}"


def filled(qtbot: QtBot, cap: int = 20_000) -> tuple[BuildLogPanel, MeasuringDelegate]:
    panel = BuildLogPanel(model=BuildLogModel(max_rows=cap))
    qtbot.addWidget(panel)
    panel.resize(480, 260)
    delegate = MeasuringDelegate(panel)
    panel.view.setItemDelegate(delegate)
    panel.show()
    panel.toggle.click()
    panel.append(LogLine("n", "\n".join(f"row {i:05d}" for i in range(20_000))))
    drain(panel, delegate)
    bar = panel.view.verticalScrollBar()
    assert bar.value() == bar.maximum(), "tail following stopped before native layout completed"
    return panel, delegate


def top(panel: BuildLogPanel) -> tuple[object, int]:
    index = panel.view.indexAt(QPoint(2, 2))
    return index.data(), panel.view.visualRect(index).top()


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("added", [0, 1, 5000, 11000])
def test_full_cap_reader_anchor(qtbot: QtBot, hidden: bool, added: int) -> None:
    panel, delegate = filled(qtbot, 20_000 + 1000 * (added == 0))
    panel.view.setCurrentIndex(panel.model.index(10005))
    panel.view.scrollTo(panel.model.index(10000), QAbstractItemView.ScrollHint.PositionAtTop)
    bar = panel.view.verticalScrollBar()
    bar.setValue(bar.value() + 3)
    assert top(panel) == ("[n] row 10000", -3)
    if hidden:
        panel.toggle.click()
    delegate.seen.clear()
    panel.append(LogLine("n", "\n".join(f"new {i}" for i in range(max(added, 1)))))
    if added == 5000:
        QApplication.processEvents()
        panel.append(LogLine("n", "another burst during native layout"))
    if hidden:
        QApplication.processEvents()
        panel.toggle.click()
    drain(panel, delegate)
    expected = (f"[n] row {max(10000, added):05d}", -3 * (added <= 10000))
    assert top(panel) == expected, "native batching moved the history reader"
    assert (panel.view.currentIndex().data() == "[n] row 10005") == (added <= 10000)
    assert bar.value() < bar.maximum(), "native clamping resumed tail following"


def interrupt(panel: BuildLogPanel, method: str) -> None:
    view = panel.view
    bar = view.verticalScrollBar()
    if method == "bar":
        bar.setValue(0)
    elif method == "scrollTo":
        view.scrollTo(panel.model.index(20), QAbstractItemView.ScrollHint.PositionAtTop)
    elif method == "key":
        QTest.keyClick(view, Qt.Key.Key_Home)
    elif method == "wheel":
        pos = view.viewport().rect().center()
        event = QWheelEvent(
            QPointF(pos),
            QPointF(view.viewport().mapToGlobal(pos)),
            QPoint(),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(view.viewport(), event)
    else:
        option = QStyleOptionSlider()
        bar.initStyleOption(option)
        handle = bar.style().subControlRect(
            QStyle.ComplexControl.CC_ScrollBar,
            option,
            QStyle.SubControl.SC_ScrollBarSlider,
            bar,
        )
        QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=handle.center())
        QTest.mouseMove(bar, QPoint(handle.center().x(), bar.height() // 2))
        QTest.mouseRelease(
            bar, Qt.MouseButton.LeftButton, pos=QPoint(handle.center().x(), bar.height() // 2)
        )


@pytest.mark.parametrize("method", ["bar", "scrollTo", "key", "wheel", "drag"])
def test_reader_interrupts_late_batches(qtbot: QtBot, method: str) -> None:
    panel, delegate = filled(qtbot)
    delegate.seen.clear()
    panel.append(LogLine("n", "\n".join(f"late {i}" for i in range(3000))))
    QApplication.processEvents()
    assert 0 < len(delegate.seen) < panel.model.rowCount(), "no partial native batch exercised"
    interrupt(panel, method)
    bar = panel.view.verticalScrollBar()
    height = panel.view.visualRect(panel.model.index(0)).height()
    assert height > 0 and bar.value() < bar.maximum()
    row = (bar.value() + 2) // height
    expected = (f"[n] row {3000 + row:05d}", row * height - bar.value())
    drain(panel, delegate)
    assert top(panel) == expected, "a later native batch stole the reader"
    QTest.keyClick(panel.view, Qt.Key.Key_End)
    delegate.seen.clear()
    panel.append(LogLine("n", "tail after End"))
    drain(panel, delegate)
    assert bar.value() == bar.maximum(), "End did not resume following"


def test_pending_refresh_destruction(qtbot: QtBot) -> None:
    panel = BuildLogPanel()
    panel.append(LogLine("n", "queued work"))
    panel.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()
    assert not shiboken6.isValid(panel)


def test_full_cap_layout_yields(qtbot: QtBot) -> None:
    panel = BuildLogPanel()
    qtbot.addWidget(panel)
    delegate = MeasuringDelegate(panel)
    panel.view.setItemDelegate(delegate)
    panel.show()
    panel.toggle.click()
    pulses: list[tuple[int, float]] = []
    timer = QTimer(panel)
    timer.timeout.connect(lambda: pulses.append((len(delegate.seen), monotonic())))
    timer.start(0)
    panel.append(LogLine("n", "\n".join("W" * (i % 75 + 1) for i in range(20_000))))
    drain(panel, delegate)
    timer.stop()
    assert len([n for n, _ in pulses if 0 < n < 20_000]) >= 20
    assert max((b[1] - a[1] for a, b in pairwise(pulses)), default=0) < 1
