"""The real dashboard log remains readable and keyboard-reachable in a small window."""

from pathlib import Path

import pytest
from build_fakes import summary
from build_window_helpers import build_window, eventually, finished, started
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget
from pytestqt.qtbot import QtBot
from test_build_controls_visual import _readable_font
from test_build_dashboard_visual import _palette
from wizard_fakes import shot

from ctstudio.core.build.events import BuildFinished, LogLine
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def _reveal(window: MainWindow, widget: QWidget) -> QScrollArea:
    QApplication.processEvents()
    area = window.findChild(QScrollArea, "dashboardScroll")
    assert area is not None
    area.ensureWidgetVisible(widget, 0, 0)
    QApplication.processEvents()
    return area


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("scaled", [False, True], ids=["native", "font150"])
def test_live_log_screenshots(qtbot: QtBot, tmp_path: Path, dark: bool, scaled: bool) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    old_palette, old_font = app.palette(), app.font()
    font, added = _readable_font(old_font)
    if scaled:
        font.setPointSizeF(old_font.pointSizeF() * 1.5)
        font.setStretch(120)
    app.setPalette(_palette(old_palette, dark))
    app.setFont(QFont(font))
    try:
        _render(
            qtbot,
            tmp_path,
            f"{'dark' if dark else 'light'}-{'150' if scaled else 'native'}",
            scaled,
        )
    finally:
        app.setPalette(old_palette)
        app.setFont(old_font)
        if added is not None:
            QFontDatabase.removeApplicationFont(added)


def _render(qtbot: QtBot, tmp_path: Path, name: str, scaled: bool) -> None:
    with build_window(qtbot, tmp_path) as (window, _project, fake):
        window.resize(720, 480) if scaled else window.resize(1280, 720)
        log, controls = window.dashboard.builds.log, window.dashboard.builds.controls
        assert log.history.fontMetrics().inFontUcs4(ord("B"))
        _reveal(window, controls)
        shot(window, f"p5-t03e32-log-collapsed-{name}.png")
        controls.test_button.click()
        started(qtbot, window, fake)
        window.services.build.build_event.emit(
            LogLine("stage:kcl", "\n".join(f"Collision message {i}" for i in range(20_003)))
        )
        assert log.model.rowCount() == 20_000 and log.model.dropped_rows == 3
        assert log.body.isHidden() and controls.cancel_button.isEnabled()
        log.toggle.click()
        eventually(
            qtbot, lambda: _tail_visible(window), "native log batches did not reach the tail"
        )
        _check_log(window)
        shot(window, f"p5-t03e32-log-output-{name}.png")
        fake.events[-1] = BuildFinished(summary("failed", ran=(), failed=("stage:kcl",)))
        finished(qtbot, window, fake)
        _reveal(window, log)
        assert log.model.rowCount() == 20_000
        shot(window, f"p5-t03e32-log-retained-{name}.png")


def _tail_visible(window: MainWindow) -> bool:
    view = window.dashboard.builds.log.view
    row = view.visualRect(window.dashboard.builds.log.model.index(19_999))
    bar = view.verticalScrollBar()
    return (
        row.isValid() and row.bottom() < view.viewport().height() and bar.value() == bar.maximum()
    )


def _check_log(window: MainWindow) -> None:
    log = window.dashboard.builds.log
    area = _reveal(window, log)
    assert log.view.isVisibleTo(window)
    assert area.horizontalScrollBar().maximum() == 0
    assert log.width() <= area.viewport().width()
    assert log.history.textFormat() == Qt.TextFormat.PlainText
    assert log.history.accessibleDescription() == log.history.text()
    assert "20000" in log.history.text().replace(",", "") and "3" in log.history.text()
    assert (
        area.viewport()
        .rect()
        .contains(log.history.mapTo(area.viewport(), log.history.rect().bottomLeft()))
    )


def _assert_in_view(window: MainWindow, widget: QWidget) -> None:
    QApplication.processEvents()
    area = window.findChild(QScrollArea, "dashboardScroll")
    assert area is not None
    bottom = widget.mapTo(area.viewport(), widget.rect().bottomLeft())
    assert area.viewport().rect().contains(bottom)


def test_native_tab_from_log_to_cancel_and_build_after_collapse(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with build_window(qtbot, tmp_path) as (window, _project, fake):
        window.resize(720, 480)
        log, controls = window.dashboard.builds.log, window.dashboard.builds.controls
        controls.test_button.click()
        started(qtbot, window, fake)
        window.services.build.build_event.emit(LogLine("n", "\n".join(map(str, range(80)))))
        _reveal(window, log.toggle)
        log.toggle.setFocus()
        QTest.keyClick(log.toggle, Qt.Key.Key_Space)
        assert log.toggle.isChecked()
        # Native Tab scrolling needs the expanded body's final geometry.
        QApplication.processEvents()
        QApplication.processEvents()
        QTest.keyClick(log.toggle, Qt.Key.Key_Tab)
        assert log.view.hasFocus()
        QTest.keyClick(log.view, Qt.Key.Key_End)
        assert log.view.currentIndex().row() == 79
        QTest.keyClick(log.view, Qt.Key.Key_Tab)
        assert controls.cancel_button.hasFocus()
        _assert_in_view(window, controls.cancel_button)
        log.toggle.click()
        finished(qtbot, window, fake)
        _reveal(window, log.toggle)
        log.toggle.setFocus()
        QTest.keyClick(log.toggle, Qt.Key.Key_Tab)
        assert controls.test_button.hasFocus()
        _assert_in_view(window, controls.test_button)
