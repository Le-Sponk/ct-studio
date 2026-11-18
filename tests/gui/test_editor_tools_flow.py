"""P5-T07e2: card Open in… → choice dialog → "Set up … in Tools…" → the Tools window."""

# pyright: reportPrivateUsage=false
# (the window's tools route is checked through its private slot, as other window tests do)

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import shiboken6
from editor_menu_helpers import flush_deletes, offered
from editor_request_helpers import settled
from editor_tools_helpers import ToolsCheck, selected_tool, tool_row, tools_window
from PySide6.QtWidgets import QApplication, QDialog, QTableWidget
from pytestqt.qtbot import QtBot

from ctstudio.gui.main_window import TOOLS_LATER

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def test_set_up_in_tools_opens_the_tools_window_at_that_editor(
    qtbot: QtBot, tmp_path: Path
) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check) as (window, work):
        page = window.dashboard
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        dialog = offered(qtbot, page)
        assert dialog.setup_button.text() == "Set up RiiStudio in Tools…"
        assert check.calls == [], "the tools were checked before anyone asked"
        dialog.setup_button.click()
        tools = window.tools_window.dialog
        assert tools is not None and tools.isVisible(), "the Tools window did not open"
        assert QApplication.activeModalWidget() is tools
        tools_page = window.tools_window.page
        assert tools_page is not None
        assert settled(qtbot, lambda: not tools_page.busy), "the tools check never finished"
        assert check.calls and check.calls[0] is not threading.main_thread(), "UI-thread check"
        assert selected_tool(tools_page) == "riistudio", "the missing editor is not selected"
        assert [call[0] for call in work.calls] == ["prepare"], "an editor was opened"
        assert page.editors.dialog is None
        tools.reject()


def test_the_editor_is_selected_once_a_running_check_shows_it(qtbot: QtBot, tmp_path: Path) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check) as (window, work):
        check.gate.clear()  # the first check of the Tools window is held
        window.tools_action.trigger()
        tools, tools_page = window.tools_window.dialog, window.tools_window.page
        assert tools is not None and tools_page is not None and tools_page.busy
        tools.reject()
        work.gate.set()
        window.dashboard.cards["course_model"].open_action.trigger()
        offered(qtbot, window.dashboard).setup_button.click()
        assert tools.isVisible() and selected_tool(tools_page) is None, "nothing to select yet"
        check.gate.set()
        assert settled(qtbot, lambda: not tools_page.busy), "the held check never finished"
        assert selected_tool(tools_page) == "riistudio", "the selection was lost"
        assert len(check.calls) == 1, "a second check was started while one was running"
        tools.reject()


def test_a_selection_made_when_idle_is_not_repeated_later(qtbot: QtBot, tmp_path: Path) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check) as (window, _work):
        window.tools_action.trigger()
        tools, tools_page = window.tools_window.dialog, window.tools_window.page
        assert tools is not None and tools_page is not None
        assert settled(qtbot, lambda: not tools_page.busy)
        tools_page.select("riistudio")  # the rows are already shown: selected at once
        assert selected_tool(tools_page) == "riistudio"
        table = tools_page.findChild(QTableWidget, "toolsTable")
        assert table is not None
        table.selectRow(tool_row(table, "brawlcrate"))  # then the user picks another tool
        tools_page.recheck(force=False)
        assert settled(qtbot, lambda: not tools_page.busy)
        assert selected_tool(tools_page) == "brawlcrate", "an old request came back"
        tools.reject()


def test_a_pick_made_while_set_up_rechecks_is_kept(qtbot: QtBot, tmp_path: Path) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check) as (window, work):
        window.tools_action.trigger()  # the Tools window already shows every tool
        tools, tools_page = window.tools_window.dialog, window.tools_window.page
        assert tools is not None and tools_page is not None
        assert settled(qtbot, lambda: not tools_page.busy)
        tools.reject()
        check.gate.clear()  # the recheck that Set up starts is held
        work.gate.set()
        window.dashboard.cards["course_model"].open_action.trigger()
        offered(qtbot, window.dashboard).setup_button.click()
        assert tools_page.busy and selected_tool(tools_page) == "riistudio"
        table = tools_page.findChild(QTableWidget, "toolsTable")
        assert table is not None
        table.selectRow(tool_row(table, "brawlcrate"))  # the user picks another tool meanwhile
        check.gate.set()
        assert settled(qtbot, lambda: not tools_page.busy)
        assert selected_tool(tools_page) == "brawlcrate", "the recheck undid the user's pick"
        tools.reject()


