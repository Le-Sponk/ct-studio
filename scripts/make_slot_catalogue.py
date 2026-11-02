"""Make ``src/ctstudio/core/project/slots.json`` from recorded ``wstrt`` output (P3-T06).

    uv run python scripts/make_slot_catalogue.py            # write slots.json from the recording
    uv run python scripts/make_slot_catalogue.py --check    # exit 1 if slots.json is out of date
    uv run python scripts/make_slot_catalogue.py --record   # re-run wstrt, then write

Every file name, display name, abbreviation and cup position comes from Wiimm's
``wstrt tracks --long`` / ``wstrt arenas --long`` (Wiimms SZS Tools 2.42a), which print the
game's standard order with Wiimm's built-in English names. ``wszst tracks`` prints only the
file names ("use BMG files to print real names"), and reading names out of the game's own
message files would mean shipping game data, so ``wstrt`` is the source.

Only the cup names are typed here: Wiimm's tables give each track a cup *number* (``1.1`` =
cup 1, track 1) but no cup name. Names checked on 2026-11-02 against
https://wiki.tockdom.com/wiki/MKW (Track Listing / Arena Listing).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
WSTRT_VERSION = "2.42a"
RECORDING = REPO_ROOT / "tests/fakes/recordings/wstrt" / WSTRT_VERSION / "windows-catalogue.json"
OUTPUT = REPO_ROOT / "src/ctstudio/core/project/slots.json"
ARGVS: tuple[tuple[str, ...], ...] = (("version",), ("tracks", "--long"), ("arenas", "--long"))

RACE_CUPS = (
    "Mushroom Cup",
    "Flower Cup",
    "Star Cup",
    "Special Cup",
    "Shell Cup",
    "Banana Cup",
    "Leaf Cup",
    "Lightning Cup",
)
ARENA_GROUPS = ("Wii Arenas", "Retro Arenas")
SHAPE = {"race": (len(RACE_CUPS), 4), "arena": (len(ARENA_GROUPS), 5)}

# " 8.  1.1  1.1  beginner_course      0x7d  n_Circuit32_n         _f  LC    Luigi Circuit"
# idx, new slot, standard slot, file, sound slot, sound file, fast suffix, abbr, name.
# An abbreviation can fill its column ("nDKJP N64 DK's ..."), leaving one space before the name.
_ROW = re.compile(
    r"^\s*\d+\.\s+(?P<new>\d)\.(?P<new_pos>\d)\s+(?P<cup>\d)\.(?P<pos>\d)\s+(?P<file>\w+)"
    r"\s+0x[0-9a-f]+\s+\S+\s+_[fF]\s+(?P<abbr>\S+)\s+(?P<name>\S.*?)\s*$"
)
_DATA_LINE = re.compile(r"^\s*\d+\.\s")  # every table row starts with its index


class GenerateError(Exception):
    """The recording cannot be turned into the catalogue."""


def load_recording(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def build(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The catalogue as JSON data; every check that the recording is complete happens here."""
    version = _stdout(records, ("version",))
    if f"v{WSTRT_VERSION} " not in version:
        raise GenerateError(f"recording is not from wstrt {WSTRT_VERSION}: {version.strip()!r}")
    rows = [
        *_rows(_stdout(records, ("tracks", "--long")), "race"),
        *_rows(_stdout(records, ("arenas", "--long")), "arena"),
    ]
    return {
        "source": f"wstrt {WSTRT_VERSION} tracks/arenas --long (scripts/make_slot_catalogue.py)",
        "slots": rows,
    }


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _stdout(records: Sequence[dict[str, Any]], argv: tuple[str, ...]) -> str:
    run = next((r for r in records if tuple(r["argv"]) == argv), None)
    shown = " ".join(argv)
    if run is None:
        raise GenerateError(f"recording has no 'wstrt {shown}' run")
    if run["exit_code"] != 0:
        raise GenerateError(f"'wstrt {shown}' failed with exit code {run['exit_code']}")
    return str(run["stdout"])


def _rows(stdout: str, kind: str) -> list[dict[str, Any]]:
    groups, size = SHAPE[kind]
    names = RACE_CUPS if kind == "race" else ARENA_GROUPS
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not _DATA_LINE.match(line):
            continue  # blank, header or ruler line
        match = _ROW.match(line)
        if match is None:
            raise GenerateError(f"cannot read this {kind} row: {line.strip()!r}")
        expected = divmod(len(rows), size)
        cup, pos = int(match["cup"]) - 1, int(match["pos"]) - 1
        if (cup, pos) != expected or (match["new"], match["new_pos"]) != (
            match["cup"],
            match["pos"],
        ):
            want = f"{expected[0] + 1}.{expected[1] + 1}"
            got = f"{match['new']}.{match['new_pos']} / {match['cup']}.{match['pos']}"
            raise GenerateError(
                f"{match['file']} is not in the standard order (expected {want}, got {got})"
            )
        rows.append(
            {
                "file": match["file"],
                "name": match["name"],
                "abbr": match["abbr"],
                "kind": kind,
                "cup": names[cup],
                "cup_number": cup + 1,
                "position": pos + 1,
            }
        )
    if len(rows) != groups * size:
        raise GenerateError(
            f"expected 32 race tracks and 10 arenas; found {len(rows)} {kind} rows,"
            f" not {groups * size}"
        )
    return rows


def record(wstrt: Path, out: Path, tools_root: Path) -> None:
    """Re-run the pinned wstrt and store its complete output (the tool folder is hidden)."""
    import record_tool_help as rth  # lazy: pulls in the tool catalogue and the core runner

    records = rth.record(wstrt, ARGVS, tools_root=tools_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make slots.json from recorded wstrt output.")
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is out of date")
    parser.add_argument("--record", action="store_true", help="re-run wstrt before generating")
    parser.add_argument("--out", type=Path, default=OUTPUT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.record:
        import tool_paths as tp

        record(tp.exe(tp.WIIMMS_BIN / "wstrt"), RECORDING, tp.TOOLS_DIR)
    text = render(build(load_recording(RECORDING)))
    out: Path = args.out
    current = out.read_text(encoding="utf-8") if out.is_file() else None
    if args.check:
        if current != text:
            print(f"{out} is out of date; run: uv run python scripts/make_slot_catalogue.py")
            return 1
        return 0
    if current != text:
        out.write_text(text, encoding="utf-8", newline="\n")
    print(f"{out}: {len(json.loads(text)['slots'])} slots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
