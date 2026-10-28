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
MAP_MARKER = b"bres\nCT-STUDIO-FAKE-ABMATT-MAP\n"
# Rows whose real output lost textures; the stand-in must never pass for a textured model.
TEXTURE_LOSS = {
    "convert without wimgt",
    "adapter convert missing texture",
    "adapter convert textures folder",
}
# P2-T05e2 adapter rows: ``-c info`` on an archive only from the matching conversion.
INFO_SOURCES = {
    "adapter info": ("out.brres", MARKER),
    "adapter minimap info": ("map_model.brres", MAP_MARKER),
}
# Adapter rows that moved textures out of the DAE's folder: case -> (folder, textures).
MOVED = {
    "adapter convert missing texture": ("unused", ("fence",)),
    "adapter convert textures folder": ("textures", ("road", "grass", "fence", "water")),
}
COMMANDS = {
    "set.txt": b"set material xlu:true for road\n",
    "bad.txt": b"frobnicate everything\n",
    "copy.txt": (
        b"copy material for road in source.brres\npaste material for road in dest.brres\n"
    ),
}


def _exact(path: Path, data: bytes) -> bool:
    return path.is_file() and path.read_bytes() == data


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


def _texture(path: Path, name: str) -> bool:
    return _exact(path, (FOLDER / "inputs" / name).read_bytes())


def _adapter_state(name: str) -> bool:
    """Staged adapter layouts: textures moved away, or info on a known conversion."""
    if name in INFO_SOURCES:
        archive, marker = INFO_SOURCES[name]
        return _exact(Path(archive), marker)
    folder, gone = MOVED.get(name, ("", ()))
    return not any(Path(f"{t}.png").exists() for t in gone) and all(
        _texture(Path(folder) / f"{t}.png", f"{t}.png") for t in gone
    )


def _fixtures_for(row: dict[str, Any]) -> bool:
    """Every recorded input beside the command, except textures the case moved away."""
    name = str(row["case"])
    if name in INFO_SOURCES:
        return True  # the conversion that made the archive already checked its inputs
    moved = {f"{t}.png" for t in MOVED.get(name, ("", ()))[1]}
    return all(_texture(Path(item), item) for item in row["inputs"] if item not in moved)


def _state(row: dict[str, Any]) -> bool:
    name = str(row["case"])
    if row["compare"] == "unmodelled" or not _fixtures_for(row) or not _wimgt_matches(name):
        return False
    if name.startswith("adapter"):
        return _adapter_state(name) and (name in INFO_SOURCES or _convert_state(name, row))
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


def _marker(row: dict[str, Any]) -> bytes:
    """Texture-loss and minimap stand-ins differ, so neither passes as a textured model."""
    if row["case"] in TEXTURE_LOSS:
        return NO_TEXTURES_MARKER
    return MAP_MARKER if row["argv"][1:2] == ["map.obj"] else MARKER


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
    marker = _marker(row)
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
