"""Shared set-up for the P5-T06b tests: a project whose parts CT Studio "made", then edited.

``made(project, part)`` does what the build runner does for a generated part: it writes the
part's output under ``.ctstudio/stage/`` and records it in state.json. ``edit`` then changes
that output the way another program would (new bytes, a later mtime). All files are
synthetic (``test_magic`` builders); nothing comes from a game disc.
"""

from __future__ import annotations

import os
from pathlib import Path

from test_magic import brres, kcl, postfx

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.components.state import (
    GENERATED_DIR,
    ProjectState,
    load_state,
    record,
    save_state,
)
from ctstudio.core.components.status import settings_key
from ctstudio.core.project.project import Project

BACKUPS = ".ctstudio/backups"
LOCK = ".ctstudio/lock"  # the open project's own lock file: it changes while open

# What CT Studio "made" for each part it can make, and what the user's edit wrote instead.
MADE: dict[str, dict[str, bytes]] = {
    "course_model": {"course_model.brres": brres()},
    "kcl": {"course.kcl": kcl()},
    "minimap": {"map_model.brres": brres(0x100)},
    "skybox": {"vrcorn_model.brres": brres(0xC0)},
    "posteffect": {
        "posteffect/posteffect.bblm": postfx(b"PBLM"),
        "posteffect/posteffect.bfg": b"fog",
    },
}
EDITED: dict[str, tuple[str, bytes]] = {
    "course_model": ("course_model.brres", brres(0x90)),
    "kcl": ("course.kcl", kcl(size=0x480)),
    "minimap": ("map_model.brres", brres(0x110)),
    "skybox": ("vrcorn_model.brres", brres(0xD0)),
    "posteffect": ("posteffect/posteffect.bblm", postfx(b"PBLM", 0x60)),
}
PARTS = sorted(MADE)
GAME_NAME = {part: COMPONENT_BY_ID[part].outputs[0].rstrip("/") for part in PARTS}


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def later(path: Path) -> None:
    """A later mtime, so the change is seen even when the size happens to match."""
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


def stage(project: Project) -> Path:
    return project.root / GENERATED_DIR


def made(project: Project, part: str) -> None:
    """Write the part's outputs and record them, as a build would."""
    outputs = [write(stage(project) / rel, data) for rel, data in MADE[part].items()]
    entry = record(project.root, settings_key(project.manifest, part), outputs, [])
    components = {**load_state(project.root).components, part: entry}
    save_state(project.root, ProjectState(components))


def edit(project: Project, part: str, data: bytes | None = None) -> Path:
    """Change the part's output outside CT Studio; ``data`` replaces the usual edit."""
    rel, edited = EDITED[part]
    path = write(stage(project) / rel, edited if data is None else data)
    later(path)
    return path


def tree(folder: Path) -> dict[str, bytes]:
    if not folder.exists():
        return {}
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def everything(project: Project) -> dict[str, bytes]:
    """Every file in the project except its lock, to show that nothing changed."""
    files = tree(project.root)
    files.pop(LOCK, None)
    return files


def folders(project: Project) -> list[str]:
    """Every folder in the project (an empty backup folder left behind would show here)."""
    root = project.root
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir())
