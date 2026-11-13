"""Timeout diagnostics retain child output without changing gate selection or limits."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NoReturn

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check

pytestmark = pytest.mark.timeout(15)


def test_real_timeout_retains_flushed_stdout_and_stderr(tmp_path: Path) -> None:
    # Allow interpreter startup; block until the runner kills this child, not a long sleep.
    code = (
        "import sys, threading; "
        "print('partial stdout é', flush=True); "
        "print('partial stderr é', file=sys.stderr, flush=True); "
        "threading.Event().wait()"
    )
    step = check.Step("timeout probe", (sys.executable, "-c", code), 2)
    result = check.run_step(step, tmp_path)
    assert result.status == "FAIL"
    assert "partial stdout é\n" in result.output
    assert "partial stderr é\n" in result.output
    assert result.output.endswith(f"timed out after 2 s: {' '.join(step.argv)}")


def test_real_pytest_timeout_keeps_case_progress_and_thread_trace(tmp_path: Path) -> None:
    (tmp_path / "test_stalled.py").write_text(
        "import threading\ndef test_stalled():\n    threading.Event().wait()\n", encoding="utf-8"
    )
    configured = next(
        step for step in check.build_steps(tmp_path, fast=True) if step.name == "pytest"
    )
    # Accelerate the diagnostic probe, not the gate's unchanged 60/1200-second limits.
    probe = check.Step(configured.name, (*configured.argv, "-o", "faulthandler_timeout=0.5"), 5)
    result = check.run_step(probe, tmp_path)
    assert result.status == "FAIL"
    assert "test_stalled.py::test_stalled" in result.output
    assert "Timeout (0:00:00.500000)!" in result.output
    assert "in test_stalled" in result.output
    assert "timed out after 5 s:" in result.output


@pytest.mark.parametrize(
    ("stdout", "stderr", "partial"),
    [
        (b"stdout \xc3\xa9\xff\n", b"stderr \xfe\n", "stdout é\ufffd\nstderr \ufffd\n"),
        ("stdout é\n", "stderr é\n", "stdout é\nstderr é\n"),
        (None, "stderr only\n", "stderr only\n"),
        ("stdout only", None, "stdout only\n"),
        (None, None, ""),
    ],
    ids=["bytes-invalid-utf8", "text", "missing-stdout", "missing-stderr", "missing-both"],
)
def test_timeout_output_accepts_bytes_text_or_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: bytes | str | None,
    stderr: bytes | str | None,
    partial: str,
) -> None:
    def expire(*args: object, **kwargs: object) -> NoReturn:
        raise subprocess.TimeoutExpired("probe", 2, output=stdout, stderr=stderr)

    monkeypatch.setattr(check.subprocess, "run", expire)
    step = check.Step("timeout probe", ("probe",), 2)
    result = check.run_step(step, tmp_path)
    assert result.status == "FAIL"
    assert result.output == partial + "timed out after 2 s: probe"


@pytest.mark.parametrize("fast", [False, True], ids=["normal", "fast"])
def test_pytest_diagnostics_preserve_selection_and_time_limits(fast: bool) -> None:
    steps = check.build_steps(ROOT, fast=fast)
    pytest_step = next(step for step in steps if step.name == "pytest")
    assert pytest_step.argv[1:4] == ("-q", "-m", check.PYTEST_SELECTION)
    assert pytest_step.argv[4:7] == ("-vv", "-o", "faulthandler_timeout=60")
    assert [step.timeout_s for step in steps] == [120, 120, 600, 300, 1200, 120, 120, 60]
    assert all(not arg.startswith("--debug") for step in steps for arg in step.argv)
    assert all(
        "-vv" not in step.argv and "faulthandler_timeout=60" not in step.argv
        for step in steps
        if step.name != "pytest"
    )
