"""Conservative ABMatt 1.3.2 executable stand-in for the recorded operations.

Rows are pinned real Windows runs, never a general BRRES converter. Validate the entire
recorded input state before copying diagnostics and writing distinguishable test markers;
unknown command variants or bytes exit 121 without writes.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import fake_rszst
from fake_runtime import Outcome, Unmodelled, finish, recordings

VERSION = "1.3.2"
FOLDER = Path(__file__).resolve().parent / "recordings" / "abmatt" / VERSION
ROWS: list[dict[str, Any]] = recordings("abmatt", VERSION, "ops")
[HELP] = recordings("abmatt", VERSION, "help")
MARKER = b"bres\nCT-STUDIO-FAKE-ABMATT\n"
NO_TEXTURES_MARKER = b"bres\nCT-STUDIO-FAKE-ABMATT-NO-TEXTURES\n"
COMMANDS = {
    "set.txt": b"set material xlu:true for road\n",
    "bad.txt": b"frobnicate everything\n",
    "copy.txt": (
        b"copy material for road in source.brres\npaste material for road in dest.brres\n"
    ),
}


def _exact(path: Path, data: bytes) -> bool:
    return path.is_file() and path.read_bytes() == data


def _fixtures(row: dict[str, Any]) -> bool:
    for name in row["inputs"]:
        reference = FOLDER / "inputs" / name
        if not _exact(Path(name), reference.read_bytes()):
            return False
    return True


def _wimgt_matches(name: str) -> bool:
    if name in {"usage", "unknown option", "unknown short option", "option missing value"}:
        return True  # getopt runs before ABMatt initialises its image converter
    present = shutil.which("wimgt") is not None
    return not present if name == "convert without wimgt" else present


def _convert_state(name: str, row: dict[str, Any]) -> bool:
    argv: list[str] = row["argv"]
    if "to" not in argv:
        raise Unmodelled("convert without an observed destination")
    destination = Path(argv[argv.index("to") + 1])
    existing = name in {
        "convert existing without overwrite",
        "convert existing overwrite",
        "convert valid existing without overwrite",
        "convert valid existing overwrite",
    }
    expected = MARKER if name.startswith("convert valid existing") else b"SENTINEL"
    if existing and not _exact(destination, expected):
        return False
    if not existing and destination.exists():
        return False
    if (name == "convert no folder") != (not destination.parent.is_dir()):
        return False
    if name in {"convert missing dae", "convert missing obj"}:
        source = "missing.dae" if name.endswith("dae") else "missing.obj"
        return not Path(source).exists()
    return True


def _brres_state(name: str) -> bool:
    if name == "info missing":
        return not Path("missing.brres").exists()
    if not _exact(Path("source.brres"), fake_rszst.FAKE_BRRES):
        return False
    if name == "copy material" and not _exact(Path("dest.brres"), fake_rszst.FAKE_BRRES):
        return False
    commands = {
        "command file": "set.txt",
        "command file without overwrite": "set.txt",
        "bad command file": "bad.txt",
        "copy material": "copy.txt",
    }
    if name in commands:
        command = commands[name]
        return _exact(Path(command), COMMANDS[command])
    return name != "command file missing" or not Path("missing.txt").exists()


def _state(row: dict[str, Any]) -> bool:
    name = str(row["case"])
    if row["compare"] == "unmodelled" or not _fixtures(row) or not _wimgt_matches(name):
        return False
    if name.startswith("convert"):
        return _convert_state(name, row)
    if name.startswith("info") or name in {
        "command file",
        "command file without overwrite",
        "command file missing",
        "bad command file",
        "inline command parsing",
        "copy material",
    }:
        return _brres_state(name)
    return True


def _outcome(row: dict[str, Any]) -> Outcome:
    code = int(row["exit_code"])
    if code == 4294967295:
        code = -1
    output = Outcome(
        exit_code=code,
        stdout=str(row["stdout"]).replace("<work>", str(Path.cwd())),
        stderr=str(row["stderr"]).replace("<work>", str(Path.cwd())),
        newline="\r\n" if os.name == "nt" else "\n",
    )
    marker = NO_TEXTURES_MARKER if row["case"] == "convert without wimgt" else MARKER
    for name, effect in row["files"].items():
        if effect["effect"] not in {"created", "changed"} or effect["magic"] != "62726573":
            raise Unmodelled(f"{name}: output format not modelled")
        output.writes.append((Path(name), marker))
    return output


def _run(argv: list[str]) -> Outcome:
    if argv == ["--help"]:
        return Outcome(
            exit_code=int(HELP["exit_code"]),
            stdout=str(HELP["stdout"]),
            stderr=str(HELP["stderr"]),
            newline="\r\n" if os.name == "nt" else "\n",
        )
    for row in ROWS:
        if row["argv"] == argv and _state(row):
            return _outcome(row)
    raise Unmodelled(f"argv or input state not recorded: {argv}")


def main(argv: list[str]) -> int:
    return finish("abmatt", argv, lambda: _run(argv))
