"""Settings → Editors… own-editor helpers (P5-T07f2): drive the add/edit dialog and the
remove question the way a user does."""

from __future__ import annotations

from pathlib import Path

from editor_request_helpers import settled
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from ctstudio.gui.views.custom_tool_dialog import CustomToolDialog
from ctstudio.gui.views.editors_page import EditorsPage

RECORD = {"name": "My Editor", "exe": "C:/Tools/my editor.exe", "args_template": ["{file}"]}


def tool_dialog(qtbot: QtBot, page: EditorsPage) -> CustomToolDialog:
    assert settled(qtbot, lambda: page.tool_dialog is not None), "no editor dialog opened"
    dialog = page.tool_dialog
    assert dialog is not None and dialog.isVisible()
    return dialog


def fill(dialog: CustomToolDialog, name: str, program: str, arguments: str) -> None:
    dialog.name.setText(name)
    dialog.program.setText(program)
    dialog.arguments.setPlainText(arguments)


def save_entry(qtbot: QtBot, page: EditorsPage, dialog: CustomToolDialog) -> None:
    """Press Save on a valid entry and wait for the page's save to finish."""
    dialog.accept()
    assert dialog.problem.isHidden(), f"refused: {dialog.problem.text()}"
    assert settled(qtbot, lambda: page.tool_dialog is None), "the dialog stayed open"
    assert settled(qtbot, lambda: not page.busy), "the save never finished"


def add(qtbot: QtBot, page: EditorsPage, name: str, program: str, arguments: str) -> None:
    page.add_button.click()
    dialog = tool_dialog(qtbot, page)
    fill(dialog, name, program, arguments)
    save_entry(qtbot, page, dialog)


def row(name: str, program: str) -> str:
    """A list row as shown: the program path in the running system's own form."""
    return f"{name} ({Path(program)})"


def listed(page: EditorsPage) -> list[str]:
    return [page.own.item(row).text() for row in range(page.own.count())]


def select(page: EditorsPage, text: str) -> None:
    rows = listed(page)
    assert text in rows, f"{text!r} not listed: {rows}"
    page.own.setCurrentRow(rows.index(text))


def answer_remove(qtbot: QtBot, page: EditorsPage, *, yes: bool) -> None:
    """Press Remove, then Yes or Cancel in the question; wait for any save to finish."""
    page.remove_button.click()
    assert settled(qtbot, lambda: page.question is not None), "no remove question"
    question = page.question
    assert question is not None
    pressed = QMessageBox.StandardButton.Yes if yes else QMessageBox.StandardButton.Cancel
    button = question.button(pressed)
    assert button is not None
    button.click()
    assert settled(qtbot, lambda: page.question is None), "the question stayed open"
    assert settled(qtbot, lambda: not page.busy), "the removal never finished"
