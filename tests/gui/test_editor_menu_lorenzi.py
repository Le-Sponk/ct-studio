"""P5-T07e1: real preparation never offers Lorenzi's editor without an exact course.kcl."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from editor_menu_helpers import menu_board, offered, row_texts
from editor_preparation_helpers import Finder, file_at
from editor_request_helpers import settled
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from ctstudio.gui.editor_launch import EditorLaunchService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
LORENZI = "Lorenzi's KMP Editor"


@pytest.mark.parametrize("collision", ["absent", "COURSE.KCL", "course.kcl"])
def test_lorenzi_is_offered_only_beside_an_exact_course_kcl(
    qtbot: QtBot, tmp_path: Path, collision: str
) -> None:
    exe = file_at(tmp_path, f"{LORENZI}.exe")
    settings_path = tmp_path / "settings.json"
    tools = {"kmp_editor_lorenzi": str(exe)}
    settings_path.write_text(json.dumps({"format": 1, "tools": tools}), encoding="utf-8")
    real = EditorLaunchService(settings_path, discover_tool=Finder(tmp_path))
    with menu_board(qtbot, tmp_path / "board", real) as (page, services, project, _held, _m):
        files = project.root / "files"
        files.mkdir(exist_ok=True)
        file_at(files, "course.kmp")
        if collision != "absent":
            file_at(files, collision)
        kmp = replace(project.manifest.components.kmp, file="files/course.kmp")
        components = replace(project.manifest.components, kmp=kmp)
        project.manifest = replace(project.manifest, components=components)
        page.set_project(project, changed=True)
        card = page.cards["kmp"]
        assert settled(qtbot, card.can_open), "the KMP card never became openable"
        card.open_action.trigger()
        dialog = offered(qtbot, page)
        rows = row_texts(dialog)
        exact = collision == "course.kcl"
        expected = LORENZI if exact else f"{LORENZI} (cannot open this file)"
        assert rows[0] == expected, f"{collision}: {rows}"
        enabled = bool(dialog.choices.item(0).flags() & Qt.ItemFlag.ItemIsEnabled)
        assert enabled == exact, f"{collision}: Lorenzi enabled={enabled}"
        if not exact:
            assert "course.kcl" in dialog.choices.item(0).toolTip()
        dialog.reject()
        assert settled(qtbot, lambda: not services.launch.busy)
