"""``ctstudio doctor`` against the real tools on this machine (P2-T06).

Uses the developer copies in ``.tools/`` (``scripts/bootstrap_tools.py``). Every bootstrapped
CLI tool with a verified version command must be found and report its pinned version through
a real probe; the command must exit 0 and print valid JSON. Skips without ``.tools``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ctstudio.core.tools.doctor import diagnose
from ctstudio.core.tools.versions import VersionCache

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / ".tools"
EXE = ".exe" if sys.platform == "win32" else ""
PINNED = {"wszst": "2.42a", "wkclt": "2.42a", "wkmpt": "2.42a", "wimgt": "2.42a"}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(180),
    pytest.mark.skipif(
        not (TOOLS / "wiimms-szs-tools" / "bin" / f"wszst{EXE}").is_file(),
        reason="needs the bootstrapped Wiimm tools in .tools/",
    ),
]


def test_real_tools_are_found_with_their_pinned_versions(tmp_path: Path) -> None:
    report = diagnose(cache=VersionCache(tmp_path / "versions.json"), force=True)
    checks = {check.tool_id: check for check in report.tools}
    for tool, version in PINNED.items():
        assert (checks[tool].status, checks[tool].version) == ("found", version), checks[tool]
    if (TOOLS / "riistudio" / f"rszst{EXE}").is_file():
        assert checks["rszst"].version == "5.11.5"
    if (TOOLS / "blender" / f"blender{EXE}").is_file():
        assert checks["blender"].status == "found" and checks["blender"].version
    assert report.ok


def test_the_command_exits_0_with_json(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(  # our own interpreter and entry point
        [sys.executable, "-m", "ctstudio", "doctor", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=150,
        env=env,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert {tool["id"]: tool["status"] for tool in data["tools"]}["wszst"] == "found"
