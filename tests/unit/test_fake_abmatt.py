"""P2-T04d: replay ABMatt 1.3.2 Windows operations through the real process runner.

Native Linux ABMatt operation output is not recorded. Linux's executable fake replays
sanitised Windows evidence with LF/newline and exit(-1) platform normalization only.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import record_tool_help as rth
import record_tool_outputs as rto
import tool_catalogue as tc
from fake_runtime import UNMODELLED_EXIT
from ops_replay import assert_like_recording, stand_ins

from ctstudio.core.tools.discovery import discover
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.versions import VersionCache, probe_versions

pytestmark = pytest.mark.timeout(60)
VERSION = tc.ALL_TOOLS["abmatt"].version
FOLDER = rth.RECORDINGS / "abmatt" / VERSION
CASES = {case.name: case for case in rto.TOOLSETS["abmatt"][1]}
OS_NAME = "windows" if os.name == "nt" else "linux"


def records() -> list[dict[str, object]]:
    return rto.load("abmatt", VERSION)


def for_this_os(record: dict[str, object]) -> dict[str, object]:
    if os.name == "nt":
        return record
    return {
        **record,
        "exit_code": 255 if record["exit_code"] == 4294967295 else record["exit_code"],
        "stdout": str(record["stdout"]).replace("\r\n", "\n"),
        "stderr": str(record["stderr"]).replace("\r\n", "\n"),
    }


def test_recorded_cases_match_case_table() -> None:
    assert {str(row["case"]) for row in records()} == set(CASES)


@pytest.mark.parametrize("row", records(), ids=lambda row: str(row["case"]))
def test_fake_matches_recorded_run(row: dict[str, object], fake_tools_path, tmp_path: Path) -> None:
    case = CASES[str(row["case"])]
    actual = rto.run_case(
        case, fake_tools_path.resolve, tmp_path, stand_ins(row, FOLDER / "inputs")
    )
    assert_like_recording(actual, for_this_os(row))


def test_help_matches_pinned_recording(fake_tools_path, tmp_path: Path) -> None:
    [row] = json.loads((FOLDER / "windows-help.json").read_text(encoding="utf-8"))
    actual = rth.capture(fake_tools_path.resolve("abmatt"), row["argv"], cwd=tmp_path, roots={})
    assert (actual["exit_code"], actual["stdout"], actual["stderr"]) == (
        row["exit_code"],
        row["stdout"],
        row["stderr"],
    )


def test_discovery_finds_fake_but_version_probe_remains_unverified(
    fake_tools_path, tmp_path: Path
) -> None:
    spec = TOOL_BY_ID["abmatt"]
    location = discover(spec)
    assert location is not None
    assert location.path.samefile(fake_tools_path.resolve("abmatt"))
    [result] = probe_versions([(spec, location)], cache=VersionCache(tmp_path / "versions.json"))
    assert result.outcome == "unprobed"  # P2-T02b does not have a verified ABMatt version command.
    assert result.location.version is None


@pytest.mark.parametrize(
    "change", ["source", "commands", "destination", "missing_parent", "copy_dest"]
)
def test_unrecorded_operation_state_is_refused(
    change: str, fake_tools_path, tmp_path: Path
) -> None:
    name = {
        "source": "command file",
        "commands": "command file",
        "destination": "convert existing overwrite",
        "missing_parent": "convert no folder",
        "copy_dest": "copy material",
    }[change]
    case = CASES[name]
    row = next(item for item in records() if item["case"] == name)
    rto.prepare(case, tmp_path, fake_tools_path.resolve, stand_ins(row, FOLDER / "inputs"))
    if change == "source":
        target = tmp_path / "source.brres"
        target.write_bytes(target.read_bytes() + b"TAMPER")
    elif change == "commands":
        target = tmp_path / "set.txt"
        target.write_bytes(target.read_bytes() + b"set material xlu:false for road\n")
    elif change == "destination":
        (tmp_path / "course_model.brres").write_bytes(b"bres\nUNRECOGNISED\n")
    elif change == "copy_dest":
        target = tmp_path / "dest.brres"
        target.write_bytes(target.read_bytes() + b"TAMPER")
    else:
        (tmp_path / "sub").mkdir()

    def output_files() -> dict[str, str]:
        return {
            name: digest
            for name, digest in rto.snapshot(tmp_path).items()
            if not name.startswith("fake-calls/")
        }

    previous = output_files()
    actual = rth.capture(fake_tools_path.resolve("abmatt"), case.argv[1:], cwd=tmp_path, roots={})
    assert actual["exit_code"] == UNMODELLED_EXIT
    assert output_files() == previous, "refusal cannot write"


def test_without_wimgt_brres_cannot_masquerade_as_textured(fake_tools_path, tmp_path: Path) -> None:
    archives: dict[str, bytes] = {}
    for name in ("convert dae", "convert without wimgt"):
        work = tmp_path / name
        work.mkdir()
        row = next(item for item in records() if item["case"] == name)
        rto.prepare(CASES[name], work, fake_tools_path.resolve, stand_ins(row, FOLDER / "inputs"))
        env = {**os.environ, "PATH": ""} if name == "convert without wimgt" else None
        result = rth.capture(
            fake_tools_path.resolve("abmatt"), CASES[name].argv[1:], cwd=work, roots={}, env=env
        )
        assert result["exit_code"] == 0
        archives[name] = (work / "course_model.brres").read_bytes()
        downstream = rth.capture(
            fake_tools_path.resolve("rszst"),
            ["brres-to-json", "course_model.brres", "out.json"],
            cwd=work,
            roots={},
        )
        assert downstream["exit_code"] == UNMODELLED_EXIT
        assert not (work / "out.json").exists()
    assert archives["convert dae"] != archives["convert without wimgt"]
    assert b"NO-TEXTURES" in archives["convert without wimgt"]
    assert b"NO-TEXTURES" not in archives["convert dae"]


@pytest.mark.parametrize(
    "name", ["adapter convert missing texture", "adapter convert textures folder"]
)
def test_texture_loss_runs_write_the_no_textures_stand_in(
    name: str, fake_tools_path, tmp_path: Path
) -> None:
    row = next(item for item in records() if item["case"] == name)
    rto.prepare(CASES[name], tmp_path, fake_tools_path.resolve, stand_ins(row, FOLDER / "inputs"))
    result = rth.capture(
        fake_tools_path.resolve("abmatt"), CASES[name].argv[1:], cwd=tmp_path, roots={}
    )
    assert result["exit_code"] == 0
    assert b"NO-TEXTURES" in (tmp_path / "out.brres").read_bytes()


def test_a_partly_moved_texture_layout_is_unrecorded(fake_tools_path, tmp_path: Path) -> None:
    """Recorded: all four textures in textures/. One left beside the DAE was never run."""
    name = "adapter convert textures folder"
    row = next(item for item in records() if item["case"] == name)
    rto.prepare(CASES[name], tmp_path, fake_tools_path.resolve, stand_ins(row, FOLDER / "inputs"))
    shutil.copyfile(tmp_path / "textures" / "road.png", tmp_path / "road.png")
    result = rth.capture(
        fake_tools_path.resolve("abmatt"), CASES[name].argv[1:], cwd=tmp_path, roots={}
    )
    assert result["exit_code"] == UNMODELLED_EXIT
    assert not (tmp_path / "out.brres").exists()


def test_fake_raw_help_line_endings_are_platform_appropriate(
    fake_tools_path, tmp_path: Path
) -> None:
    import subprocess

    raw = subprocess.run(  # noqa: S603 - executable installed by the test fixture
        [str(fake_tools_path.resolve("abmatt")), "--help"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    line_end = b"\r\n" if os.name == "nt" else b"\n"
    assert raw.stdout.count(b"\n") == raw.stdout.count(line_end)
    assert raw.stdout.endswith(line_end)


@pytest.mark.parametrize("change", ["dae", "texture", "obj", "argv"])
def test_unrecorded_imports_and_flags_are_refused(
    change: str, fake_tools_path, tmp_path: Path
) -> None:
    inputs = FOLDER / "inputs"
    for name in ("course.dae", *rto.DAE_TEXTURES, "map.obj"):
        data = (inputs / name).read_bytes()
        (tmp_path / name).write_bytes(
            data + b"X"
            if name == {"dae": "course.dae", "texture": "water.png", "obj": "map.obj"}.get(change)
            else data
        )
    args = (
        ["convert", "map.obj", "to", "map_model.brres", "-o"]
        if change == "obj"
        else ["convert", "course.dae", "to", "course_model.brres", "-o"]
    )
    if change == "argv":
        args.append("--moonview")
    actual = rth.capture(fake_tools_path.resolve("abmatt"), args, cwd=tmp_path, roots={})
    assert actual["exit_code"] == UNMODELLED_EXIT
    assert "not modelled" in str(actual["stderr"])
    assert actual["stdout"] == ""
    assert not (tmp_path / "course_model.brres").exists()
    assert not (tmp_path / "map_model.brres").exists()
