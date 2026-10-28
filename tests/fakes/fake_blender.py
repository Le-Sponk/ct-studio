"""Pinned Blender 5.2.2 headless stand-in; replays Windows observations only.

The fake runs exact recorded scripts under the test interpreter (not bpy). It refuses
unknown scripts, .blend bytes and argv before execution, so unsupported work cannot
silently succeed. Linux output translation does not certify real Linux Blender.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from fake_runtime import Outcome, Unmodelled, finish, recordings

VERSION = "5.2.2"
INPUTS = Path(__file__).resolve().parent / "recordings" / "blender" / VERSION / "inputs"
ROWS: list[dict[str, Any]] = recordings("blender", VERSION, "ops")
HELP: list[dict[str, Any]] = recordings("blender", VERSION, "help")
BANNER = str(ROWS[0]["stdout"]).split("\n\nBlender quit\n")[0] + "\n"
NEWLINE = "\r\n" if os.name == "nt" else "\n"


def _verified_inputs(row: dict[str, Any]) -> dict[str, bytes] | None:
    """Read once and retain the exact bytes that may be executed as Python."""
    verified: dict[str, bytes] = {}
    for name, metadata in row["inputs"].items():
        source, reference = Path(name), INPUTS / name
        if not source.is_file() or not reference.is_file():
            return None
        data = source.read_bytes()
        if data != reference.read_bytes() or hashlib.sha256(data).hexdigest() != metadata["sha256"]:
            return None
        verified[name] = data
    return verified


def _file_state(name: str) -> bool:
    if name == "script writes":
        return not Path("result.txt").exists()
    if name == "junk blend":
        return _exact(Path("junk.blend"), b"not a track file\n" * 4)
    missing = {
        "missing blend": "missing.blend",
        "missing script": "missing.py",
        "missing script exit 7": "missing.py",
        "unknown option": "--bogus-flag",
    }
    return name not in missing or not Path(missing[name]).exists()


def _state(row: dict[str, Any]) -> dict[str, bytes] | None:
    verified = _verified_inputs(row)
    if verified is None or not _file_state(str(row["case"])):
        return None
    return verified


def _exact(path: Path, data: bytes) -> bool:
    return path.is_file() and path.read_bytes() == data


def _argv_matches(row: dict[str, Any], argv: list[str]) -> bool:
    expected = [
        str(arg)
        .replace("<work>\\", str(Path.cwd()) + os.sep)
        .replace("<work>/", str(Path.cwd()) + os.sep)
        for arg in row["argv"]
    ]
    return expected == argv


def _substitute(text: str) -> str:
    return text.replace("<work>\\", str(Path.cwd()) + os.sep).replace(
        "<work>/", str(Path.cwd()) + os.sep
    )


def _script_path(argv: list[str]) -> Path | None:
    if "--python" not in argv:
        return None
    name = argv[argv.index("--python") + 1]
    return Path(name).absolute()


def _execute_script(
    path: Path, argv: list[str], source: bytes
) -> tuple[str, str, int | None, bool]:
    """Execute the verified bytes, including their actual file writes and sys.exit."""
    stdout, stderr = io.StringIO(), io.StringIO()
    previous = sys.argv
    sys.argv = ["blender", *argv]
    code: int | None = None
    failed = False
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                exec(  # noqa: S102 - execute only byte-verified test scripts, as Blender does
                    compile(source, str(path), "exec"),
                    {"__name__": "__main__", "__file__": str(path)},
                )
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
            except Exception as exc:
                failed = True
                frames = [
                    frame
                    for frame in traceback.extract_tb(exc.__traceback__)
                    if frame.filename == str(path)
                ]
                stderr.write("Traceback (most recent call last):\n")
                stderr.write("".join(traceback.format_list(frames)))
                stderr.write("".join(traceback.format_exception_only(type(exc), exc)))
    finally:
        sys.argv = previous
    return stdout.getvalue(), stderr.getvalue(), code, failed


def _script_outcome(row: dict[str, Any], argv: list[str], path: Path, source: bytes) -> Outcome:
    printed, errors, code, failed = _execute_script(path, argv, source)
    exit_on_error = failed and "--python-exit-code" in argv
    if exit_on_error:
        errors += f"\nError: script failed, file: '{path.name}', exiting.\n"
    exit_code = (
        code
        if code is not None
        else int(argv[argv.index("--python-exit-code") + 1])
        if exit_on_error
        else 0
    )
    prefix = (
        _substitute(str(row["stdout"]).partition("ARGS ")[0])
        if row["case"] == "valid blend"
        else ""
    )
    stdout = prefix + printed + BANNER + ("" if code is not None else "\nBlender quit\n")
    return Outcome(exit_code=exit_code, stdout=stdout, stderr=errors, newline=NEWLINE)


def _outcome(row: dict[str, Any], argv: list[str], verified: dict[str, bytes]) -> Outcome:
    name = str(row["case"])
    path = _script_path(argv)
    if path is None or name in {
        "missing blend",
        "junk blend",
        "unknown option",
        "missing script",
        "missing script exit 7",
    }:
        return Outcome(
            exit_code=int(row["exit_code"]),
            stdout=_substitute(str(row["stdout"])),
            stderr=_substitute(str(row["stderr"])),
            newline=NEWLINE,
        )
    if path.name not in verified:
        raise Unmodelled("recorded script was not verified")
    return _script_outcome(row, argv, path, verified[path.name])


def _run(argv: list[str]) -> Outcome:
    for row in HELP:
        if row["argv"] == argv:
            return Outcome(
                exit_code=int(row["exit_code"]),
                stdout=str(row["stdout"]),
                stderr=str(row["stderr"]),
                newline=NEWLINE,
            )
    for row in ROWS:
        if _argv_matches(row, argv):
            verified = _state(row)
            if verified is not None:
                return _outcome(row, argv, verified)
    raise Unmodelled(f"argv or input state not recorded: {argv}")


def main(argv: list[str]) -> int:
    return finish("blender", argv, lambda: _run(argv))
