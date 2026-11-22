"""P5-T07f2 edges found in review: Enter and focus in the Editors window, the editor just
added is selected, a remove answered during a read, an editor removed outside the window,
and Browse…. Real main window, synthetic settings files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from custom_editor_helpers import RECORD, add, fill, listed, row, save_entry, select, tool_dialog
from editor_request_helpers import settled
from editor_settings_helpers import (
    HeldPreferences,
    backups,
    editors_window,
    settings_file,
    write_settings,
)
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMessageBox
from pytestqt.qtbot import QtBot

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def _focused_window(dialog: QDialog) -> None:
    dialog.activateWindow()
    QApplication.processEvents()


def test_enter_outside_the_list_never_adds_or_edits(qtbot: QtBot) -> None:
    write_settings({"format": 1})
    with editors_window(qtbot) as (window, page):
        dialog = window.editors_window.dialog
        assert dialog is not None
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        close = buttons.button(QDialogButtonBox.StandardButton.Close)
        assert close is not None and close.isDefault(), "Close is not the default button"
        own = (page.add_button, page.edit_button, page.remove_button)
        assert not any(button.autoDefault() for button in own), "Enter could press Add…"
        _focused_window(dialog)
        page.own.setFocus()
        QTest.keyClick(page.own, Qt.Key.Key_Return)  # an empty list: nothing to edit
        QApplication.processEvents()
        assert page.tool_dialog is None and dialog.isVisible(), "Enter in the empty list acted"


def test_the_focus_stays_put_after_a_keyboard_save(qtbot: QtBot) -> None:
    write_settings({"format": 1})
    with editors_window(qtbot) as (window, page):
        dialog = window.editors_window.dialog
        assert dialog is not None
        _focused_window(dialog)
        page.tabs.setCurrentWidget(page.own_section)
        page.add_button.setFocus()
        assert page.add_button.hasFocus(), "the probe needs the focus on Add…"
        QTest.keyClick(page.add_button, Qt.Key.Key_Space)
        entry = tool_dialog(qtbot, page)
        fill(entry, "Keys", "C:/k.exe", "{file}")
        save_entry(qtbot, page, entry)
        QApplication.processEvents()
        focus = dialog.focusWidget()  # what gets the keys when the window is in front
        assert focus is page.add_button, f"the focus moved to {focus}"
        QTest.keyClick(page.add_button, Qt.Key.Key_Space)
        again = tool_dialog(qtbot, page)
        assert again.windowTitle() == "Add editor"
        assert dialog.isVisible(), "Space closed the Editors window"
        again.reject()
        assert settled(qtbot, lambda: page.tool_dialog is None)
        page.remove_button.setFocus()
        QTest.keyClick(page.remove_button, Qt.Key.Key_Space)
        assert settled(qtbot, lambda: page.question is not None), "no remove question"
        question = page.question
        assert question is not None
        yes = question.button(QMessageBox.StandardButton.Yes)
        assert yes is not None
        yes.click()
        assert settled(qtbot, lambda: page.question is None and not page.busy)
        assert listed(page) == [] and not page.remove_button.isEnabled()
        assert dialog.focusWidget() is page.own, "Remove is off now: the list keeps the keys"


def test_the_editor_just_added_is_selected(qtbot: QtBot) -> None:
    write_settings({"format": 1, "custom_tools": {"mine": RECORD}})
    with editors_window(qtbot) as (_window, page):
        select(page, row("My Editor", "C:/Tools/my editor.exe"))
        add(qtbot, page, "Second", "C:/second.exe", "{file}")
        assert page.selected_tool() == "custom-second", "the new editor is not selected"
        assert page.edit_button.isEnabled() and page.remove_button.isEnabled()
        add(qtbot, page, "Second", "C:/second.exe", "{file}")
        assert page.selected_tool() == "custom-second-2", "the newest editor is not selected"


def test_editors_added_outside_are_listed_but_not_selected(qtbot: QtBot) -> None:
    write_settings({"format": 1, "custom_tools": {"mine": RECORD}})
    outside = dict(RECORD, name="Outside", exe="C:/outside.exe")
    with editors_window(qtbot) as (_window, page):
        select(page, row("My Editor", "C:/Tools/my editor.exe"))
        page.edit_button.click()
        entry = tool_dialog(qtbot, page)
        fill(entry, "Renamed", "C:/Tools/my editor.exe", "{file}")
        write_settings({"format": 1, "custom_tools": {"mine": RECORD, "custom-outside": outside}})
        save_entry(qtbot, page, entry)
        assert row("Outside", "C:/outside.exe") in listed(page)
        assert page.selected_tool() == "mine", "an edit selected another editor"
        page.add_button.click()
        entry = tool_dialog(qtbot, page)
        fill(entry, "Added", "C:/added.exe", "{file}")
        later = dict(RECORD, name="Later", exe="C:/later.exe")
        current = (
            settings_file()
            .read_text(encoding="utf-8")
            .replace(
                '"custom_tools": {', f'"custom_tools": {{"custom-later": {json.dumps(later)}, ', 1
            )
        )
        settings_file().write_text(current, encoding="utf-8")
        save_entry(qtbot, page, entry)
        assert row("Later", "C:/later.exe") in listed(page)
        assert page.selected_tool() == "custom-added", "the add selected another editor"


def test_a_remove_answered_while_a_read_runs_saves_nothing(qtbot: QtBot) -> None:
    before = write_settings({"format": 1, "custom_tools": {"mine": RECORD}})
    held = HeldPreferences()
    with editors_window(qtbot, held) as (_window, page):
        select(page, row("My Editor", "C:/Tools/my editor.exe"))
        page.remove_button.click()
        assert settled(qtbot, lambda: page.question is not None), "no remove question"
        question = page.question
        assert question is not None
        held.gate.clear()
        page.reload()  # not reachable from the UI: the question blocks the window
        yes = question.button(QMessageBox.StandardButton.Yes)
        assert yes is not None
        yes.click()
        assert settled(qtbot, lambda: page.question is None)
        held.gate.set()
        assert settled(qtbot, lambda: not page.busy)
        assert held.customs == [], "removed during a read"
        assert listed(page) == [row("My Editor", "C:/Tools/my editor.exe")]
    assert settings_file().read_bytes() == before and not backups()


def test_editing_an_editor_removed_outside_writes_nothing(qtbot: QtBot) -> None:
    write_settings({"format": 1, "custom_tools": {"mine": RECORD}})
    with editors_window(qtbot) as (_window, page):
        select(page, row("My Editor", "C:/Tools/my editor.exe"))
        page.edit_button.click()
        entry = tool_dialog(qtbot, page)
        fill(entry, "Renamed", "C:/Tools/my editor.exe", "{file}")
        before = write_settings({"format": 1, "later": True})
        save_entry(qtbot, page, entry)
        assert page.banner.isVisible(), "the lost edit was not reported"
        assert "Renamed was removed outside this window" in page.banner.text()
        assert "not saved" in page.banner.text() and page.note.text() == ""
    assert settings_file().read_bytes() == before and not backups()


def test_browse_fills_in_the_chosen_program(qtbot: QtBot, tmp_path: Path) -> None:
    write_settings({"format": 1})
    tools = tmp_path / "Tools é"
    tools.mkdir()
    with editors_window(qtbot) as (_window, page):
        page.add_button.click()
        entry = tool_dialog(qtbot, page)
        entry.program.setText(f"  {tools}  ")
        entry.browse.click()
        browser = entry.browser
        assert browser is not None and browser.isVisible(), "Browse… opened nothing"
        assert Path(browser.directory().absolutePath()) == tools, "Browse… starts elsewhere"
        chosen = str(tools / "new editor.exe")
        browser.fileSelected.emit(chosen)
        browser.reject()
        assert entry.program.text() == chosen
        entry.browse.click()
        again = entry.browser
        assert again is not None
        again.reject()  # Cancel keeps what was there
        assert entry.program.text() == chosen
        entry.reject()
