"""P5-T03e33b in the real window: worker CommandRun events become copyable rows, screenshots."""

from pathlib import Path

import pytest
from build_window_helpers import build_window, eventually, finished, started
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QScrollArea
from pytestqt.qtbot import QtBot
from test_build_controls_visual import _readable_font
from test_build_dashboard_visual import _palette
from wizard_fakes import SCREENS, shot

from ctstudio.core.build.events import CommandRun, LogLine
from ctstudio.gui.build_log_model import LogRole
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]

TEXT = '"C:\\Tools\\wszst.exe" create "course café" --dest "out dir"'
SHIFT_CTRL = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier


def _emit_run(window: MainWindow) -> None:
    signal = window.services.build.build_event
    signal.emit(LogLine("stage:kcl", "Collision: 12 triangles checked"))
    signal.emit(CommandRun("stage:kcl", ("C:\\Tools\\wszst.exe", "create"), TEXT))
    signal.emit(LogLine("stage:kcl", "$ wszst looks like a command but is tool output"))


def _copy(window: MainWindow) -> QAction:
    action = window.dashboard.builds.log.findChild(QAction, "build_log_copy_command")
    assert action is not None
    return action


def test_a_worker_command_is_copied_by_keyboard_from_the_dashboard(
    qtbot: QtBot, tmp_path: Path, qapp: QApplication
) -> None:
    previous = qapp.clipboard().text()
    qapp.clipboard().setText("untouched")
    try:
        with build_window(qtbot, tmp_path) as (window, _project, fake):
            log = window.dashboard.builds.log
            window.dashboard.builds.controls.test_button.click()
            started(qtbot, window, fake)
            _emit_run(window)
            assert log.model.rowCount() == 3
            assert log.model.data(log.model.index(1), LogRole.Command) == TEXT
            assert log.model.data(log.model.index(2), LogRole.Command) is None
            log.toggle.click()
            QApplication.processEvents()
            QApplication.processEvents()
            log.toggle.setFocus()
            QTest.keyClick(log.toggle, Qt.Key.Key_Tab)
            assert log.view.hasFocus()
            QTest.keyClick(log.view, Qt.Key.Key_End)
            QTest.keyClick(log.view, Qt.Key.Key_C, SHIFT_CTRL)
            assert qapp.clipboard().text() == "untouched", "tool output must not copy"
            QTest.keyClick(log.view, Qt.Key.Key_Up)
            assert log.view.currentIndex().row() == 1
            QTest.keyClick(log.view, Qt.Key.Key_C, SHIFT_CTRL)
            assert qapp.clipboard().text() == TEXT
            finished(qtbot, window, fake)
            assert _copy(window).isEnabled(), "the finished run's command stays copyable"
    finally:
        qapp.clipboard().setText(previous)


def test_a_command_from_a_rebound_project_is_not_shown(qtbot: QtBot, tmp_path: Path) -> None:
    with build_window(qtbot, tmp_path) as (window, project, fake):
        log = window.dashboard.builds.log
        window.dashboard.builds.controls.test_button.click()
        started(qtbot, window, fake)
        window.dashboard.set_project(project, changed=True)
        window.services.build.build_event.emit(CommandRun("stage:kcl", ("C:\\t.exe",), TEXT))
        assert log.model.rowCount() == 0
        assert not _copy(window).isEnabled()
        finished(qtbot, window, fake)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_command_row_screenshots(qtbot: QtBot, tmp_path: Path, dark: bool) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    old_palette, old_font = app.palette(), app.font()
    font, added = _readable_font(old_font)
    app.setPalette(_palette(old_palette, dark))
    app.setFont(QFont(font))
    try:
        _render(qtbot, tmp_path, "dark" if dark else "light")
    finally:
        app.setPalette(old_palette)
        app.setFont(old_font)
        if added is not None:
            QFontDatabase.removeApplicationFont(added)


def _render(qtbot: QtBot, tmp_path: Path, name: str) -> None:
    with build_window(qtbot, tmp_path) as (window, _project, fake):
        window.resize(1280, 720)
        log = window.dashboard.builds.log
        window.dashboard.builds.controls.test_button.click()
        started(qtbot, window, fake)
        _emit_run(window)
        log.toggle.click()
        eventually(qtbot, log.view.isVisible, "the expanded log did not show its rows")
        log.view.setFocus()
        log.view.setCurrentIndex(log.model.index(1))
        area = window.findChild(QScrollArea, "dashboardScroll")
        assert area is not None
        area.ensureWidgetVisible(log, 0, 0)
        QApplication.processEvents()
        shot(window, f"p5-t03e33b-command-row-{name}.png")
        centre = log.view.visualRect(log.model.index(1)).center()
        log.view.customContextMenuRequested.emit(QPoint(centre))
        menu = log.findChild(QMenu, "build_log_menu")
        assert menu is not None
        eventually(qtbot, menu.isVisible, "the log menu did not open")
        shot(menu, f"p5-t03e33b-command-menu-{name}.png")
        assert (SCREENS / f"p5-t03e33b-command-menu-{name}.png").stat().st_size > 0
        menu.close()
        finished(qtbot, window, fake)
