"""P5-T07f1: a choice made in Settings → Editors… reaches the next Open in… without a restart,
and the window stays usable from the keyboard. Real preparation, synthetic editor files."""

from __future__ import annotations

from pathlib import Path

import pytest
from editor_preparation_helpers import Finder, file_at
from editor_request_helpers import settled
from editor_settings_helpers import (
    choose,
    combo,
    editors_page,
    editors_window,
    open_in_rows,
    project_window,
    settings_file,
    write_settings,
)
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox
from pytestqt.qtbot import QtBot

from ctstudio.gui.editor_launch import EditorLaunchService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def test_the_next_open_in_lists_the_chosen_editor_first(qtbot: QtBot, tmp_path: Path) -> None:
    tools = tmp_path / "tools é"
    tools.mkdir()
    paths = {name: str(file_at(tools, f"{name}.exe")) for name in ("brawlcrate", "riistudio")}
    write_settings({"format": 1, "tools": paths, "kept": True})
    real = EditorLaunchService(settings_file(), discover_tool=Finder(tools))
    with project_window(qtbot, tmp_path / "board", real) as window:
        assert open_in_rows(qtbot, window) == ["BrawlCrate", "RiiStudio"]
        window.editors_action.trigger()
        page = editors_page(window)
        assert settled(qtbot, lambda: not page.busy), "the first read never ended"
        choose(qtbot, page, ".brres", "RiiStudio")
        dialog = window.editors_window.dialog
        assert dialog is not None
        dialog.reject()
        assert open_in_rows(qtbot, window) == ["RiiStudio", "BrawlCrate"], "not used next time"
        window.editors_action.trigger()
        assert settled(qtbot, lambda: not page.busy)
        choose(qtbot, page, ".brres", "Default order (BrawlCrate first)")
        dialog.reject()
        assert open_in_rows(qtbot, window) == ["BrawlCrate", "RiiStudio"], "reset not used"


def test_the_choices_work_from_the_keyboard(qtbot: QtBot) -> None:
    with editors_window(qtbot) as (window, page):
        dialog = window.editors_window.dialog
        assert dialog is not None
        dialog.activateWindow()
        QApplication.processEvents()
        first = combo(page, ".brres")
        first.setFocus()
        assert first.hasFocus(), "could not focus the first choice"
        reached: list[QComboBox] = [first]
        for _ in range(6):
            focus = QApplication.focusWidget()
            assert focus is not None
            QTest.keyClick(focus, Qt.Key.Key_Tab)
            now = QApplication.focusWidget()
            if isinstance(now, QComboBox) and now not in reached:
                reached.append(now)
        assert reached == [combo(page, kind) for kind in (".brres", ".szs", ".kmp")], "Tab order"
        kmp = combo(page, ".kmp")
        kmp.setFocus()
        assert kmp.hasFocus()
        QTest.keyClick(kmp, Qt.Key.Key_Down)
        assert settled(qtbot, lambda: not page.busy), "the keyboard pick never saved"
        assert kmp.currentText() == "Lorenzi's KMP Editor"
        assert "Lorenzi's KMP Editor first" in page.note.text(), page.note.text()
        focus = QApplication.focusWidget()
        assert focus is not None
        QTest.keyClick(focus, Qt.Key.Key_Escape)
        assert not dialog.isVisible(), "Escape did not close the window"
