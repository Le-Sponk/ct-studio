"""Linux and Windows operation recordings agree apart from listed differences (P2-T08b).

Both recordings run the same cases on the same synthetic fixtures. Every exit code, file
effect and input must match exactly. Printed text may differ only in the ways listed in
``DIFFERENCES``; anything else fails, so a new Linux-only behaviour cannot hide in a
fake that replays the Windows recording.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings"
TOOLS = ("wszst", "wkclt", "wkmpt", "wimgt", "blender")
EXACT = ("exit_code", "files", "inputs")
TEXT = ("argv", "stdout", "stderr")

Rule = Callable[[str], str]


def _slashes_in_work_paths(text: str) -> str:
    return re.sub(r"<work>[^\s\"']*", lambda m: m.group(0).replace("\\", "/"), text)


def _wiimm_build_name(text: str) -> str:
    return re.sub(r" (?:cygwin64|x86_64) - Dirk Clemens ", " <build> - Dirk Clemens ", text)


def _blender_build_time(text: str) -> str:
    return re.sub(r"(built \d{4}-\d\d-\d\d) \d\d:\d\d:\d\d", r"\1 <time>", text)


def _getopt_wording(text: str) -> str:
    # Cygwin getopt: "wszst: unknown option -- bogus-flag"; glibc prints argv[0] in full
    # and "unrecognized option '--bogus-flag'" or "invalid option -- 'Z'".
    text = re.sub(r"<tools>/wiimms-szs-tools/bin/(\w+):", r"\1:", text)
    text = re.sub(r"unrecognized option '--([\w-]+)'", r"unknown option -- \1", text)
    return re.sub(r"invalid option -- '(\w)'", r"unknown option -- \1", text)


def _autoadd_default_folder(text: str) -> str:
    # Windows builds look in Cygwin's /usr/bin; Linux beside the tools (share/szs).
    return text.replace("<tools>/wiimms-szs-tools/share/szs/auto-add", "/usr/bin/auto-add")


DIFFERENCES: dict[str, tuple[str, Rule]] = {
    "slashes": ("Windows writes work paths with backslashes", _slashes_in_work_paths),
    "wiimm-build": ("version line names the build: cygwin64 or x86_64", _wiimm_build_name),
    "blender-time": ("each Blender download was built at a different minute", _blender_build_time),
    "getopt": ("Cygwin and glibc word bad-option errors differently", _getopt_wording),
    "autoadd": ("default auto-add folder differs per build", _autoadd_default_folder),
}


def normalise(value: object) -> object:
    if isinstance(value, list):
        return [normalise(item) for item in value]
    if not isinstance(value, str):
        return value
    for _reason, rule in DIFFERENCES.values():
        value = rule(value)
    return value


def _load(tool: str, system: str) -> dict[str, dict[str, object]]:
    (folder,) = (RECORDINGS / tool).iterdir()  # one pinned version per tool
    records = json.loads((folder / f"{system}-ops.json").read_text(encoding="utf-8"))
    return {record["case"]: record for record in records}


@pytest.mark.parametrize("tool", TOOLS)
def test_linux_recording_covers_every_windows_case(tool: str) -> None:
    assert sorted(_load(tool, "linux")) == sorted(_load(tool, "windows"))


def mismatches(windows: dict[str, object], linux: dict[str, object]) -> list[str]:
    """Keys where one case's runs differ beyond ``DIFFERENCES``."""
    exact = [key for key in EXACT if linux.get(key) != windows.get(key)]
    text = [key for key in TEXT if normalise(linux.get(key)) != normalise(windows.get(key))]
    return exact + text


def disagreements(
    windows: dict[str, dict[str, object]], linux: dict[str, dict[str, object]]
) -> dict[str, list[str]]:
    """Cases whose Linux run differs beyond ``DIFFERENCES``, with the differing keys."""
    found = {case: mismatches(record, linux[case]) for case, record in windows.items()}
    return {case: keys for case, keys in found.items() if keys}


