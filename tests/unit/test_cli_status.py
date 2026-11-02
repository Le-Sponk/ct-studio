"""P3-T07: ``ctstudio status`` text and JSON (``ctstudio.cli.status``), in-process.

The table is pinned by an exact snapshot built from fixed statuses, so a wording or layout
change is a deliberate test edit. The end-to-end runs against the fake tools are in
``test_cli_project.py``.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from ctstudio.__main__ import main
from ctstudio.cli import status as cli_status
from ctstudio.cli.status import JSON_FORMAT, exit_code, render, to_json
from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.components.status import STATE_LABELS, ComponentStatus, State
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.project.project import Project

pytestmark = pytest.mark.timeout(60)

ROOT = Path("C:/Tracks/Sponk é")
MANIFEST = Manifest(project=ProjectInfo(name="Sponk Raceway", slot="farm_course"))
_MODEL = "track.blend changed since course_model.brres was made"
_NO_BLENDER = "needs Blender, which was not found (see the Tools page)"
_EDITED = "posteffect/posteffect.bblm was changed outside CT Studio"
STATUSES = {
    "course_model": ComponentStatus(State.STALE, (_MODEL,)),
    "kcl": ComponentStatus(State.READY),
    "minimap": ComponentStatus(State.MISSING, ("map_model.brres has not been made yet",)),
    "skybox": ComponentStatus(
        State.ERROR, ("vrcorn_model.brres has not been made yet", _NO_BLENDER)
    ),
    "kmp": ComponentStatus(State.MANUAL, ("using files/course.kmp",)),
    "posteffect": ComponentStatus(State.EDITED_EXTERNALLY, (_EDITED,)),
    "objects": ComponentStatus(State.READY, ("added automatically while the track is assembled",)),
    "track_info": ComponentStatus(State.WARNING, ("no author set",)),
}

SNAPSHOT = """\
Sponk Raceway, replacing Moo Moo Meadows (Mushroom Cup, track 2)
Folder: C:/Tracks/Sponk é

      Part          Status
----  ------------  ------------------------
[~]   Course model  out of date
        track.blend changed since course_model.brres was made
[ok]  Collision     ready
[ ]   Minimap       missing
        map_model.brres has not been made yet
[x]   Skybox        problem
        vrcorn_model.brres has not been made yet
        needs Blender, which was not found (see the Tools page)
[ok]  Course data   your own file
        using files/course.kmp
[*]   Post-effects  edited outside CT Studio
        posteffect/posteffect.bblm was changed outside CT Studio
[ok]  Objects       ready
        added automatically while the track is assembled
[!]   Track info    warning
        no author set

3 of 8 parts are ready. Fix the parts marked [x] before building: Skybox.
"""


def test_the_table_matches_the_snapshot() -> None:
    assert render(ROOT, MANIFEST, STATUSES) == SNAPSHOT


def test_with_no_problem_the_verdict_says_nothing_blocks_a_build() -> None:
    fine = {**STATUSES, "skybox": ComponentStatus(State.MISSING, ("not made yet",))}
    last = render(ROOT, MANIFEST, fine).splitlines()[-1]
    assert last == "3 of 8 parts are ready. Nothing listed here stops a build."


def test_an_arena_slot_is_named_as_an_arena() -> None:
    arena = Manifest(project=ProjectInfo(name="Box", slot="block_battle"))
    first = render(ROOT, arena, STATUSES).splitlines()[0]
    assert first == "Box, replacing Block Plaza (Wii Arenas, arena 1)"


def test_every_state_has_an_icon_and_a_plain_label() -> None:
    assert set(cli_status.ICONS) == set(State) == set(STATE_LABELS)
    assert len(set(cli_status.ICONS.values())) == len(State) - 1, "only ready/manual share [ok]"
    assert cli_status.ICONS[State.READY] == cli_status.ICONS[State.MANUAL] == "[ok]"
    assert all(label and label[0].islower() for label in STATE_LABELS.values())


def test_json_lists_every_part_in_dashboard_order() -> None:
    data = to_json(ROOT, MANIFEST, STATUSES)
    assert data["format"] == JSON_FORMAT == 1
    assert data["ok"] is False
    assert data["project"] == {
        "name": "Sponk Raceway",
        "folder": "C:/Tracks/Sponk é",
        "slot": "farm_course",
        "slot_name": "Moo Moo Meadows",
    }
    parts = data["parts"]
    assert [p["id"] for p in parts] == [spec.id for spec in COMPONENTS]
    assert parts[3] == {
        "id": "skybox",
        "name": "Skybox",
        "state": "error",
        "label": "problem",
        "reasons": [
            "vrcorn_model.brres has not been made yet",
            "needs Blender, which was not found (see the Tools page)",
        ],
    }
    assert parts[1]["reasons"] == []
    json.dumps(data)  # plain data only


@pytest.mark.parametrize(
    ("state", "code"),
    [(State.ERROR, 1), *((s, 0) for s in State if s is not State.ERROR)],
)
def test_only_a_problem_part_fails_the_command(state: State, code: int) -> None:
    statuses = dict.fromkeys(STATUSES, ComponentStatus(State.READY))
    statuses["kcl"] = ComponentStatus(state, ("why",))
    assert exit_code(statuses) == code
    assert to_json(ROOT, MANIFEST, statuses)["ok"] is (code == 0)


# --- the subcommand, in-process -------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail at once, instead of opening a window, if a subcommand falls through to the GUI."""
    fake = types.ModuleType("ctstudio.gui.app")

    def run_gui(*_args: object) -> int:
        raise AssertionError("the GUI was started")

    fake.run_gui = run_gui  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ctstudio.gui.app", fake)


