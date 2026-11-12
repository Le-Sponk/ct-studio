"""A project folder on disk: create, open, save, lock (P3-T02, ARCHITECTURE §5).

``Project.create`` makes the §5 folders, a default ``ctstudio.toml`` and a ``.gitignore``.
It refuses a folder that already has things in it unless ``force`` is set, and never
replaces an existing ``ctstudio.toml``. ``Project.open`` loads the manifest and takes the
project lock (``lock.py``); when another CT Studio holds it, the project opens read-only
and ``read_only_reason`` says who. Close the project (or use it as a context manager) to
release the lock.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from ctstudio.core.errors import ProjectError
from ctstudio.core.fsutil import atomic_write_text
from ctstudio.core.project import manifest_io
from ctstudio.core.project.lock import HeldLock, LockOwner, acquire
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.project.slots import DEFAULT_SLOT
from ctstudio.core.project.toml_table import Table

FOLDERS = ("files", "overrides", "build", ".ctstudio")
GITIGNORE = "# CT Studio: rebuilt on demand, safe to delete\n.ctstudio/\nbuild/\n"


@dataclass
class Project:
    root: Path
    manifest: Manifest
    lock: HeldLock | None
    read_only_reason: str | None = None
    lock_owner: LockOwner | None = None

    @property
    def read_only(self) -> bool:
        """No writer lock, or unsafe saved state despite retaining the lock for inspection."""
        return self.lock is None or self.read_only_reason is not None

    @property
    def manifest_path(self) -> Path:
        return self.root / manifest_io.FILE_NAME

    @classmethod
    def create(
        cls,
        root: Path,
        name: str,
        *,
        blend: Path | None = None,
        slot: str = DEFAULT_SLOT,
        force: bool = False,
    ) -> Project:
        """A new project in ``root`` (created if missing), opened and locked."""
        info = _checked(ProjectInfo(name=name, slot=slot, blend=_blend_text(root, blend)))
        _check_target(root, force=force)
        _make_layout(root)
        manifest_io.save(Manifest(project=info), root / manifest_io.FILE_NAME)
        return cls.open(root)

    @classmethod
    def open(cls, root: Path) -> Project:
        """The project in ``root``; read-only when another CT Studio has it open."""
        manifest_path = root / manifest_io.FILE_NAME
        if not manifest_path.is_file():
            manifest_io.load(manifest_path)  # raises the "no ctstudio.toml" error
        (root / ".ctstudio").mkdir(exist_ok=True)
        result = acquire(root)
        try:
            manifest = manifest_io.load(manifest_path)
        except BaseException:
            if result.held is not None:
                result.held.release()
            raise
        return cls(root, manifest, result.held, result.reason, result.owner)

    def save(self, manifest: Manifest) -> None:
        """Write ``manifest`` and make it the current snapshot."""
        if self.read_only:
            raise ProjectError(
                "This project is open read-only, so it was not saved.",
                hint=f"{self.read_only_reason or 'It was closed'}. Close it there and reopen.",
            )
        manifest_io.save(manifest, self.manifest_path)
        self.manifest = manifest

    def close(self) -> None:
        """Release the lock; the project stays readable but can no longer be saved."""
        if self.lock is not None:
            self.lock.release()
            self.lock = None
            self.read_only_reason = "the project was closed"

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _checked(info: ProjectInfo) -> ProjectInfo:
    """``info`` validated by the same rules as a loaded file, before anything is written."""
    data: dict[str, object] = {"name": info.name, "slot": info.slot}
    if info.blend is not None:
        data["blend"] = info.blend
    return manifest_io.project_info(Table(data, "project", []))


def _blend_text(root: Path, blend: Path | None) -> str | None:
    """Relative with forward slashes when inside the project, otherwise absolute."""
    if blend is None:
        return None
    absolute = Path(os.path.abspath(blend))
    project = Path(os.path.abspath(root))
    if absolute.is_relative_to(project):
        return absolute.relative_to(project).as_posix()
    return str(blend.resolve())


def _make_layout(root: Path) -> None:
    try:
        for folder in FOLDERS:
            (root / folder).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProjectError(
            f"Could not make {root}.",
            hint="Choose a folder you can write to.",
            details=f"path={root}; error={exc}",
        ) from exc
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        atomic_write_text(gitignore, GITIGNORE)


def _check_target(root: Path, *, force: bool) -> None:
    if root.exists() and not root.is_dir():
        raise ProjectError(f"{root} is not a folder.", hint="Choose a folder for the project.")
    if (root / manifest_io.FILE_NAME).exists():
        raise ProjectError(
            f"{root} already has a CT Studio project.",
            hint="Open it instead, or choose another folder.",
        )
    if root.is_dir() and not force and any(root.iterdir()):
        raise ProjectError(
            f"{root} is not empty.",
            hint="Choose an empty or new folder, or use --force to add a project to this folder.",
        )