@pytest.mark.parametrize("tool", TOOLS)
def test_linux_and_windows_runs_agree_apart_from_listed_differences(tool: str) -> None:
    assert disagreements(_load(tool, "windows"), _load(tool, "linux")) == {}


def test_a_changed_linux_run_is_reported() -> None:
    windows = _load("wszst", "windows")
    linux = {**windows, "autoadd status": {**windows["autoadd status"], "exit_code": 9}}
    assert disagreements(windows, dict(windows)) == {}
    assert disagreements(windows, linux) == {"autoadd status": ["exit_code"]}


@pytest.mark.parametrize("key", ["exit_code", "files", "inputs", "argv", "stdout", "stderr"])
def test_a_difference_in_any_recorded_part_is_reported(key: str) -> None:
    base: dict[str, object] = {
        "argv": ["a"],
        "exit_code": 0,
        "stdout": "o",
        "stderr": "e",
        "files": {"a": 1},
        "inputs": {"b": 2},
    }
    assert mismatches(base, dict(base)) == []
    assert mismatches(base, {**base, key: "changed"}) == [key]


def test_no_runner_folder_leaks_into_linux_recordings() -> None:
    for path in RECORDINGS.glob("*/*/linux-*.json"):
        text = path.read_text(encoding="utf-8")
        assert "/home/runner" not in text, path
        assert "/tmp/" not in text, path  # noqa: S108 - a check, not a temp file


@pytest.mark.parametrize(
    ("windows", "linux"),
    [
        ('"<work>\\sub\\t.szs"', '"<work>/sub/t.szs"'),
        (
            "wszst: Wiimms SZS Tool v2.42a r8989 cygwin64 - Dirk Clemens - 2024-03-26",
            "wszst: Wiimms SZS Tool v2.42a r8989 x86_64 - Dirk Clemens - 2024-03-26",
        ),
        ("(hash d13f built 2026-09-15 01:37:04)", "(hash d13f built 2026-09-15 01:34:58)"),
        (
            "wszst: unknown option -- bogus-flag",
            "<tools>/wiimms-szs-tools/bin/wszst: unrecognized option '--bogus-flag'",
        ),
        ("wszst: unknown option -- Z", "<tools>/wiimms-szs-tools/bin/wszst: invalid option -- 'Z'"),
        ("PATH: /usr/bin/auto-add", "PATH: <tools>/wiimms-szs-tools/share/szs/auto-add"),
    ],
)
def test_each_listed_difference_is_allowed(windows: str, linux: str) -> None:
    assert normalise(linux) == normalise(windows)


@pytest.mark.parametrize(
    ("windows", "linux"),
    [
        ("exit 0", "exit 1"),
        ('"<work>\\a.szs"', '"<work>/b.szs"'),
        (
            "wszst: Wiimms SZS Tool v2.42a r8989 cygwin64 - Dirk Clemens - 2024-03-26",
            "wszst: Wiimms SZS Tool v2.43a r8989 x86_64 - Dirk Clemens - 2024-03-26",
        ),
        ("r8989 cygwin64 - Dirk Clemens - 2024-03-26", "r8989 i686 - Dirk Clemens - 2024-03-26"),
        ("(hash d13f built 2026-09-15 01:37:04)", "(hash e000 built 2026-09-15 01:34:58)"),
        ("(built 2026-09-15 01:37:04)", "(built 2026-09-16 01:37:04)"),
        ("(built 2026-09-15 01:37:04)", "(built 2026-09-15 later)"),
        ("wszst: unknown option -- bogus-flag", "wszst: unknown option -- other-flag"),
        ("PATH: /usr/bin/auto-add", "PATH: <tools>/elsewhere/auto-add"),
    ],
)
def test_other_differences_still_fail(windows: str, linux: str) -> None:
    assert normalise(linux) != normalise(windows)
