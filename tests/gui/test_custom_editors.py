"""P5-T07f2: the user's own editor programs in Settings → Editors….

Every test drives the real main window and the real settings file (synthetic contents).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from custom_editor_helpers import (
    RECORD,
    add,
    answer_remove,
    fill,
    listed,
    row,
    save_entry,
    select,
    tool_dialog,
)
from editor_request_helpers import settled
from editor_settings_helpers import (
    HeldPreferences,
    backups,
    editors_window,
    saved,
    settings_file,
    write_settings,
)
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from ctstudio.core.project import settings
from ctstudio.core.project.custom_tool_preferences import check_id
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.spec import CustomTool
from ctstudio.gui.editor_settings import fresh_id
from ctstudio.gui.views.custom_tool_dialog import custom_entry

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def test_an_added_editor_is_saved_with_a_backup_and_unknown_fields(qtbot: QtBot) -> None:
    write_settings({"format": 1, "later": {"kept": [1, 2]}, "custom_tools": {}})
    with editors_window(qtbot) as (_window, page):
        assert listed(page) == []
        assert not page.edit_button.isEnabled() and not page.remove_button.isEnabled()
        add(qtbot, page, "  Paint é  ", " C:/Tools/paint é.exe ", "{file}\n\n--folder={dir}\n")
        assert listed(page) == [row("Paint é", "C:/Tools/paint é.exe")]
        assert page.note.text() == "Added Paint é. Open in… offers it next time."
    data = saved()
    assert data["later"] == {"kept": [1, 2]}, "an unknown field was lost"
    assert data["custom_tools"] == {
        "custom-paint-e": {
            "name": "Paint é",
            "exe": str(Path("C:/Tools/paint é.exe")),
            "args_template": ["{file}", "--folder={dir}"],
        }
    }
    assert len(backups()) == 1, "no backup was kept"


def test_a_new_entry_starts_with_the_file_argument(qtbot: QtBot) -> None:
    write_settings({"format": 1})
    with editors_window(qtbot) as (_window, page):
        labels = page.findChildren(QLabel)
        headings = [label.text() for label in labels if label.buddy() is page.own]
        assert headings == ["Your own editors (Open in… offers them for every file):"], headings
        page.add_button.click()
        dialog = tool_dialog(qtbot, page)
        assert dialog.windowTitle() == "Add editor"
        assert (dialog.name.text(), dialog.program.text()) == ("", "")
        assert dialog.arguments.toPlainText() == "{file}"
        dialog.reject()


def test_a_new_id_never_reuses_a_taken_one(qtbot: QtBot) -> None:
    write_settings(
        {
            "format": 1,
            "custom_tools": {"custom-paint": dict(RECORD, name="Paint")},
            "wine_prefixes": {"custom-paint-2": {"prefix": "/home/me/.wine-old"}},
        }
    )
    with editors_window(qtbot) as (_window, page):
        add(qtbot, page, "Paint", "C:/Tools/other.exe", "{file}")
        add(qtbot, page, "BrawlCrate", "C:/Tools/bc.exe", "{file}")
    tools = saved()["custom_tools"]
    assert isinstance(tools, dict)
    ids = sorted(str(key) for key in cast("dict[object, object]", tools))
    assert ids == ["custom-brawlcrate", "custom-paint", "custom-paint-3"], ids
    assert settings.load().wine_prefixes() == {"custom-paint-2": Path("/home/me/.wine-old")}


def test_editing_keeps_the_id_and_unknown_record_fields(qtbot: QtBot) -> None:
    record = dict(RECORD, later_field={"keep": True})
    write_settings({"format": 1, "custom_tools": {"mine": record}})
    with editors_window(qtbot) as (_window, page):
        select(page, row("My Editor", "C:/Tools/my editor.exe"))
        assert page.edit_button.isEnabled() and page.remove_button.isEnabled()
        page.own.currentItem().setSelected(False)  # as Ctrl+click on the selected row does
        assert page.own.currentItem() is not None, "the probe needs a current, unselected row"
        assert not page.edit_button.isEnabled() and not page.remove_button.isEnabled()
        select(page, row("My Editor", "C:/Tools/my editor.exe"))
        page.edit_button.click()
        dialog = tool_dialog(qtbot, page)
        assert dialog.windowTitle() == "Edit editor"
        assert dialog.name.text() == "My Editor"
        assert dialog.program.text() == str(Path("C:/Tools/my editor.exe"))
        assert dialog.arguments.toPlainText() == "{file}"
        fill(dialog, "Renamed", "C:/Tools/my editor.exe", "--open\n{file}")
        save_entry(qtbot, page, dialog)
        assert page.note.text() == "Saved Renamed. Open in… uses the change next time."
        assert page.selected_tool() == "mine", "the edited editor is no longer selected"
    assert saved()["custom_tools"] == {
        "mine": {
            "name": "Renamed",
            "exe": str(Path("C:/Tools/my editor.exe")),
            "args_template": ["--open", "{file}"],
            "later_field": {"keep": True},
        }
    }


def test_an_unchanged_edit_writes_nothing(qtbot: QtBot) -> None:
    before = write_settings({"format": 1, "custom_tools": {"mine": RECORD}})
    with editors_window(qtbot) as (_window, page):
        select(page, row("My Editor", "C:/Tools/my editor.exe"))
        page.edit_button.click()
        dialog = tool_dialog(qtbot, page)
        dialog.program.setText("C:/Tools/my editor.exe")
        save_entry(qtbot, page, dialog)
    assert settings_file().read_bytes() == before and not backups(), "rewritten for nothing"


@pytest.mark.parametrize(
    ("name", "program", "arguments", "reason"),
    [
        ("", "C:/e.exe", "{file}", "Enter a name and the program to start."),
        ("Ed", "   ", "{file}", "Enter a name and the program to start."),
        ("Ed", "C:/e.exe", "--x\n{path}", "The argument {path} cannot be used: the only"),
        ("Ed", "C:/e.exe", "{file!r}", "The argument {file!r} cannot be used"),
        ("Ed", "C:/e.exe", "{", "The argument { cannot be used"),
        ("Ed\0", "C:/e.exe", "{file}", "The name contains a NUL character"),
        ("Ed", "C:/e\0.exe", "{file}", "The program contains a NUL character"),
    ],
    ids=[
        "no name",
        "blank program",
        "unknown field",
        "conversion",
        "brace",
        "nul name",
        "nul program",
    ],
)
def test_an_invalid_entry_is_refused_with_the_reason(
    qtbot: QtBot, name: str, program: str, arguments: str, reason: str
) -> None:
    before = write_settings({"format": 1})
    held = HeldPreferences()
    with editors_window(qtbot, held) as (_window, page):
        page.add_button.click()
        dialog = tool_dialog(qtbot, page)
        fill(dialog, name, program, arguments)
        dialog.accept()
        assert dialog.isVisible(), "the dialog closed on an invalid entry"
        assert dialog.problem.isVisible() and reason in dialog.problem.text(), dialog.problem.text()
        assert (
            dialog.problem.textFormat() == Qt.TextFormat.PlainText
        )  # it can quote the typed arguments
        fill(dialog, "Fixed", "C:/fixed.exe", "{file}")
        dialog.accept()
        assert settled(qtbot, lambda: page.tool_dialog is None), "a fixed entry was refused"
        assert settled(qtbot, lambda: not page.busy)
    assert held.customs[:1] == [(None, CustomTool("Fixed", Path("C:/fixed.exe"), ["{file}"]))]
    assert settings_file().read_bytes() != before


def test_cancel_saves_nothing(qtbot: QtBot) -> None:
    before = write_settings({"format": 1})
    held = HeldPreferences()
    with editors_window(qtbot, held) as (_window, page):
        page.add_button.click()
        dialog = tool_dialog(qtbot, page)
        fill(dialog, "Ed", "C:/e.exe", "{file}")
        dialog.reject()
        assert settled(qtbot, lambda: page.tool_dialog is None)
        assert not page.busy and held.customs == []
    assert settings_file().read_bytes() == before


def test_removing_asks_first_and_keeps_other_editors(qtbot: QtBot) -> None:
    other = dict(RECORD, name="Other", exe="C:/Tools/other.exe")
    write_settings({"format": 1, "custom_tools": {"mine": RECORD, "other": other}})
    with editors_window(qtbot) as (_window, page):
        select(page, row("My Editor", "C:/Tools/my editor.exe"))
        page.remove_button.click()
        assert settled(qtbot, lambda: page.question is not None), "no remove question"
        question = page.question
        assert question is not None
        QTest.keyClick(question, Qt.Key.Key_Return)
        assert settled(qtbot, lambda: page.question is None)
        assert len(listed(page)) == 2 and not backups(), "Enter removed it"
        answer_remove(qtbot, page, yes=False)
        assert len(listed(page)) == 2 and not backups(), "Cancel removed it"
        answer_remove(qtbot, page, yes=True)
        assert listed(page) == [row("Other", "C:/Tools/other.exe")]
        assert page.note.text() == "Removed My Editor. Open in… no longer offers it."
        assert not page.edit_button.isEnabled(), "a removed editor stayed selected"
    assert saved()["custom_tools"] == {"other": other}
    assert len(backups()) == 1


def test_reopening_shows_editors_changed_outside(qtbot: QtBot) -> None:
    write_settings({"format": 1})
    with editors_window(qtbot) as (window, page):
        dialog = window.editors_window.dialog
        assert dialog is not None
        dialog.reject()
        write_settings({"format": 1, "custom_tools": {"mine": RECORD}})
        window.editors_action.trigger()
        assert settled(qtbot, lambda: not page.busy)
        assert listed(page) == [row("My Editor", "C:/Tools/my editor.exe")]


def test_editors_stay_off_while_busy_and_on_a_damaged_file(qtbot: QtBot) -> None:
    write_settings({"format": 1, "custom_tools": {"mine": RECORD}})
    held = HeldPreferences()
    with editors_window(qtbot, held) as (_window, page):
        select(page, row("My Editor", "C:/Tools/my editor.exe"))
        held.gate.clear()
        page.reload()
        assert page.busy
        buttons = (page.add_button, page.edit_button, page.remove_button)
        assert not page.own.isEnabled() and not any(b.isEnabled() for b in buttons)
        page.add_tool()
        page.edit_tool()
        page.remove_tool()
        assert page.tool_dialog is None and page.question is None, "opened while busy"
        before = write_settings("{damaged after shown")
        held.gate.set()
        assert settled(qtbot, lambda: not page.busy)
        assert page.banner.isVisible() and "cannot be used" in page.banner.text()
        assert not page.own.isEnabled() and not any(b.isEnabled() for b in buttons)
        assert held.customs == []
    assert settings_file().read_bytes() == before and not backups()


def test_a_save_refused_by_a_file_damaged_meanwhile_writes_nothing(qtbot: QtBot) -> None:
    write_settings({"format": 1, "custom_tools": {"mine": RECORD}})
    with editors_window(qtbot) as (_window, page):
        page.add_button.click()
        dialog = tool_dialog(qtbot, page)
        fill(dialog, "Ed", "C:/e.exe", "{file}")
        before = write_settings('{"format": 99}')
        save_entry(qtbot, page, dialog)
        assert page.banner.isVisible() and "cannot be used" in page.banner.text()
        assert listed(page) == [row("My Editor", "C:/Tools/my editor.exe")], "showed an unsaved add"
    assert settings_file().read_bytes() == before and not backups()


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [("a\udc80", "The arguments contain text that cannot be saved")],
)
def test_text_qt_cannot_carry_is_still_refused(arguments: str, reason: str) -> None:
    """Qt replaces a lone surrogate as it is typed; the check refuses it anyway."""
    try:
        custom_entry("Ed", "C:/e.exe", arguments)
    except ValueError as exc:
        assert reason in str(exc), str(exc)
    else:
        raise AssertionError("the entry was accepted")


NONE_TAKEN: frozenset[str] = frozenset()


@pytest.mark.parametrize(
    ("name", "taken", "expected"),
    [
        ("My Editor é!", NONE_TAKEN, "custom-my-editor-e"),
        ("Ünïcødé 编辑器", NONE_TAKEN, "custom-unicde"),
        ("", NONE_TAKEN, "custom-tool"),
        ("ÉÉ", NONE_TAKEN, "custom-ee"),
        ("编辑器", NONE_TAKEN, "custom-tool"),
        ("x", frozenset({"custom-x", "custom-x-2"}), "custom-x-3"),
        ("A" * 60, NONE_TAKEN, "custom-" + "a" * 40),
        ("a" * 39 + " b", NONE_TAKEN, "custom-" + "a" * 39),
    ],
)
def test_fresh_ids_are_valid_and_free(name: str, taken: frozenset[str], expected: str) -> None:
    tool_id = fresh_id(name, taken)
    assert tool_id == expected
    assert check_id(tool_id) == tool_id, "the settings file would refuse the id"


def test_no_built_in_id_looks_like_a_custom_one() -> None:
    """Fresh ids skip only custom and Wine-prefix ids; built-ins must never start custom-."""
    assert not [tool_id for tool_id in TOOL_BY_ID if tool_id.startswith("custom-")]


def test_an_entry_saved_while_a_read_runs_starts_nothing(qtbot: QtBot) -> None:
    write_settings({"format": 1})
    held = HeldPreferences()
    with editors_window(qtbot, held) as (_window, page):
        page.add_button.click()
        dialog = tool_dialog(qtbot, page)
        fill(dialog, "Ed", "C:/e.exe", "{file}")
        held.gate.clear()
        page.reload()  # not reachable from the UI: the entry dialog blocks the window
        dialog.accept()
        assert settled(qtbot, lambda: page.tool_dialog is None)
        held.gate.set()
        assert settled(qtbot, lambda: not page.busy)
        assert held.customs == [] and listed(page) == [], "saved during a read"
