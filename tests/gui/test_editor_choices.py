"""P5-T07e1: the editor-choice dialog offers only available editors and explains the rest."""

from __future__ import annotations

from pathlib import Path

import pytest
from editor_menu_helpers import row_texts
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton
from pytestqt.qtbot import QtBot

from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.gui.editor_launch import EditorOption, PreparedEditors
from ctstudio.gui.views.editor_choices import EditorChoices

pytestmark = pytest.mark.gui
CRATE = EditorChoice("builtin", "brawlcrate")
RII = EditorChoice("builtin", "riistudio")
MINE = EditorChoice("custom", "mine")
LORENZI = EditorChoice("builtin", "kmp_editor_lorenzi")


def prepared(*options: EditorOption) -> PreparedEditors:
    return PreparedEditors(Path("course 日本.brres"), ".brres", options)


MIXED = prepared(
    EditorOption(RII, "RiiStudio", "missing", "RiiStudio was not found.", "Install it."),
    EditorOption(CRATE, "BrawlCrate", "available", "Executable found; loading is unverified.", ""),
    EditorOption(LORENZI, "Lorenzi's KMP Editor", "ineligible", "Needs course.kcl.", "Add it."),
    EditorOption(MINE, "My editor", "available", "Executable found; loading is unverified.", ""),
)


def shown(qtbot: QtBot, choices: PreparedEditors, *, can_open: bool = True) -> EditorChoices:
    dialog = EditorChoices(choices, can_open=can_open)
    qtbot.addWidget(dialog)
    dialog.open()
    qtbot.waitUntil(dialog.isVisible)
    return dialog


def focus_list(qtbot: QtBot, dialog: EditorChoices) -> None:
    """Activate the window first: focus set before activation moves elsewhere offscreen."""
    dialog.activateWindow()
    qtbot.waitUntil(dialog.isActiveWindow)
    dialog.choices.setFocus()
    assert dialog.choices.hasFocus(), "the choice list did not take the keyboard focus"


def enabled_rows(dialog: EditorChoices) -> list[bool]:
    return [
        bool(dialog.choices.item(row).flags() & Qt.ItemFlag.ItemIsEnabled)
        for row in range(dialog.choices.count())
    ]


def test_rows_keep_order_and_only_available_editors_can_be_chosen(qtbot: QtBot) -> None:
    dialog = shown(qtbot, MIXED)
    assert dialog.windowTitle() == "Open course 日本.brres in…"
    assert row_texts(dialog) == [
        "RiiStudio (not found)",
        "BrawlCrate",
        "Lorenzi's KMP Editor (cannot open this file)",
        "My editor",
    ]
    assert enabled_rows(dialog) == [False, True, False, True]
    assert dialog.choices.currentRow() == 1, "the first available editor is preselected"
    assert dialog.open_button.isEnabled() and dialog.open_button.isDefault()
    notes = dialog.notes.text()
    assert "RiiStudio: RiiStudio was not found.\nNext: Install it." in notes
    assert "Lorenzi's KMP Editor: Needs course.kcl.\nNext: Add it." in notes
    assert "cannot tell whether" in notes, "launch-only wording missing"
    tip = dialog.choices.item(0).toolTip()
    assert tip == "RiiStudio was not found.\nNext: Install it."


def test_open_returns_the_selected_exact_choice(qtbot: QtBot) -> None:
    dialog = shown(qtbot, MIXED)
    dialog.choices.setCurrentRow(3)
    dialog.open_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.chosen == MINE


def test_keyboard_moves_between_available_rows_and_return_opens(qtbot: QtBot) -> None:
    dialog = shown(qtbot, MIXED)
    focus_list(qtbot, dialog)
    QTest.keyClick(dialog.choices, Qt.Key.Key_Down)
    assert dialog.choices.currentRow() == 3, "the keyboard landed on an unavailable editor"
    QTest.keyClick(dialog.choices, Qt.Key.Key_Return)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.chosen == MINE


