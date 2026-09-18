"""S3a Linux build smoke test; conversion correctness belongs to S3b."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / ".tools" / "riistudio-build-pinned" / "source" / "cli" / "rszst"
# The optional source-built tool is not installed by the general bootstrap script.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(30),
    pytest.mark.skipif(not BINARY.is_file(), reason="build RiiStudio using SPIKES.md S3a"),
]


RECORDING = ROOT / "tests" / "fakes" / "recordings" / "rszst" / "5.11.5" / "linux-cli.json"
CASES = json.loads(RECORDING.read_text(encoding="utf-8"))


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
    # Successful help and invalid arguments share this exit code on Linux.
    assert result.returncode == case["exit_code"] == 255
    assert result.stderr == case["stderr"] == ""
    assert "RiiStudio CLI Alpha 5.11.5" in result.stdout
    # Build timestamp/compiler are variable; the preceding CLI contract is not.
    assert (
        result.stdout.split("\n\nRiiStudio CLI")[0] == case["stdout"].split("\n\nRiiStudio CLI")[0]
    )


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
    assert all(r["exit_code"] == 255 for r in records)
    second = subprocess.run(  # noqa: S603 - repeat must refuse overwrite.
        argv, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False
    )
    assert second.returncode != 0
    assert "FileExistsError" in second.stderr
    assert destination.read_bytes() == original
