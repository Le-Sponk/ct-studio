"""P5-T07g: every original default Open in… target, through the real preparation.

With no saved choice, each kind of file is offered its built-in editors in the original
order (P5-T07: brres → BrawlCrate, RiiStudio; kmp → Lorenzi, KMP Cloud; szs → BrawlCrate,
RiiStudio; blend → Blender), and the user's own editors after them for any file, also one
with no built-in editor. Folders go to the system file manager (tests/unit/test_folders.py).
"Offered" means listed: no built-in editor is installed here, so each is listed as missing
(availability is tested in test_editor_preparation.py); the own editor's program exists.
"""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from editor_preparation_helpers import Finder, file_at, no_side_effects, project_at, tree

from ctstudio.core.project import settings
from ctstudio.core.tools.spec import CustomTool
from ctstudio.gui.editor_launch import EditorLaunchService

__all__ = ["no_side_effects"]

BRRES = [("brawlcrate", "BrawlCrate"), ("riistudio", "RiiStudio")]
DEFAULTS = {
    "course.brres": BRRES,
    "course.szs": BRRES,
    "course.kmp": [("kmp_editor_lorenzi", "Lorenzi's KMP Editor"), ("kmp_cloud", "KMP Cloud")],
    "course.blend": [("blender", "Blender")],
    "course.kcl": [],  # no built-in editor: only the user's own editors
}


def _prepare(
    tmp_path: Path, name: str, saved: Mapping[str, object] | None
) -> list[tuple[str, str, str]]:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, name)
    if name == "course.kmp":
        file_at(project.root, "course.kcl")  # Lorenzi's prerequisite
    path = tmp_path / "settings.json"
    if saved is not None:
        path.write_text(json.dumps({"format": 1, "tools": {}, **saved}), encoding="utf-8")
    before = tree(tmp_path)
    prepared = EditorLaunchService(path, discover_tool=Finder(tmp_path)).prepare(project, doc)
    assert tree(tmp_path) == before, "preparing the choices changed a file"
    return [
        (f"{o.choice.namespace}:{o.choice.tool_id}", o.label, o.state) for o in prepared.options
    ]


def _builtin(pairs: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    return [(f"builtin:{tool}", label, "missing") for tool, label in pairs]


@pytest.mark.parametrize("name", list(DEFAULTS))
def test_each_kind_offers_its_default_editors_in_order(tmp_path: Path, name: str) -> None:
    assert _prepare(tmp_path, name, None) == _builtin(DEFAULTS[name])


@pytest.mark.parametrize("name", list(DEFAULTS))
def test_own_editors_follow_the_defaults_for_any_file(tmp_path: Path, name: str) -> None:
    exe = file_at(tmp_path, "my editor")
    own = settings.UserSettings().with_custom_tool("custom-own", CustomTool("Mine", exe, []))
    offered = _prepare(tmp_path, name, own.other)
    assert offered == [*_builtin(DEFAULTS[name]), ("custom:custom-own", "Mine", "available")]
