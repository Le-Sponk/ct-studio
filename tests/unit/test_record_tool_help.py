"""P2-T04a: the help recorder runs pinned tools through the core runner and sanitises output."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from version_fakes import fake_executable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import record_tool_help as rth

pytestmark = pytest.mark.timeout(20)


def test_record_keeps_every_line_and_normalises_newlines_and_paths(tmp_path: Path) -> None:
    tools = tmp_path / "tools é"
    exe = fake_executable(tools / "bin")
    code = (
        "import sys\n"
        "for i in range(120):\n"
        "    sys.stdout.buffer.write(f'line {i}\\r\\n'.encode())\n"
        "sys.stdout.buffer.write(('seen in ' + sys.argv[1] + '\\n').encode())\n"
        "sys.stderr.buffer.write(b'warn\\r\\n')\n"
        "sys.exit(3)\n"
    )
    [record] = rth.record(exe, [("-c", code, str(exe.parent))], tools_root=exe.parent)
    assert record["argv"] == ["-c", code, "<tool-dir>"], "absolute paths are not recorded"
    assert record["exit_code"] == 3
    lines = record["stdout"].split("\n")
    assert lines[0] == "line 0" and lines[119] == "line 119", "no 50-line tail truncation"
    assert lines[120] == "seen in <tool-dir>"
    assert record["stdout"].endswith("\n") and "\r" not in record["stdout"]
    assert record["stderr"] == "warn\n"


def test_an_unpinned_installed_version_is_refused(tmp_path: Path) -> None:
    installed = tmp_path / "installed.json"
    installed.write_text(json.dumps({"abmatt": {"version": "1.3.1"}}), encoding="utf-8")
    with pytest.raises(rth.RecordError, match=r"abmatt 1\.3\.1 is installed but 1\.3\.2"):
        rth.pinned_version("abmatt", installed)
    installed.write_text("{}", encoding="utf-8")
    with pytest.raises(rth.RecordError, match="not installed"):
        rth.pinned_version("abmatt", installed)


def test_the_plan_covers_every_wiimm_command_the_contract_needs() -> None:
    plan = {name: argvs for name, _tool, _exe, argvs in rth.PLAN}
    assert set(plan) == {"wszst", "wkclt", "wkmpt", "wimgt", "abmatt", "blender"}
    assert ("help", "create") in plan["wszst"] and ("version",) in plan["wszst"]
    assert ("--help",) in plan["abmatt"] and ("--help",) in plan["blender"]
