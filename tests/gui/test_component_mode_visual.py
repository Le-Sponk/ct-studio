"""P5-T03f: native control/dialog screenshots and keyboard-only cancellation."""

import threading
from pathlib import Path

import pytest
from component_window_helpers import mode_window, window_with_mode_service
from mode_helpers import ModeWork
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMenu
from pytestqt.qtbot import QtBot
from test_dashboard_visual import sample
from wizard_fakes import shot

from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.views.component_mode import ComponentModeDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def dark_palette(app: QApplication) -> QPalette:
    original = app.palette()
    dark = QPalette(original)
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
        dark.setColor(role, QColor("#202530"))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        dark.setColor(role, QColor("#f3f5f8"))
    app.setPalette(dark)
    return original


def assert_cancelled(window: MainWindow, before: bytes, old_status: str) -> None:
    project = window.services.project
    assert project is not None
    card = window.dashboard.cards["kcl"]
    assert not window.services.editing
    assert project.manifest_path.read_bytes() == before
    assert not list(project.root.glob("*.bak"))
    assert card.status_label.text() == old_status
    assert card.mode_label.text() == "Mode: auto"


def test_default_mode_entry_supports_keyboard_cancel(qtbot: QtBot, tmp_path: Path) -> None:
    window = mode_window(qtbot, tmp_path)
    project = window.services.project
    assert project is not None
    before = project.manifest_path.read_bytes()
    card = window.dashboard.cards["kcl"]
    old_status = card.status_label.text()
    try:
        card.mode_button.setFocus()
        qtbot.keyClick(card.mode_button, Qt.Key.Key_Space)
        dialog = window.findChild(ComponentModeDialog, "componentModeDialog")
        assert dialog is not None
        qtbot.waitUntil(lambda: not dialog.busy)
        assert dialog.component_id == "kcl"
        assert dialog.mode.currentData() == "auto"
        assert dialog.save_button.isEnabled()
        dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
        qtbot.keyClick(dialog.mode, Qt.Key.Key_Escape)
        assert_cancelled(window, before, old_status)
    finally:
        window.close()


@pytest.mark.parametrize("save", [False, True], ids=["cancel", "save"])
def test_default_mode_dialog_is_deleted_before_reopening(
    qtbot: QtBot, tmp_path: Path, save: bool
) -> None:
    window = mode_window(qtbot, tmp_path)
    try:
        for mode in ("manual", "auto", "manual"):
            qtbot.waitUntil(lambda: not window.dashboard.busy)
            window.dashboard.cards["kcl"].mode_button.click()
            dialog = window.findChild(ComponentModeDialog, "componentModeDialog")
            assert dialog is not None
            qtbot.waitUntil(lambda active=dialog: not active.busy)
            dialog.mode.setCurrentIndex(dialog.mode.findData(mode))
            if save:
                dialog.save_button.click()
            else:
                dialog.reject()
            qtbot.waitUntil(lambda: window._details is None)
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert window.findChild(ComponentModeDialog, "componentModeDialog") is None
        assert not window.services.editing
    finally:
        window.close()


def test_dashboard_and_mode_menu_images(qtbot: QtBot, tmp_path: Path) -> None:
    window = mode_window(qtbot, tmp_path)
    window.resize(1100, 1050)
    sample(window)
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    try:
        shot(window, "p5-t03f-dashboard-light.png")
        original = dark_palette(app)
        try:
            shot(window, "p5-t03f-dashboard-dark.png")
        finally:
            app.setPalette(original)
        card = window.dashboard.cards["skybox"]
        menu = card.more_button.menu()
        assert menu is not None
        menu.popup(card.more_button.mapToGlobal(QPoint(0, card.more_button.height())))
        shot(menu, "p5-t03f-more-menu.png")
        mode_menu = card.findChild(QMenu, "skyboxModeMenu")
        assert mode_menu is not None
        mode_menu.popup(menu.pos() + QPoint(menu.width(), 0))
        shot(mode_menu, "p5-t03f-mode-menu.png")
        mode_menu.close()
        menu.close()
    finally:
        window.close()


def test_mode_dialog_light_dark_and_error_images(qtbot: QtBot, tmp_path: Path) -> None:
    work = ModeWork()
    window = window_with_mode_service(qtbot, tmp_path, work)
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    try:
        window.dashboard.cards["skybox"].mode_button.click()
        dialog = window.findChild(ComponentModeDialog, "componentModeDialog")
        assert dialog is not None
        qtbot.waitUntil(lambda: not dialog.busy)
        shot(dialog, "p5-t03f-mode-light.png")
        original = dark_palette(app)
        try:
            shot(dialog, "p5-t03f-mode-dark.png")
        finally:
            app.setPalette(original)
        work.save_error = RuntimeError("Synthetic folder unavailable; reconnect it and retry.")
        dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
        dialog.save_button.click()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert not dialog.saved and dialog.isVisible()
        shot(dialog, "p5-t03f-mode-error.png")
    finally:
        window.close()


def test_mode_dialog_saving_image(qtbot: QtBot, tmp_path: Path) -> None:
    work = ModeWork()
    work.save_gate = threading.Event()
    window = window_with_mode_service(qtbot, tmp_path, work)
    try:
        window.dashboard.cards["kcl"].mode_button.click()
        dialog = window.findChild(ComponentModeDialog, "componentModeDialog")
        assert dialog is not None
        qtbot.waitUntil(lambda: not dialog.busy)
        dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
        dialog.save_button.click()
        qtbot.waitUntil(lambda: any(op == "save" for op, _thread in work.calls))
        assert dialog.busy and not dialog.save_button.isEnabled()
        shot(dialog, "p5-t03f-mode-saving.png")
    finally:
        work.save_gate.set()
        qtbot.waitUntil(lambda: not window.services.editing)
        window.close()
