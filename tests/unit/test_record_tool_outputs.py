"""P2-T04d: operation capture scrubs only ABMatt's volatile text."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import record_tool_help as rth
import record_tool_outputs as rto
import tool_catalogue as tc
from version_fakes import fake_executable


def test_abmatt_recordings_cover_conversion_and_command_failures() -> None:
    records = rto.load("abmatt", "1.3.2")
    cases = {str(row["case"]): row for row in records}
    assert {
        "convert dae",
        "convert obj map",
        "convert existing without overwrite",
        "convert valid existing without overwrite",
        "convert without wimgt",
        "command file",
        "command file missing",
        "info",
        "bad command file",
        "unknown option",
        "copy material",
    } <= cases.keys()
    assert any(row["files"] for row in records)
    assert all(
        "<duration>" in str(row["stdout"]) or "finished in" not in str(row["stdout"])
        for row in records
    )
    assert all(
        "[<pid>]" in str(row["stderr"])
        or "Failed to execute script __main__" not in str(row["stderr"])
        for row in records
    )


def test_abmatt_recorder_verifies_rszst_pin_and_actual_version(
    fake_tools_path, tmp_path: Path
) -> None:
    installed = tmp_path / "installed.json"
    pin = tc.ALL_TOOLS["riistudio"].version
    installed.write_text(json.dumps({"riistudio": {"version": pin}}), encoding="utf-8")
    rto.verify_abmatt_source(installed, fake_tools_path.resolve("rszst"))
    with pytest.raises(rth.RecordError, match=r"rszst .*expected"):
        rto.verify_abmatt_source(installed, fake_tools_path.resolve("abmatt"))
    installed.write_text(json.dumps({"riistudio": {"version": "5.11.3"}}), encoding="utf-8")
    with pytest.raises(rth.RecordError, match=r"5\.11\.3.*pinned"):
        rto.verify_abmatt_source(installed, fake_tools_path.resolve("rszst"))


@pytest.mark.parametrize(
    "setup",
    [
        (("rszst", "import-brres", "missing.dae", "source.brres"),),
        (("@dae",), ("rszst", "import-brres", "course.dae", "sub/source.brres")),
    ],
)
def test_failed_or_missing_setup_output_cannot_be_recorded(
    setup: tuple[tuple[str, ...], ...], fake_tools_path, tmp_path: Path
) -> None:
    inputs = rth.RECORDINGS / "rszst" / "5.11.5" / "inputs"
    case = rto.Case("broken setup", ("abmatt",), setup)
    with pytest.raises(rth.RecordError, match=r"setup.*rszst"):
        rto.prepare(
            case, tmp_path, fake_tools_path.resolve, lambda name: (inputs / name).read_bytes()
        )


def test_nonzero_setup_exit_is_rejected_even_without_an_output_contract(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "bin")
    work = tmp_path / "work"
    work.mkdir()
    case = rto.Case("failed setup", ("abmatt",), (("rszst", "-c", "import sys; sys.exit(1)"),))
    with pytest.raises(rth.RecordError, match=r"setup rszst exited 1"):
        rto.prepare(case, work, lambda _tool: exe, lambda _name: b"")


def test_blender_scrubs_only_elapsed_time() -> None:
    record: dict[str, object] = {
        "stdout": '00:00.625  reports          | ERROR Cannot read file "<work>/bad.blend"\n'
        '00:01.123  blend            | Read blend: "<work>/good.blend"\n'
        "Blender 5.2.2 LTS (hash xyz built 2026-09-15 01:37:04)\n",
        "stderr": "Traceback: boom at 00:00.321\n",
    }
    clean = rto.normalize_blender(record)
    stdout = str(record["stdout"])
    assert clean["stdout"] == stdout.replace("00:00.625", "<elapsed>").replace(
        "00:01.123", "<elapsed>"
    )
    assert clean["stderr"] == record["stderr"]
    assert stdout.startswith("00:00.625")


def test_blender_recording_covers_python_and_file_states() -> None:
    rows = rto.load("blender", "5.2.2")
    assert {str(row["case"]) for row in rows} == {case.name for case in rto.BLENDER_CASES}
    assert {
        "script args",
        "script exception exit 7",
        "script exits 3",
        "valid blend",
        "missing blend",
        "junk blend",
        "unknown option",
        "bpy only in real Blender",
    } <= {str(row["case"]) for row in rows}
    assert all("00:00." not in str(row["stdout"]) for row in rows)
    assert any(row["files"] for row in rows)


def test_blender_recorded_input_digest_matches_entire_retained_file() -> None:
    inputs = rth.RECORDINGS / "blender" / "5.2.2" / "inputs"
    rows = rto.load("blender", "5.2.2")
    verified = 0
    for row in rows:
        for name, metadata in cast(dict[str, dict[str, object]], row["inputs"]).items():
            assert metadata["sha256"] == hashlib.sha256((inputs / name).read_bytes()).hexdigest()
            verified += 1
    assert verified >= 10


def test_run_case_tracks_full_digest_of_used_inputs(fake_tools_path, tmp_path: Path) -> None:
    inputs = rth.RECORDINGS / "blender" / "5.2.2" / "inputs"
    case = next(case for case in rto.BLENDER_CASES if case.name == "script writes")
    record = rto.run_case(
        case, fake_tools_path.resolve, tmp_path, lambda name: (inputs / name).read_bytes()
    )
    metadata = cast(dict[str, dict[str, object]], record["inputs"])["write.py"]
    assert metadata["sha256"] == hashlib.sha256((inputs / "write.py").read_bytes()).hexdigest()


def test_blender_recorder_refuses_wrong_or_missing_pinned_build(
    fake_tools_path, tmp_path: Path
) -> None:
    installed = tmp_path / "installed.json"
    pin = tc.ALL_TOOLS["blender"].version
    installed.write_text(json.dumps({"blender": {"version": pin}}), encoding="utf-8")
    rto.verify_blender_source(installed, fake_tools_path.resolve("blender"))
    with pytest.raises(rth.RecordError, match=r"blender version mismatch"):
        rto.verify_blender_source(installed, fake_tools_path.resolve("abmatt"))
    installed.write_text(json.dumps({"blender": {"version": "0.1.0"}}), encoding="utf-8")
    with pytest.raises(rth.RecordError, match=r"0\.1\.0.*pinned"):
        rto.verify_blender_source(installed, fake_tools_path.resolve("blender"))


def test_abmatt_scrubs_duration_and_frozen_process_id() -> None:
    record: dict[str, object] = {
        "stdout": "\t... finished in 1.04 secs\nWrote file '<work>/map.brres'\n",
        "stderr": "Traceback (most recent call last):\n[12345] Failed to execute script __main__\n",
    }
    clean = rto.normalize_abmatt(record)
    assert clean["stdout"] == "\t... finished in <duration> secs\nWrote file '<work>/map.brres'\n"
    assert (
        clean["stderr"]
        == "Traceback (most recent call last):\n[<pid>] Failed to execute script __main__\n"
    )
    assert record["stdout"] != clean["stdout"], "keep the original evidence intact"
