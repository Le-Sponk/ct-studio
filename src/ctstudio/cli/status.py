"""``ctstudio status``: every part of a project, with what is left to do (P3-T07).

Reads ``ctstudio.toml`` without taking the project's lock, so it also works while CT
Studio has the project open. Tools are only looked for, never started. Exit status: 1 when
the project cannot be read or a part has a problem that stops a build, else 0. The JSON
schema is in ``docs/dev/CLI.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.components.status import STATE_LABELS, ComponentStatus, State, evaluate
from ctstudio.core.project import manifest_io, settings
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.settings import SettingsError
from ctstudio.core.project.slots import find
from ctstudio.core.tools.availability import available_tools

JSON_FORMAT = 1
ICONS: Mapping[State, str] = {
    State.MISSING: "[ ]",
    State.STALE: "[~]",
    State.READY: "[ok]",
    State.WARNING: "[!]",
    State.ERROR: "[x]",
    State.MANUAL: "[ok]",
    State.EDITED_EXTERNALLY: "[*]",
}
_DONE = (State.READY, State.MANUAL)
_HEADERS = ("", "Part", "Status")


@dataclass(frozen=True)
class _ReadOnly:
    """The two things a status needs; ``Project.open`` would take the lock."""

    root: Path
    manifest: Manifest


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "status",
        help="show what each part of a project needs",
        description="Show each part of the project in FOLDER (default: this folder) and why "
        "it has that status. Exits 1 when a part has a problem that stops a build.",
    )
    parser.add_argument("folder", nargs="?", type=Path, default=Path(), help="the project folder")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")


def configured_tools() -> dict[str, Path]:
    """Paths set in CT Studio; a damaged settings file is reported, then left out."""
    try:
        return settings.load().configured()
    except SettingsError as exc:
        print(
            f"Warning: {exc.user_message}\nPaths set in CT Studio are ignored for this check.",
            file=sys.stderr,
        )
        return {}


def run(args: argparse.Namespace) -> int:
    root: Path = args.folder.resolve()
    manifest = manifest_io.load(root / manifest_io.FILE_NAME)
    statuses = evaluate(_ReadOnly(root, manifest), available_tools(configured=configured_tools()))
    if args.json:
        print(json.dumps(to_json(root, manifest, statuses), indent=1, ensure_ascii=False))
    else:
        print(render(root, manifest, statuses), end="")
    return exit_code(statuses)


def exit_code(statuses: Mapping[str, ComponentStatus]) -> int:
    return 1 if any(s.state is State.ERROR for s in statuses.values()) else 0


def to_json(
    root: Path, manifest: Manifest, statuses: Mapping[str, ComponentStatus]
) -> dict[str, object]:
    info = manifest.project
    parts = [
        {
            "id": part,
            "name": COMPONENT_BY_ID[part].name,
            "state": status.state.value,
            "label": STATE_LABELS[status.state],
            "reasons": list(status.reasons),
        }
        for part, status in statuses.items()
    ]
    return {
        "format": JSON_FORMAT,
        "ok": exit_code(statuses) == 0,
        "project": {
            "name": info.name,
            "folder": root.as_posix(),
            "slot": info.slot,
            "slot_name": find(info.slot).name,
        },
        "parts": parts,
    }


def render(root: Path, manifest: Manifest, statuses: Mapping[str, ComponentStatus]) -> str:
    """The table: one row per part, then one indented line per reason, then a verdict."""
    rows = [
        (ICONS[s.state], COMPONENT_BY_ID[part].name, STATE_LABELS[s.state])
        for part, s in statuses.items()
    ]
    widths = [max(len(cells[i]) for cells in (_HEADERS, *rows)) for i in range(3)]

    def line(cells: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)).rstrip()

    info = manifest.project
    out = [f"{info.name}, replacing {find(info.slot).label}", f"Folder: {root.as_posix()}", ""]
    out += [line(_HEADERS), line(tuple("-" * w for w in widths))]
    for cells, status in zip(rows, statuses.values(), strict=True):
        out.append(line(cells))
        out.extend(f"        {reason}" for reason in status.reasons)
    out += ["", _verdict(statuses)]
    return "\n".join(out) + "\n"


def _verdict(statuses: Mapping[str, ComponentStatus]) -> str:
    done = sum(s.state in _DONE for s in statuses.values())
    ready = f"{done} of {len(statuses)} parts are ready."
    broken = [COMPONENT_BY_ID[p].name for p, s in statuses.items() if s.state is State.ERROR]
    if broken:
        marked = ICONS[State.ERROR]
        return f"{ready} Fix the parts marked {marked} before building: {', '.join(broken)}."
    return f"{ready} Nothing listed here stops a build."
