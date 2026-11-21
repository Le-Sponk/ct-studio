"""P5-T07f2: an editor added in Settings → Editors… is offered by the next Open in… without a
restart, and the own-editor controls work from the keyboard. Real preparation, synthetic
editor files."""

from __future__ import annotations

from pathlib import Path

import pytest
from custom_editor_helpers import add, answer_remove, listed, select, tool_dialog
from editor_preparation_helpers import Finder, file_at
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
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

from ctstudio.gui.editor_launch import EditorLaunchService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def test_the_next_open_in_offers_an_added_editor(qtbot: QtBot, tmp_path: Path) -> None:
    tools = tmp_path / "tools é"
    tools.mkdir()
    brawlcrate = str(file_at(tools, "brawlcrate.exe"))
    mine = file_at(tools, "my paint é.exe")
    write_settings({"format": 1, "tools": {"brawlcrate": brawlcrate}})
    real = EditorLaunchService(settings_file(), discover_tool=Finder(tools))
    with project_window(qtbot, tmp_path / "board", real) as window:
        assert open_in_rows(qtbot, window)[0] == "BrawlCrate"
        assert not any("Paint" in text for text in open_in_rows(qtbot, window))
        window.editors_action.trigger()
        page = editors_page(window)
        assert settled(qtbot, lambda: not page.busy), "the first read never ended"
        add(qtbot, page, "Paint é", str(mine), "{file}")
        dialog = window.editors_window.dialog
        assert dialog is not None
        dialog.reject()
        rows = open_in_rows(qtbot, window)
        assert rows[0] == "BrawlCrate" and rows[-1] == "Paint é", f"not offered: {rows}"
        window.editors_action.trigger()
        assert settled(qtbot, lambda: not page.busy)
        select(page, f"Paint é ({mine})")
        answer_remove(qtbot, page, yes=True)
        dialog.reject()
        assert not any("Paint" in text for text in open_in_rows(qtbot, window)), "still offered"


def _tab(times: int) -> list[QWidget]:
    """Press Tab ``times`` times; return the widgets that got the focus, in order."""
    reached: list[QWidget] = []
    for _ in range(times):
        focus = QApplication.focusWidget()
        assert focus is not None
        QTest.keyClick(focus, Qt.Key.Key_Tab)
        now = QApplication.focusWidget()
        if now is not None and now not in reached:
            reached.append(now)
    return reached


def test_own_editors_work_from_the_keyboard(qtbot: QtBot) -> None:
    write_settings({"format": 1})
    with editors_window(qtbot) as (window, page):
        dialog = window.editors_window.dialog
        assert dialog is not None
        dialog.activateWindow()
        QApplication.processEvents()
        page.combos[".kmp"].setFocus()
        reached = _tab(4)
        assert reached[:2] == [page.own, page.add_button], f"Tab order: {reached}"
        page.add_button.setFocus()
        QTest.keyClick(page.add_button, Qt.Key.Key_Space)
        entry = tool_dialog(qtbot, page)
        QApplication.processEvents()
        assert entry.name.hasFocus(), "the name field does not start with the focus"
        QTest.keyClicks(entry.name, "Keys")
        QTest.keyClick(entry.name, Qt.Key.Key_Tab)
        assert entry.program.hasFocus(), "Tab does not reach the program"
        QTest.keyClicks(entry.program, "C:/k.exe")
        QTest.keyClick(entry.program, Qt.Key.Key_Tab)
        assert entry.browse.hasFocus(), "Tab does not reach Browse…"
        QTest.keyClick(entry.browse, Qt.Key.Key_Tab)
        assert entry.arguments.hasFocus(), "Tab does not reach the arguments"
        QTest.keyClick(entry.arguments, Qt.Key.Key_Tab)
        assert not entry.arguments.hasFocus(), "Tab stays in the arguments"
        QTest.keyClick(entry.name, Qt.Key.Key_Return)
        assert settled(qtbot, lambda: page.tool_dialog is None), "Enter did not save"
        assert settled(qtbot, lambda: not page.busy)
        assert listed(page) == [f"Keys ({Path('C:/k.exe')})"]
        page.own.setFocus()
        QTest.keyClick(page.own, Qt.Key.Key_Down)
        assert page.selected_tool() == "custom-keys", "arrow keys do not select"
        QTest.keyClick(page.own, Qt.Key.Key_Return)
        entry = tool_dialog(qtbot, page)
        assert entry.windowTitle() == "Edit editor" and entry.name.text() == "Keys"
        QTest.keyClick(entry.name, Qt.Key.Key_Escape)
        assert settled(qtbot, lambda: page.tool_dialog is None), "Escape did not cancel"
        assert dialog.isVisible(), "Escape in the entry closed the Editors window too"
