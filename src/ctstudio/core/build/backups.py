"""Back up files CT Studio made that the user then edited, before a step replaces them.

ARCHITECTURE §8: before any overwrite of a file whose hash differs from what the app last
wrote, a timestamped backup is made — no exceptions. The build cache names such files
(``Lookup.edited``); they are copied to ``.ctstudio/backups/<UTC time>/<project path>``.
Complete backups are never deleted by CT Studio; only a backup that failed part-way is
removed again.
"""

from __future__ import annotations

import errno
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ctstudio.core.build.node import StepFailed
from ctstudio.core.validation.issues import Issue

BACKUP_DIR = ".ctstudio/backups"


def back_up(root: Path, files: Sequence[Path], step: str) -> Path:
    """Copy ``files`` into a new backup folder and return it; StepFailed when that fails."""
    try:
        folder = _new_folder(root / BACKUP_DIR, _stamp())
    except OSError as exc:
        raise _failed(root, files[0], step, exc) from exc
    for file in files:
        try:
            copy = folder / _relative(root, file)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, copy)
        except OSError as exc:
            raise _failed(root, file, step, exc) from exc
    return folder


def save_copies(root: Path, paths: Sequence[Path]) -> Path:
    """Copy files or whole folders into a new backup folder and return it.

    On any failure the incomplete backup folder is removed again and the error re-raised
    (an ``OSError`` naming the file that could not be copied).
    """
    folder = _new_folder(root / BACKUP_DIR, _stamp())
    try:
        for path in paths:
            copy = folder / _relative(root, path)
            for item in [path, *sorted(path.rglob("*"))] if path.is_dir() else [path]:
                _copy_item(item, copy / item.relative_to(path))
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder


def _copy_item(item: Path, copy: Path) -> None:
    if item.is_dir():
        copy.mkdir(parents=True, exist_ok=True)
    else:
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, copy)


def _new_folder(parent: Path, stamp: str) -> Path:
    for n in range(1000):
        folder = parent / (f"{stamp}-{n}" if n else stamp)
        try:
            folder.mkdir(parents=True)
        except FileExistsError:
            continue
        return folder
    raise FileExistsError(f"no free backup folder for {stamp} in {parent}")


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S.%fZ")


def _relative(root: Path, file: Path) -> Path:
    return file.relative_to(root) if file.is_relative_to(root) else Path("outside") / file.name


def _failed(root: Path, file: Path, step: str, exc: OSError) -> StepFailed:
    shown = _relative(root, file).as_posix()
    full = exc.errno == errno.ENOSPC
    hint = (
        "Free some disk space, then build again."
        if full
        else "Check that the project folder can be written to, then build again."
    )
    return StepFailed(
        Issue(
            "error",
            "build",
            "BUILD_BACKUP_FAILED",
            f"Could not back up {shown}, which you edited, before replacing it: "
            f"{exc.strerror or exc}.",
            f"{hint} Your edit was not touched.",
            step,
            file,
        )
    )
