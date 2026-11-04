"""P5-T03c: native-palette details dialog, keyboard use and busy/error screenshots."""

import threading
from pathlib import Path

import pytest
from details_helpers import DetailsWork
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from test_project_details_window import window_with_details
from wizard_fakes import shot

from ctstudio.gui.views.project_details import ProjectDetailsDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_details_dialog_screenshots(qtbot: QtBot, tmp_path: Path) -> None:
    work = DetailsWork()
    view = window_with_details(qtbot, tmp_path, work)
    view.dashboard.edit_button.click()
    dialog = view.findChild(ProjectDetailsDialog, "projectDetailsDialog")
    assert dialog is not None
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    original = app.palette()
    gate = threading.Event()
    try:
        qtbot.waitUntil(lambda: not dialog.busy)
        assert dialog.minimumSizeHint().width() <= 720
        assert dialog.save_button.isEnabled()
        shot(dialog, "p5-t03c-details-light.png")
        dark = QPalette(original)
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
            dark.setColor(role, QColor("#202530"))
        for role in (
            QPalette.ColorRole.WindowText,
            QPalette.ColorRole.Text,
            QPalette.ColorRole.ButtonText,
        ):
            dark.setColor(role, QColor("#f3f5f8"))
        dark.setColor(QPalette.ColorRole.PlaceholderText, QColor("#adb3bf"))
        app.setPalette(dark)
        shot(dialog, "p5-t03c-details-dark.png")
        app.setPalette(original)
        dialog.source.setText(str(tmp_path / "Missing source.blend"))
        dialog.accept()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert "Could not save" in dialog.problem.text()
        shot(dialog, "p5-t03c-details-error.png")
        work.save_gate = gate
        dialog.source.clear()
        dialog.slot.setCurrentIndex(1)
        dialog.accept()
        assert dialog.busy and dialog.progress.isVisible()
        shot(dialog, "p5-t03c-details-saving.png")
    finally:
        gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        app.setPalette(original)
        if not dialog.saved:
            dialog.reject()
        view.close()


@pytest.mark.parametrize("save", [False, True])
def test_keyboard_save_and_escape_cancel(qtbot: QtBot, tmp_path: Path, save: bool) -> None:
    view = window_with_details(qtbot, tmp_path, DetailsWork())
    project = view.services.project
    assert project is not None
    before = project.manifest_path.read_bytes()
    view.dashboard.edit_button.setFocus()
    qtbot.keyClick(view.dashboard.edit_button, Qt.Key.Key_Space)
    dialog = view.findChild(ProjectDetailsDialog, "projectDetailsDialog")
    assert dialog is not None
    try:
        qtbot.waitUntil(lambda: not dialog.busy)
        dialog.slot.setFocus()
        qtbot.keyClick(dialog.slot, Qt.Key.Key_Down)
        qtbot.keyClick(dialog.slot, Qt.Key.Key_Tab)
        assert dialog.source.hasFocus()
        qtbot.keyClick(dialog.source, Qt.Key.Key_Tab)
        assert dialog.choose_button.hasFocus()
        qtbot.keyClick(dialog.choose_button, Qt.Key.Key_Tab)
        assert dialog.clear_button.hasFocus()
        qtbot.keyClick(dialog.clear_button, Qt.Key.Key_Tab)
        assert dialog.save_button.hasFocus()
        if save:
            qtbot.keyClick(dialog.save_button, Qt.Key.Key_Return)
        else:
            qtbot.keyClick(dialog.save_button, Qt.Key.Key_Escape)
        qtbot.waitUntil(lambda: not view.services.editing)
        assert (project.manifest_path.read_bytes() != before) == save
    finally:
        view.close()
