"""Standalone bounded live-log behavior; dashboard ownership is tested separately."""

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QSizePolicy
from pytestqt.qtbot import QtBot

from ctstudio.core.build.events import LogLine
from ctstudio.gui.build_log_model import BuildLogModel
from ctstudio.gui.views.build_log import BuildLogPanel

pytestmark = [pytest.mark.gui, pytest.mark.timeout(10)]


def test_collapsed_keyboard_toggle_and_empty_state(qtbot: QtBot) -> None:

    panel = BuildLogPanel()
    qtbot.addWidget(panel)
    panel.show()
    assert panel.body.isHidden()
    assert panel.toggle.text() == "Show build log"
    assert panel.toggle.isCheckable() and not panel.toggle.isChecked()
    assert_initial(panel)
    panel.toggle.setFocus()
    QTest.keyClick(panel.toggle, Qt.Key.Key_Space)
    assert not panel.body.isHidden()
    assert panel.toggle.text() == "Hide build log"
    QTest.keyClick(panel.toggle, Qt.Key.Key_Space)
    assert panel.body.isHidden()


def assert_initial(panel: BuildLogPanel) -> None:
    assert panel.history.accessibleDescription() == panel.history.text()
    assert "no output" in panel.history.text().lower()
    assert "start a build" in panel.history.text().lower()
    assert panel.view.isHidden()
    for widget in (panel, panel.toggle, panel.body, panel.view, panel.history):
        assert widget.objectName() and widget.accessibleName()


@pytest.fixture
def panel(qtbot: QtBot) -> BuildLogPanel:
    widget = BuildLogPanel(model=BuildLogModel(max_rows=100))
    qtbot.addWidget(widget)
    widget.resize(480, 260)
    widget.show()
    return widget


def settle() -> None:
    for _ in range(8):
        QApplication.processEvents()


def fill(panel: BuildLogPanel, start: int = 0, count: int = 80) -> None:
    assert callable(getattr(panel, "append", None)), "append(LogLine) is missing"
    for number in range(start, start + count):
        panel.append(LogLine("é-step", f"literal <b>row {number}</b> $ not a command"))


def top(panel: BuildLogPanel) -> tuple[object, int]:
    index = panel.view.indexAt(QPoint(2, 2))
    return index.data(), panel.view.visualRect(index).top()


def test_hidden_collection_injected_caps_and_literal_text(qtbot: QtBot) -> None:
    model = BuildLogModel(max_rows=3, max_line_chars=8)
    widget = BuildLogPanel(model=model)
    qtbot.addWidget(widget)
    assert widget.model is model
    fill(widget, count=5)
    settle()
    assert widget.body.isHidden()
    assert model.rowCount() == 3 and model.dropped_rows == 2
    assert model.index(2).data() == "[é-step] …command"
    assert "3 retained" in widget.history.text() and "2 omitted" in widget.history.text()
    assert "shorten" in widget.history.text().lower()
    assert "disk" in widget.history.text().lower()
    assert_history_policy(widget)
    assert not widget.view.isHidden()


def assert_history_policy(widget: BuildLogPanel) -> None:
    assert widget.history.textFormat() == Qt.TextFormat.PlainText
    assert widget.history.wordWrap()
    assert widget.history.accessibleDescription() == widget.history.text()
    assert widget.history.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored


