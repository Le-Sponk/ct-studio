"""P2-T04d: operation capture scrubs only ABMatt's volatile text."""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
