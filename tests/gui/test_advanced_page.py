"""P5-T08e1: Settings → Advanced on the real main window.

"Tool commands in the build log": Shown (the default) or Hidden, read from ``settings.json``
on the page's worker and saved at once through a fresh read; a damaged or newer file is
shown and never overwritten. Below it the open project's reserved ``[build]
extra_wszst_args``, read-only, shown again at every opening; no project: explained.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from advanced_helpers import open_advanced, pick, project_with_args
from editor_request_helpers import settled
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot
from settings_window_helpers import main_window, settings_dialog
from tools_fakes import FakeDoctor, doctor, settings_file

from ctstudio.core.project import settings
from ctstudio.core.project.settings import SHOW_TOOL_COMMANDS
from ctstudio.core.tools.commands import command_text
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.views.advanced_page import NO_PROJECT, NONE_SAVED, RESERVED_NOTE

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
__all__ = ["doctor", "settings_file"]  # fixtures used by name
DAMAGED = '{"format": 1, "show_tool_commands": 1}\n'
ARGUMENTS = ("--long-name", "a path with spaces é", 'quote " inside')


def saved() -> dict[str, object]:
    return json.loads(settings.default_path().read_text(encoding="utf-8"))


def write(text: str) -> None:
    path = settings.default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def focused(dialog: QWidget) -> QWidget | None:
    widget = QApplication.focusWidget()
    return widget if widget is not None and dialog.isAncestorOf(widget) else None


def opened(qtbot: QtBot, window: MainWindow, folder: Path, arguments: tuple[str, ...]) -> None:
    window._opened(project_with_args(folder, arguments))  # pyright: ignore[reportPrivateUsage]
    assert settled(qtbot, lambda: not window.dashboard.busy), "the dashboard check hung"


def reserved_text(window: MainWindow) -> str:
    page = window.settings_window.advanced_page
    assert page is not None
    return page.reserved.text().replace("\u200b", "")


def test_the_page_offers_shown_and_hidden_and_starts_at_shown(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        combo = page.commands.combo
        offered = [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]
        assert offered == [("Shown", True), ("Hidden", False)]
        assert combo.currentData() is True, "no saved choice must mean shown"
        assert combo.isEnabled() and combo.isVisible()
        label = page.commands.label
        assert label.text() == "&Tool commands in the build log" and label.buddy() is combo


def test_a_pick_is_saved_at_once_and_read_back(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    write('{"future": [1]}')
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        pick(page, False)
        assert settled(qtbot, lambda: not page.busy and bool(page.commands.note.text()))
        assert saved() == {"format": 1, "future": [1], SHOW_TOOL_COMMANDS: False, "tools": {}}
        note = page.commands.note.text()
        assert note == "Saved. The next build's log leaves the tool commands out.", note
        pick(page, True)
        assert settled(qtbot, lambda: not page.busy and "shows" in page.commands.note.text())
        assert saved()[SHOW_TOOL_COMMANDS] is True
        assert page.commands.note.text() == "Saved. The next build's log shows the tool commands."


def test_a_file_damaged_after_reading_is_refused_and_the_keyboard_kept_near(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        dialog = settings_dialog(window)
        write(DAMAGED)
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
        combo = page.commands.combo
        combo.setFocus()
        assert combo.hasFocus(), "the choice could not take the focus"
        QTest.keyClick(combo, Qt.Key.Key_Down)
        assert settled(qtbot, lambda: not page.busy and combo.isHidden())
        assert settings.default_path().read_text(encoding="utf-8") == DAMAGED
        assert len(list(settings.default_path().parent.iterdir())) == 1, "a backup was made"
        assert "cannot be used" in page.commands.banner.text()
        where = focused(dialog)
        assert where is page.tabs.tabBar(), f"the keyboard went to {where!r}, not the tabs"


def test_without_a_project_the_reserved_arguments_are_explained(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        page.tabs.setCurrentWidget(page.project_tab)
        assert reserved_text(window) == NO_PROJECT
        assert page.reserved_note.isHidden(), "the note about a project's file shows"
        assert page.reserved.isVisible()


def test_the_open_projects_reserved_arguments_are_shown_as_saved(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, tmp_path: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        opened(qtbot, window, tmp_path, ARGUMENTS)
        page = open_advanced(qtbot, window)
        assert page.tabs.currentWidget() is page.commands, "the page did not start at its choice"
        page.tabs.setCurrentWidget(page.project_tab)
        assert page.tabs.tabText(1) == "This &project" and page.tabs.tabText(0) == "This co&mputer"
        assert reserved_text(window) == command_text(ARGUMENTS)
        assert page.reserved_note.isVisible() and page.reserved_note.text() == RESERVED_NOTE
        title = page.findChild(QWidget, "reservedTitle")
        assert title is not None and title.isVisible()


def test_every_opening_shows_the_current_projects_arguments(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, tmp_path: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        open_advanced(qtbot, window)
        assert reserved_text(window) == NO_PROJECT
        settings_dialog(window).close()
        opened(qtbot, window, tmp_path, ())
        window.settings_window.open("Advanced")
        assert reserved_text(window) == NONE_SAVED, "the opening did not show the new project"
        settings_dialog(window).close()
        opened(qtbot, window, tmp_path / "second", ("--x",))
        window.settings_window.open()  # at the last page shown
        assert reserved_text(window) == command_text(("--x",))


def test_tab_goes_from_the_list_to_the_tabs_the_choice_then_close(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        dialog = settings_dialog(window)
        pages, close = window.settings_window.pages, window.settings_window.close
        assert pages is not None and close is not None
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
        pages.setFocus()
        QTest.keyClick(pages, Qt.Key.Key_Tab)
        assert focused(dialog) is page.tabs.tabBar(), f"Tab went to {focused(dialog)!r}"
        QTest.keyClick(page.tabs.tabBar(), Qt.Key.Key_Tab)
        assert focused(dialog) is page.commands.combo, f"Tab went to {focused(dialog)!r}"
        QTest.keyClick(page.commands.combo, Qt.Key.Key_Tab)
        assert focused(dialog) is close, f"Tab went to {focused(dialog)!r}, not Close"
