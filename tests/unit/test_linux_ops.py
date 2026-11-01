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
TOOLS = ("wszst", "wkclt", "wkmpt", "wimgt", "blender", "rszst", "abmatt")
EXACT = ("files", "inputs")
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


def _windows_backslashes(text: str) -> str:
    # ABMatt prints ".\\course.dae" and frozen-module traceback paths ("brres\\brres.py",
    # "src\\lxml\\parser.pxi") with backslashes; a repr'd "<work>\\\\sub" path has already
    # become "<work>//sub" through the "slashes" rule above.
    text = re.sub(r"<work>[^\s\"']*", lambda m: m.group(0).replace("//", "/"), text)
    text = re.sub(r'File "([^"]*)"', lambda m: f'File "{m.group(1).replace(chr(92), "/")}"', text)
    return re.sub(r"(?<![\w.])\.\\", "./", text)


def _traceback_line_numbers(text: str) -> str:
    # The Linux ABMatt 1.3.2 build's command.py/load_config.py sit 2-4 lines off the
    # Windows build's; the frames (file and function) are the same.
    return re.sub(r'(File "[^"]*", line )\d+', r"\1<n>", text)


def _pyinstaller_wording(text: str) -> str:
    # PyInstaller's bootloader on Windows: "Failed to execute script __main__"; the Linux
    # build's newer one: "Failed to execute script '__main__' due to unhandled exception!".
    return text.replace(
        "Failed to execute script '__main__' due to unhandled exception!",
        "Failed to execute script __main__",
    )


def _rszst_progress_order(text: str) -> str:
    # rszst optimises meshes on worker threads: its "\r"-redrawn "(n / 4)" progress bars
    # print in completion order, which varies run to run.
    bars = re.compile(r"(?:Optimizing meshes \(\d+ / \d+\)[^\r\n]*\r)+")
    return bars.sub(
        lambda m: "".join(f"{bar}\r" for bar in sorted(m.group(0).split("\r")[:-1])), text
    )


def _abmatt_function_name(text: str) -> str:
    # The Linux ABMatt 1.3.2 build calls convert_lib's helper _try_import_textures.
    return text.replace(", in _try_import_textures", ", in try_import_textures")


DIFFERENCES: dict[str, tuple[str, Rule]] = {
    "slashes": ("Windows writes work paths with backslashes", _slashes_in_work_paths),
    "wiimm-build": ("version line names the build: cygwin64 or x86_64", _wiimm_build_name),
    "blender-time": ("each Blender download was built at a different minute", _blender_build_time),
    "getopt": ("Cygwin and glibc word bad-option errors differently", _getopt_wording),
    "autoadd": ("default auto-add folder differs per build", _autoadd_default_folder),
    "backslashes": ("ABMatt prints Windows paths with backslashes", _windows_backslashes),
    "traceback-lines": ("ABMatt's Linux build has shifted source lines", _traceback_line_numbers),
    "pyinstaller": ("ABMatt's builds use different PyInstaller wording", _pyinstaller_wording),
    "progress-order": ("rszst mesh progress prints in thread order", _rszst_progress_order),
    "abmatt-helper": ("one ABMatt helper is private in the Linux build", _abmatt_function_name),
}

WINDOWS_MINUS_ONE = 4294967295  # exit(-1) as Windows reports it


def same_exit(windows: object, linux: object, linux_stderr: str) -> bool:
    """Exit codes match, apart from two measured ways the systems report a failure.

    * ``exit(-1)``: Windows shows 4294967295, Linux 255 (rszst, ``abmatt info``).
    * A frozen-Python crash: Windows' PyInstaller exits -1, Linux's exits 1 (ABMatt).
    Either way the run failed on both, which is all the adapters read (non-zero = failed).
    """
    if windows == linux:
        return True
    if windows != WINDOWS_MINUS_ONE:
        return False
    crashed = "Failed to execute script '__main__' due to unhandled exception!" in linux_stderr
    return linux == 255 or (linux == 1 and crashed)


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


