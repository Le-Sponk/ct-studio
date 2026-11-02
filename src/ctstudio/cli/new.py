"""``ctstudio new``: make a project folder (P3-T07).

The project is created, then closed at once, so the lock is never left behind.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.core.project.slots import DEFAULT_SLOT, Slot, UnknownSlot, find


def _slot(text: str) -> Slot:
    try:
        return find(text)
    except UnknownSlot as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "new",
        help="make a new track project",
        description="Make a new CT Studio project in FOLDER (created if missing).",
    )
    parser.add_argument("folder", type=Path, help="the project folder")
    parser.add_argument("--name", help="the track's name (default: the folder name)")
    parser.add_argument("--blend", type=Path, help="the Blender file the track is made from")
    parser.add_argument(
        "--slot",
        type=_slot,
        default=find(DEFAULT_SLOT),
        help="the original track it replaces: file name, track name or abbreviation "
        f"(default: {DEFAULT_SLOT})",
    )
    parser.add_argument(
        "--force", action="store_true", help="add a project to a folder that already has files"
    )


def run(args: argparse.Namespace) -> int:
    folder: Path = args.folder
    slot: Slot = args.slot
    blend: Path | None = args.blend
    if blend is not None and not blend.is_file():
        raise ProjectError(
            f"{blend} was not found.",
            hint="Give the path of an existing .blend file, or leave --blend out and choose "
            "it later.",
        )
    name = args.name if args.name is not None else folder.resolve().name
    with Project.create(folder, name, blend=blend, slot=slot.file, force=args.force) as project:
        info = project.manifest.project
        print(
            f"Created '{info.name}' in {project.root.resolve().as_posix()}, replacing {slot.label}."
        )
        if info.blend is not None:
            print(f"Blender file: {info.blend}")
    print(f'See what is left to do: ctstudio status "{folder}"')
    return 0
