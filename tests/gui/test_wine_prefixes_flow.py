"""P5-T07f3: a Wine prefix chosen in Settings → Editors… is used by the next Open in… on Linux
(fake platform: real preparation, synthetic Windows programs and prefix folders, nothing
started), and the Wine tab works from the keyboard."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from editor_preparation_helpers import Finder, file_at, linux, pe_at
from editor_request_helpers import settled
from editor_settings_helpers import (
    editors_page,
    editors_window,
    open_in_rows,
    project_window,
    settings_file,
    write_settings,
)
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from wine_prefix_helpers import choose_folder, clear_prefix, folder_dialog, pick, show_wine

from ctstudio.gui.editor_launch import EditorLaunchService
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def _prefix(root: Path) -> Path:
    prefix = root / "wine prefix é"
    prefix.mkdir()
    (prefix / "system.reg").write_text("#arch=win64", encoding="utf8")
    return prefix


def _linux_service(tools: Path) -> EditorLaunchService:
    finder = Finder(tools)
    finder.environment = replace(finder.environment, platform="linux")
    return EditorLaunchService(settings_file(), discover_tool=finder, current_platform=linux)


def _wine_tab(qtbot: QtBot, window: MainWindow) -> None:
    window.editors_action.trigger()
    page = editors_page(window)
    assert settled(qtbot, lambda: not page.busy), "the read never ended"
    show_wine(page)


def _close_editors(window: MainWindow) -> None:
    dialog = window.editors_window.dialog
    assert dialog is not None
    dialog.reject()


@pytest.mark.parametrize("own", [False, True], ids=["built-in", "own"])
def test_the_next_open_in_on_linux_uses_the_chosen_prefix(
    qtbot: QtBot, tmp_path: Path, own: bool
) -> None:
    tools = tmp_path / "tools é"
    tools.mkdir()
    program = pe_at(tools, "program é.exe")
    wine = file_at(tools, "wine")
    prefix = _prefix(tmp_path)
    data: dict[str, object] = {"format": 1, "tools": {"wine": str(wine)}}
    if own:
        data["custom_tools"] = {
            "custom-paint": {"name": "Paint", "exe": str(program), "args_template": ["{file}"]}
        }
    else:
        data["tools"] = {"wine": str(wine), "brawlcrate": str(program)}
    write_settings(data)
    name = "Paint" if own else "BrawlCrate"
    with project_window(qtbot, tmp_path / "board", _linux_service(tools)) as window:
        assert f"{name} (not found)" in open_in_rows(qtbot, window), "ready without a prefix"
        _wine_tab(qtbot, window)
        page = editors_page(window)
        choose_folder(qtbot, page, name, prefix)
        _close_editors(window)
        rows = open_in_rows(qtbot, window)
        assert name in rows, f"the chosen prefix was not used: {rows}"
        _wine_tab(qtbot, window)
        clear_prefix(qtbot, page, name)
        _close_editors(window)
        assert f"{name} (not found)" in open_in_rows(qtbot, window), "a cleared prefix is used"


def test_the_wine_tab_works_from_the_keyboard(qtbot: QtBot, tmp_path: Path) -> None:
    write_settings({"format": 1})
    with editors_window(qtbot) as (window, page):
        dialog = window.editors_window.dialog
        assert dialog is not None
        dialog.activateWindow()
        QApplication.processEvents()
        page.tabs.tabBar().setFocus()
        for _ in range(2):
            QTest.keyClick(page.tabs.tabBar(), Qt.Key.Key_Right)
        assert page.tabs.currentWidget() is page.wine, "arrow keys do not reach the Wine tab"
        QTest.keyClick(page.tabs.tabBar(), Qt.Key.Key_Tab)
        assert page.wine.rows.hasFocus(), "Tab does not reach the editor rows"
        QTest.keyClick(page.wine.rows, Qt.Key.Key_End)
        QTest.keyClick(page.wine.rows, Qt.Key.Key_Home)
        assert page.wine.selected() == "brawlcrate", "Home and End do not select a row"
        QTest.keyClick(page.wine.rows, Qt.Key.Key_Tab)
        assert page.wine.choose_button.hasFocus(), "Tab does not reach Choose folder…"
        page.wine.rows.setFocus()  # Enter on the focused button closes the window (TD-021)
        QTest.keyClick(page.wine.rows, Qt.Key.Key_Return)
        chooser = folder_dialog(qtbot, page)
        assert dialog.isVisible(), "Enter on a row closed the Editors window"
        QTest.keyClick(chooser, Qt.Key.Key_Escape)
        assert settled(qtbot, lambda: page.wine.folder_dialog is None), "Escape kept it open"
        assert dialog.isVisible(), "Escape in the folder dialog closed the Editors window"
        assert settings_file().read_bytes() == b'{"format": 1}', "Escape saved something"
        page.wine.rows.setFocus()
        QTest.keyClick(page.wine.rows, Qt.Key.Key_Return)
        pick(folder_dialog(qtbot, page), tmp_path)
        assert settled(qtbot, lambda: not page.busy), "the save never ended"
        assert dialog.focusWidget() is page.wine.rows, "the focus left the rows after a save"
