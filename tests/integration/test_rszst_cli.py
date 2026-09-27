"""rszst CLI discovery contract, per platform; conversion correctness belongs to S3b.

Linux: the S3a source build. Windows: the official Alpha 5.11.5 release zip (P0-T13).
Each platform has its own recording, because the two differ in exactly two ways that
an adapter must not paper over: the exit status (the CLI calls exit(-1), which Linux
truncates to 255 and Windows reports as 0xFFFFFFFF) and the program name in `Usage:`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp

BINARY = tp.RSZST
PLATFORM = "windows" if os.name == "nt" else "linux"
EXIT_MINUS_ONE = tp.EXIT_MINUS_ONE
pytestmark = [pytest.mark.integration, pytest.mark.timeout(30)]
needs_rszst = pytest.mark.skipif(
    not BINARY.is_file(), reason="no rszst: S3a recipe (Linux) or --only riistudio (Windows)"
)


RECORDINGS = ROOT / "tests" / "fakes" / "recordings" / "rszst" / "5.11.5"
RECORDING = RECORDINGS / f"{PLATFORM}-cli.json"
CASES = json.loads(RECORDING.read_text(encoding="utf-8"))


def contract(stdout: str) -> str:
    """The help text before the build banner (timestamp/compiler vary per build)."""
    return stdout.split("\n\nRiiStudio CLI")[0]


def test_platforms_differ_only_in_exit_status_and_program_name() -> None:
    """Runs anywhere: pins the cross-platform difference the adapter must encode."""
    linux = json.loads((RECORDINGS / "linux-cli.json").read_text(encoding="utf-8"))
    windows = json.loads((RECORDINGS / "windows-cli.json").read_text(encoding="utf-8"))
    assert [c["argv"] for c in linux] == [c["argv"] for c in windows]
    assert {c["exit_code"] for c in linux} == {255}
    assert {c["exit_code"] for c in windows} == {0xFFFFFFFF}
    for lin, win in zip(linux, windows, strict=True):
        assert contract(win["stdout"]) == contract(lin["stdout"]).replace(
            "Usage: rszst ", "Usage: rszst.exe "
        ), lin["argv"]


@needs_rszst
@pytest.mark.parametrize("case", CASES, ids=[" ".join(c["argv"]) for c in CASES])
def test_cli_discovery_matches_recording(case: dict, tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    working = tmp_path / "CLI probe é"
    working.mkdir()
    result = subprocess.run(  # noqa: S603 - pinned local executable, argv only.
        [str(BINARY), *case["argv"]],
        cwd=working,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    # Successful help and invalid arguments share this exit status on both platforms.
    assert result.returncode == case["exit_code"] == EXIT_MINUS_ONE
    assert result.stderr == case["stderr"] == ""
    assert "RiiStudio CLI Alpha 5.11.5" in result.stdout
    assert contract(result.stdout) == contract(case["stdout"])


@needs_rszst
def test_probe_preserves_existing_recording(tmp_path: Path) -> None:
    destination = tmp_path / "recording é.json"
    argv = [
        sys.executable,
        str(ROOT / "spikes" / "s3_rszst_probe.py"),
        "--output",
        str(destination),
    ]
    first = subprocess.run(  # noqa: S603 - local probe, argv only.
        argv, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False
    )
    assert first.returncode == 0, first.stderr
    original = destination.read_bytes()
    records = json.loads(original)
    assert [r["argv"] for r in records] == [r["argv"] for r in CASES]
    assert all(r["exit_code"] == EXIT_MINUS_ONE for r in records)
    second = subprocess.run(  # noqa: S603 - repeat must refuse overwrite.
        argv, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False
    )
    assert second.returncode != 0
    assert "FileExistsError" in second.stderr
    assert destination.read_bytes() == original