def test_follow_is_coalesced_and_keyboard_reachable(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel = BuildLogPanel(model=BuildLogModel(max_rows=2000))
    qtbot.addWidget(panel)
    panel.show()
    panel.toggle.click()
    calls: list[int] = []
    original = panel.view.scrollToBottom

    def scroll() -> None:
        calls.append(1)
        original()

    monkeypatch.setattr(panel.view, "scrollToBottom", scroll)
    fill(panel, count=1000)
    assert not calls, "each append must not force a layout/scroll"
    settle()
    assert 1 <= len(calls) <= 8  # One burst callback, then native layout-batch completions.
    assert panel.view.visualRect(panel.model.index(999)).isValid()
    bar = panel.view.verticalScrollBar()
    assert bar.maximum() > 0 and bar.value() == bar.maximum()
    panel.toggle.setFocus()
    QTest.keyClick(panel.toggle, Qt.Key.Key_Tab)
    assert panel.view.hasFocus()
    QTest.keyClick(panel.view, Qt.Key.Key_Home)
    assert panel.view.currentIndex().row() == 0


@pytest.mark.parametrize("hidden", [False, True])
def test_reading_position_and_selection_survive_eviction(
    panel: BuildLogPanel, hidden: bool
) -> None:
    panel.resize(240, 260)
    panel.toggle.click()
    fill(panel)
    settle()
    panel.view.setCurrentIndex(panel.model.index(35))
    panel.view.scrollTo(panel.model.index(30), QAbstractItemView.ScrollHint.PositionAtTop)
    settle()
    vertical = panel.view.verticalScrollBar()
    vertical.setValue(vertical.value() + 3)
    horizontal = panel.view.horizontalScrollBar()
    assert horizontal.maximum() > 0
    horizontal.setValue(horizontal.maximum())
    sideways = horizontal.value()
    before, offset = top(panel)
    selected = panel.view.currentIndex().data()
    if hidden:
        panel.toggle.click()
    fill(panel, 80, 30)
    settle()
    if hidden:
        panel.toggle.click()
        settle()
    assert top(panel) == (before, offset)
    assert horizontal.value() == sideways
    assert panel.view.currentIndex().data() == selected
    assert panel.view.currentIndex().row() == 25
    assert panel.view.verticalScrollBar().value() < panel.view.verticalScrollBar().maximum()


def test_scroll_up_before_pending_follow_and_end_resumes(
    panel: BuildLogPanel, qtbot: QtBot
) -> None:
    panel.toggle.click()
    fill(panel)
    settle()
    fill(panel, 80, 5)
    bar = panel.view.verticalScrollBar()
    bar.setValue(0)
    settle()
    assert bar.value() == 0
    panel.view.setFocus()
    QTest.keyClick(panel.view, Qt.Key.Key_End)
    settle()
    fill(panel, 85, 5)
    settle()
    assert bar.value() == bar.maximum()
    panel.toggle.click()
    fill(panel, 90, 50)
    settle()
    panel.toggle.click()
    settle()
    assert bar.value() == bar.maximum()


@pytest.mark.parametrize("collapse", [False, True])
def test_clear_stops_pending_work_resets_selection_and_reuses(
    panel: BuildLogPanel, collapse: bool
) -> None:
    panel.toggle.click()
    fill(panel, count=150)
    panel.view.setCurrentIndex(panel.model.index(15))
    assert callable(getattr(panel, "clear", None)), "clear is missing"
    panel.clear(collapse=collapse)
    assert not any(timer.isActive() for timer in panel.findChildren(QTimer))
    settle()
    assert_cleared(panel, collapse)
    fill(panel, 200, 90)
    if collapse:
        panel.toggle.click()
    settle()
    assert "0 omitted" in panel.history.text()
    assert panel.view.verticalScrollBar().value() == panel.view.verticalScrollBar().maximum()


def assert_cleared(panel: BuildLogPanel, collapse: bool) -> None:
    assert panel.model.rowCount() == panel.model.dropped_rows == 0
    assert not panel.view.currentIndex().isValid()
    assert not panel.view.selectionModel().hasSelection()
    assert panel.body.isHidden() is collapse
    assert panel.view.isHidden() and "no output" in panel.history.text().lower()


def test_long_rows_scroll_internally_and_font_height_is_bounded(panel: BuildLogPanel) -> None:
    panel.toggle.click()
    assert callable(getattr(panel, "append", None)), "append is missing"
    panel.append(LogLine("step", "short"))
    panel.append(LogLine("step", "W" * 4000))
    panel.append(LogLine("step", "short again"))
    settle()
    panel.view.setCurrentIndex(panel.model.index(1))
    panel.view.scrollTo(panel.model.index(1))
    settle()
    assert panel.width() == 480
    assert panel.view.horizontalScrollBar().maximum() > 0
    horizontal = panel.view.horizontalScrollBar()
    horizontal.setValue(horizontal.maximum())
    assert panel.view.visualRect(panel.model.index(1)).right() <= panel.view.viewport().width()
    assert not panel.view.wordWrap()
    assert panel.view.textElideMode() == Qt.TextElideMode.ElideNone
    assert panel.view.height() <= 9 * panel.view.fontMetrics().lineSpacing() + 30
    font = QFont(panel.font())
    font.setPointSizeF(font.pointSizeF() * 1.5)
    panel.setFont(font)
    settle()
    assert panel.view.height() >= 6 * panel.view.fontMetrics().lineSpacing()
    assert panel.view.height() <= 9 * panel.view.fontMetrics().lineSpacing() + 30