def test_escape_chooses_nothing(qtbot: QtBot) -> None:
    dialog = shown(qtbot, MIXED)
    focus_list(qtbot, dialog)
    QTest.keyClick(dialog.choices, Qt.Key.Key_Escape)
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.chosen is None and not dialog.isVisible()


def test_read_only_projects_see_choices_but_cannot_open(qtbot: QtBot) -> None:
    dialog = shown(qtbot, MIXED, can_open=False)
    assert enabled_rows(dialog) == [False, True, False, True]
    assert not dialog.open_button.isEnabled()
    assert dialog.notes.text().startswith("This project is open read-only here")
    focus_list(qtbot, dialog)
    QTest.keyClick(dialog.choices, Qt.Key.Key_Return)
    assert dialog.isVisible() and dialog.chosen is None, "a read-only dialog opened an editor"
    dialog.open_button.clicked.emit()  # straight into the slot, past Qt's disablement
    assert dialog.chosen is None


def test_with_nothing_available_open_stays_off_and_says_why(qtbot: QtBot) -> None:
    dialog = shown(qtbot, prepared(*MIXED.options[::2]))
    assert enabled_rows(dialog) == [False, False]
    assert dialog.choices.currentRow() == -1
    assert not dialog.open_button.isEnabled()
    assert dialog.notes.text().startswith("No editor here can open this file yet.")
    dialog.open_button.clicked.emit()
    assert dialog.chosen is None


def test_double_click_opens_an_available_row_only(qtbot: QtBot) -> None:
    dialog = shown(qtbot, MIXED)
    dialog.choices.itemDoubleClicked.emit(dialog.choices.item(0))  # unavailable
    assert dialog.isVisible() and dialog.chosen is None
    dialog.choices.itemDoubleClicked.emit(dialog.choices.item(3))
    assert dialog.result() == QDialog.DialogCode.Accepted and dialog.chosen == MINE


def test_the_read_only_note_gives_the_projects_own_reason(qtbot: QtBot) -> None:
    reason = "Could not record the outside edit. Close and reopen CT Studio before editing."
    dialog = EditorChoices(MIXED, can_open=False, why_not=reason)
    qtbot.addWidget(dialog)
    lines = dialog.notes.text().splitlines()
    assert lines[:2] == [
        "This project is open read-only here, so no editor can be started from it.",
        f"Why: {reason}",
    ]
    assert ".." not in dialog.notes.text(), "the reason's own full stop was doubled"
    assert "other CT Studio" not in dialog.notes.text(), "blamed another CT Studio"
    writable = EditorChoices(MIXED, can_open=True, why_not=reason)
    qtbot.addWidget(writable)
    assert "Why:" not in writable.notes.text()


def test_the_list_is_labelled_and_every_row_describes_itself(qtbot: QtBot) -> None:
    dialog = EditorChoices(MIXED, can_open=True)
    qtbot.addWidget(dialog)
    labels = [label for label in dialog.findChildren(QLabel) if label.buddy() is dialog.choices]
    shown = [label.text() for label in labels]
    assert shown == [f"&Choose an editor for {MIXED.document.name}:"]  # no part: the file
    for row, option in enumerate(MIXED.options):
        described = dialog.choices.item(row).data(Qt.ItemDataRole.AccessibleDescriptionRole)
        assert described == dialog.choices.item(row).toolTip() and option.explanation in described


def test_the_heading_names_the_file_as_typed_and_keeps_its_shortcut(qtbot: QtBot) -> None:
    marked = PreparedEditors(Path("<b>course.brres"), ".brres", MIXED.options)
    dialog = shown(qtbot, marked)
    heading = next(each for each in dialog.findChildren(QLabel) if each.buddy() is dialog.choices)
    assert heading.textFormat() == Qt.TextFormat.PlainText
    assert "<b>course.brres" in heading.text()
    elsewhere = dialog.findChildren(QPushButton)[-1]
    elsewhere.setFocus()
    assert not dialog.choices.hasFocus()
    dialog.activateWindow()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is dialog)
    QTest.keyClick(dialog, Qt.Key.Key_C, Qt.KeyboardModifier.AltModifier)
    assert dialog.choices.hasFocus(), "Alt+C no longer reaches the list"
