"""P2-T04e: Windows Blender 5.2.2 observations via the executable fake and runner.

Linux replays only the translated Windows fake contract, not real Linux Blender output.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import record_tool_help as rth
import record_tool_outputs as rto
from fake_runtime import UNMODELLED_EXIT
from ops_replay import assert_like_recording, stand_ins

from ctstudio.core.tools.discovery import discover
from ctstudio.core.tools.registry import TOOL_BY_ID

VERSION = "5.2.2"
FOLDER = rth.RECORDINGS / "blender" / VERSION
CASES = {case.name: case for case in rto.BLENDER_CASES}
pytestmark = pytest.mark.timeout(60)


def rows() -> list[dict[str, object]]:
    return rto.load("blender", VERSION)


def for_this_os(row: dict[str, object]) -> dict[str, object]:
    if os.name == "nt":
        return row
    return {
        **row,
        "argv": [str(arg).replace("<work>\\", "<work>/") for arg in cast(list[str], row["argv"])],
        "stdout": str(row["stdout"]).replace("<work>\\", "<work>/"),
        "stderr": str(row["stderr"]).replace("<work>\\", "<work>/"),
    }


def test_recording_cases_match_table() -> None:
    assert {str(row["case"]) for row in rows()} == set(CASES)


@pytest.mark.parametrize("row", rows(), ids=lambda row: str(row["case"]))
def test_fake_matches_real_windows_operation(
    row: dict[str, object], fake_tools_path, tmp_path: Path
) -> None:
    case = CASES[str(row["case"])]
    result = rto.run_case(
        case, fake_tools_path.resolve, tmp_path, stand_ins(row, FOLDER / "inputs")
    )
    expected = for_this_os(row)
    if row["compare"] == "bpy_missing":
        assert result["exit_code"] == (7 if "exit 7" in case.name else 0)
        assert "ModuleNotFoundError: No module named 'bpy'" in str(result["stderr"])
        assert result["files"] == {}
        assert "bpy: bpy" not in str(result["stdout"])
        assert str(result["stdout"]).endswith("Blender quit\n")
    else:
        assert_like_recording(result, expected)
    if case.name == "script writes":
        assert result["files"] == {"result.txt": {"effect": "created", "magic": "67656e65"}}


@pytest.mark.parametrize("argv", [["--version"], ["--help"]])
def test_help_and_version_match_recorded_pinned_build(
    argv: list[str], fake_tools_path, tmp_path: Path
) -> None:
    recordings = json.loads((FOLDER / "windows-help.json").read_text(encoding="utf-8"))
    expected = next(row for row in recordings if row["argv"] == argv)
    actual = rth.capture(fake_tools_path.resolve("blender"), argv, cwd=tmp_path, roots={})
    assert (actual["exit_code"], actual["stdout"], actual["stderr"]) == (
        expected["exit_code"],
        expected["stdout"],
        expected["stderr"],
    )


def test_discovery_finds_seventh_executable(fake_tools_path) -> None:
    assert len(fake_tools_path.executables) == 7
    spec = TOOL_BY_ID["blender"]
    found = discover(spec)
    assert found is not None
    assert found.path.samefile(fake_tools_path.resolve("blender"))


@pytest.mark.parametrize("change", ["script", "blend", "junk", "missing", "flags", "extra", "path"])
def test_unmeasured_input_or_argv_refused_without_effects(
    change: str, fake_tools_path, tmp_path: Path
) -> None:
    case = CASES[
        "valid blend"
        if change == "blend"
        else "junk blend"
        if change == "junk"
        else "script writes"
    ]
    row = next(item for item in rows() if item["case"] == case.name)
    rto.prepare(case, tmp_path, fake_tools_path.resolve, stand_ins(row, FOLDER / "inputs"))
    argv = rto.expand(case.argv[1:], tmp_path)
    if change == "script":
        (tmp_path / "write.py").write_bytes(b"print('not the same script')\n")
    elif change == "blend":
        p = tmp_path / "good.blend"
        p.write_bytes(p.read_bytes() + b"X")
    elif change == "junk":
        (tmp_path / "junk.blend").write_bytes(b"BLENDER_varying")
    elif change == "missing":
        (tmp_path / "write.py").unlink()
    elif change == "flags":
        argv.append("--bogus")
    elif change == "extra":
        (tmp_path / "unexpected.blend").write_bytes(b"junk")
        argv.insert(2, "unexpected.blend")
    else:
        argv[argv.index("write.py")] = "other.py"

    def output_files() -> dict[str, str]:
        return {
            key: value
            for key, value in rto.snapshot(tmp_path).items()
            if not key.startswith("fake-calls/")
        }

    before = output_files()
    result = rth.capture(fake_tools_path.resolve("blender"), argv, cwd=tmp_path, roots={})
    assert result["exit_code"] == UNMODELLED_EXIT
    assert result["stdout"] == ""
    assert "not modelled" in str(result["stderr"])
    assert output_files() == before
    assert not (tmp_path / "result.txt").exists()


def test_fake_executes_pinned_script_with_test_interpreter(fake_tools_path, tmp_path: Path) -> None:
    case = CASES["script writes"]
    row = next(item for item in rows() if item["case"] == case.name)
    rto.prepare(case, tmp_path, fake_tools_path.resolve, stand_ins(row, FOLDER / "inputs"))
    env = {**os.environ, "CT_STUDIO_BLENDER_TEST_PAYLOAD": "live-check"}
    result = rth.capture(
        fake_tools_path.resolve("blender"), case.argv[1:], cwd=tmp_path, roots={}, env=env
    )
    assert result["exit_code"] == 0
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "live-check\n"


def test_replay_detects_modified_remainder_of_retained_blend(tmp_path: Path) -> None:
    row = next(item for item in rows() if item["case"] == "valid blend")
    kept = tmp_path / "inputs"
    kept.mkdir()
    original = (FOLDER / "inputs" / "good.blend").read_bytes()
    tampered = bytearray(original)
    tampered[2048] ^= 1
    (kept / "good.blend").write_bytes(tampered)
    with pytest.raises(AssertionError, match="digest"):
        stand_ins(row, kept)("good.blend")


def test_fake_compiles_exactly_the_verified_script_bytes(
    fake_tools_path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fake_blender

    case = CASES["script writes"]
    row = next(item for item in rows() if item["case"] == case.name)
    rto.prepare(case, tmp_path, fake_tools_path.resolve, stand_ins(row, FOLDER / "inputs"))
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "write.py"
    original = Path.read_bytes
    reads = 0

    def switched(path: Path) -> bytes:
        nonlocal reads
        if path.resolve() == target:
            reads += 1
            return original(path) if reads == 1 else b"print('wrong script ran')\n"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", switched)
    actual = fake_blender._run(list(case.argv[1:]))
    assert reads == 1, "verified and executed bytes must be one snapshot"
    assert actual.exit_code == 0
    assert actual.stdout.startswith("saved\n")
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "generated\n"


def test_bridge_script_contract_requires_nonzero_python_exit_code(
    fake_tools_path, tmp_path: Path
) -> None:
    row = next(item for item in rows() if item["case"] == "script exception")
    rto.prepare(
        CASES["script exception"],
        tmp_path,
        fake_tools_path.resolve,
        stand_ins(row, FOLDER / "inputs"),
    )
    default = rth.capture(
        fake_tools_path.resolve("blender"),
        CASES["script exception"].argv[1:],
        cwd=tmp_path,
        roots={},
    )
    guarded = rth.capture(
        fake_tools_path.resolve("blender"),
        CASES["script exception exit 7"].argv[1:],
        cwd=tmp_path,
        roots={},
    )
    assert default["exit_code"] == 0 and "RuntimeError: boom" in str(default["stderr"])
    assert guarded["exit_code"] == 7 and "RuntimeError: boom" in str(guarded["stderr"])
    assert "Error: script failed" in str(guarded["stderr"])


def test_bpy_is_not_silently_available_in_test_interpreter(fake_tools_path, tmp_path: Path) -> None:
    assert "bpy" not in sys.modules
    case = CASES["bpy missing exit 7"]
    row = next(item for item in rows() if item["case"] == case.name)
    rto.prepare(case, tmp_path, fake_tools_path.resolve, stand_ins(row, FOLDER / "inputs"))
    result = rth.capture(fake_tools_path.resolve("blender"), case.argv[1:], cwd=tmp_path, roots={})
    assert result["exit_code"] == 7
    assert "ModuleNotFoundError: No module named 'bpy'" in str(result["stderr"])
    assert "bpy: bpy" not in str(result["stdout"])