def test_every_tool_with_a_linux_ops_recording_is_compared() -> None:
    recorded = {path.parts[-3] for path in RECORDINGS.glob("*/*/linux-ops.json")}
    assert recorded == set(TOOLS)


@pytest.mark.parametrize("tool", TOOLS)
def test_linux_recording_covers_every_windows_case(tool: str) -> None:
    assert sorted(_load(tool, "linux")) == sorted(_load(tool, "windows"))


def mismatches(windows: dict[str, object], linux: dict[str, object]) -> list[str]:
    """Keys where one case's runs differ beyond ``DIFFERENCES``."""
    stderr = str(linux.get("stderr", ""))
    code = (
        [] if same_exit(windows.get("exit_code"), linux.get("exit_code"), stderr) else ["exit_code"]
    )
    exact = [key for key in EXACT if linux.get(key) != windows.get(key)]
    text = [key for key in TEXT if normalise(linux.get(key)) != normalise(windows.get(key))]
    return code + exact + text


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
        ("Converting .\\course.dae... ", "Converting ./course.dae... "),
        ('  File "brres\\lib\\binfile.py", line 9', '  File "brres/lib/binfile.py", line 9'),
        ("such file: '<work>\\\\sub\\\\c.brres'", "such file: '<work>/sub/c.brres'"),
        ('  File "command.py", line 713, in run', '  File "command.py", line 711, in run'),
        (
            "[<pid>] Failed to execute script __main__",
            "[<pid>] Failed to execute script '__main__' due to unhandled exception!",
        ),
        (
            "Optimizing meshes (2 / 4) 50 %\rOptimizing meshes (1 / 4) 25 %\rDone\r",
            "Optimizing meshes (1 / 4) 25 %\rOptimizing meshes (2 / 4) 50 %\rDone\r",
        ),
        ("line 82, in try_import_textures", "line 82, in _try_import_textures"),
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
        ("Converting .\\course.dae... ", "Converting ./other.dae... "),
        ('  File "brres\\brres.py", line 9', '  File "brres/other.py", line 9'),
        ('  File "command.py", line 713, in run', '  File "command.py", line 711, in walk'),
        ("Failed to execute script __main__", "Failed to execute script 'other'"),
        (
            "Optimizing meshes (2 / 4) 50 %\rDone\r",
            "Optimizing meshes (2 / 4) 50 %\rOptimizing meshes (2 / 4) 50 %\rDone\r",
        ),
        (
            "Optimizing meshes (1 / 4) 25 %\rCompiling\rOptimizing meshes (2 / 4) 50 %\r",
            "Optimizing meshes (2 / 4) 50 %\rCompiling\rOptimizing meshes (1 / 4) 25 %\r",
        ),
        ("in try_import_textures", "in _try_import_other"),
    ],
)
def test_other_differences_still_fail(windows: str, linux: str) -> None:
    assert normalise(linux) != normalise(windows)


@pytest.mark.parametrize(
    ("windows", "linux", "stderr", "same"),
    [
        (0, 0, "", True),
        (4294967295, 255, "", True),  # exit(-1)
        (
            4294967295,
            1,
            "[<pid>] Failed to execute script '__main__' due to unhandled exception!",
            True,
        ),
        (4294967295, 1, "an ordinary error", False),  # exit 1 without the crash is a change
        (4294967295, 2, "", False),
        (1, 255, "", False),
        (0, 1, "", False),
        (255, 4294967295, "", False),  # only the Windows-to-Linux direction is measured
    ],
)
def test_exit_codes_match_apart_from_how_each_system_reports_a_failure(
    windows: int, linux: int, stderr: str, same: bool
) -> None:
    assert same_exit(windows, linux, stderr) is same


def test_progress_order_keeps_every_bar_and_separator() -> None:
    text = "A\rOptimizing meshes (2 / 4) b\rOptimizing meshes (1 / 4) a\rZ\r"
    assert normalise(text) == "A\rOptimizing meshes (1 / 4) a\rOptimizing meshes (2 / 4) b\rZ\r"