def test_a_later_recheck_keeps_the_users_own_selection(qtbot: QtBot, tmp_path: Path) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check) as (window, work):
        work.gate.set()
        window.dashboard.cards["course_model"].open_action.trigger()
        offered(qtbot, window.dashboard).setup_button.click()
        tools_page = window.tools_window.page
        assert tools_page is not None
        assert settled(qtbot, lambda: not tools_page.busy)
        assert selected_tool(tools_page) == "riistudio"
        table = tools_page.findChild(QTableWidget, "toolsTable")
        assert table is not None
        table.selectRow(tool_row(table, "brawlcrate"))  # the user looks at another tool
        tools_page.recheck(force=False)
        assert settled(qtbot, lambda: not tools_page.busy)
        assert selected_tool(tools_page) == "brawlcrate", "a recheck jumped back to the editor"
        tools = window.tools_window.dialog
        assert tools is not None
        tools.reject()


def test_a_request_the_check_could_not_show_is_dropped(qtbot: QtBot, tmp_path: Path) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check) as (window, work):
        check.fail = True  # the first check of the Tools window fails: no rows are drawn
        work.gate.set()
        window.dashboard.cards["course_model"].open_action.trigger()
        offered(qtbot, window.dashboard).setup_button.click()
        tools, tools_page = window.tools_window.dialog, window.tools_window.page
        assert tools is not None and tools_page is not None
        assert settled(qtbot, lambda: not tools_page.busy)
        assert selected_tool(tools_page) is None
        tools.reject()
        check.fail = False
        window.tools_action.trigger()  # a plain Settings → Tools, later
        assert settled(qtbot, lambda: not tools_page.busy)
        assert selected_tool(tools_page) is None, "an old request picked a tool unasked"
        tools.reject()


def test_a_request_while_no_check_runs_is_not_kept(qtbot: QtBot, tmp_path: Path) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check) as (window, _work):
        check.fail = True  # the window's first check fails: idle, and no rows drawn
        window.tools_action.trigger()
        tools, tools_page = window.tools_window.dialog, window.tools_window.page
        assert tools is not None and tools_page is not None
        assert settled(qtbot, lambda: not tools_page.busy)
        tools_page.select("riistudio")  # nothing to select, and no check that could show it
        assert selected_tool(tools_page) is None
        check.fail = False
        tools_page.recheck(force=False)
        assert settled(qtbot, lambda: not tools_page.busy)
        assert selected_tool(tools_page) is None, "a request outlived the moment it was made"
        tools.reject()


def test_read_only_projects_may_still_set_up_tools_from_the_card(
    qtbot: QtBot, tmp_path: Path
) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check, read_only=True) as (window, work):
        page = window.dashboard
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        dialog = offered(qtbot, page)
        assert not dialog.open_button.isEnabled(), "a read-only project could open"
        dialog.setup_button.click()
        tools, tools_page = window.tools_window.dialog, window.tools_window.page
        assert tools is not None and tools.isVisible(), "read-only blocked the Tools window"
        assert tools_page is not None
        assert settled(qtbot, lambda: not tools_page.busy)
        assert selected_tool(tools_page) == "riistudio"
        assert [call[0] for call in work.calls] == ["prepare"]
        tools.reject()


def test_tools_never_open_over_another_modal_window(qtbot: QtBot, tmp_path: Path) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check) as (window, _work):
        window.about_dialog.open()
        qtbot.waitUntil(lambda: QApplication.activeModalWidget() is window.about_dialog)
        window.dashboard.tools_requested.emit("riistudio")  # e.g. a late request
        assert window.tools_window.dialog is None, "Tools was stacked on another window"
        assert window.dashboard.launch_notice.text() == TOOLS_LATER
        assert check.calls == []
        window.about_dialog.reject()


def test_a_retired_choice_dialog_asks_for_no_tools(qtbot: QtBot, tmp_path: Path) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check) as (window, work):
        page = window.dashboard
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        dialog = offered(qtbot, page)
        project = window.services.project
        assert project is not None
        page.set_project(project, changed=True)  # e.g. project details were saved
        assert shiboken6.isValid(dialog) and dialog.result() == QDialog.DialogCode.Rejected
        before = page.launch_notice.text()
        dialog.setup = "riistudio"  # a late "Set up" finish from the retired dialog
        dialog.finished.emit(QDialog.DialogCode.Rejected.value)
        assert window.tools_window.dialog is None, "a retired dialog opened Tools"
        assert page.launch_notice.text() == before
        flush_deletes()
        assert not shiboken6.isValid(dialog)


def test_choices_found_behind_another_window_say_how_to_see_them(
    qtbot: QtBot, tmp_path: Path
) -> None:
    check = ToolsCheck()
    with tools_window(qtbot, tmp_path, check) as (window, work):
        page = window.dashboard
        page.cards["course_model"].open_action.trigger()
        window.about_dialog.open()
        qtbot.waitUntil(lambda: QApplication.activeModalWidget() is window.about_dialog)
        work.gate.set()
        assert settled(qtbot, lambda: not window.services.launch.busy)
        assert page.editors.dialog is None
        text = page.launch_notice.text()
        assert text.startswith("Editor choices for course_model.brres are ready")
        assert text.endswith("choose Open in… again."), "no way back to the choices"
        window.about_dialog.reject()