@pytest.fixture(autouse=True)
def settings_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    from ctstudio.core.project import settings

    path = tmp_path / "config é" / "settings.json"
    monkeypatch.setattr(settings, "default_path", lambda: path)
    return path


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """``available_tools`` answers every tool; each call's arguments are recorded."""
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> frozenset[str]:
        calls.append(kwargs)
        return frozenset({"wszst", "wkclt", "wimgt", "rszst", "abmatt", "blender"})

    monkeypatch.setattr(cli_status, "available_tools", fake)
    return calls


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "Sponk é"
    (root / "files").mkdir(parents=True)
    (root / "files" / "track.blend").write_bytes(b"BLENDER-v300REND")
    Project.create(root, "Sponk", blend=root / "files" / "track.blend", force=True).close()
    return root


def test_status_prints_the_table_and_exits_0_with_nothing_blocking(
    tmp_path: Path, tools: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path)
    assert main(["status", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Sponk, replacing Luigi Circuit (Mushroom Cup, track 1)\n")
    assert "[ ]   Course model  missing" in out
    assert tools == [{"configured": {}}]


def test_status_defaults_to_the_current_folder(
    tmp_path: Path,
    tools: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(_project(tmp_path))
    assert main(["status", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["project"]["folder"] == (tmp_path / "Sponk é").resolve().as_posix()


def test_missing_tools_make_parts_a_problem_and_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path)
    monkeypatch.setattr(cli_status, "available_tools", lambda **_k: frozenset[str]())
    assert main(["status", str(root), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    model = data["parts"][0]
    assert model["state"] == "error"
    assert "needs Blender, which was not found (see the Tools page)" in model["reasons"]


def test_paths_set_in_ct_studio_are_used(
    tmp_path: Path, tools: list[dict[str, object]], settings_file: Path
) -> None:
    from ctstudio.core.project import settings

    chosen = tmp_path / "my blender.exe"
    settings.save(settings.UserSettings({"blender": str(chosen)}))
    assert main(["status", str(_project(tmp_path)), "--json"]) == 0
    assert tools == [{"configured": {"blender": chosen}}]


def test_damaged_settings_are_reported_and_ignored(
    tmp_path: Path,
    tools: list[dict[str, object]],
    settings_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text("{ not json", encoding="utf-8")
    assert main(["status", str(_project(tmp_path))]) == 0
    err = capsys.readouterr().err
    assert err.startswith("Warning: ") and "ignored for this check" in err
    assert tools == [{"configured": {}}]


def test_a_folder_without_a_project_is_an_error(
    tmp_path: Path, tools: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["status", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "There is no ctstudio.toml in" in captured.err
    assert tools == [], "no tool search for a folder that is not a project"


def test_status_never_takes_or_creates_the_lock(
    tmp_path: Path, tools: list[dict[str, object]]
) -> None:
    root = _project(tmp_path)
    lock = root / ".ctstudio" / "lock"
    assert not lock.exists()
    assert main(["status", str(root), "--json"]) == 0
    assert not lock.exists()
