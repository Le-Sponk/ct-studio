"""Blocking project-details persistence; invoke only from a joined GUI worker."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import tomli_w

from ctstudio.core import fsutil
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.project.slots import SLOTS


@dataclass(frozen=True)
class DetailsSnapshot:
    """Loaded manifest plus its exact bytes, for optimistic edit protection."""

    root: Path
    manifest: Manifest
    raw: bytes
    backup: Path | None = None


class ProjectDetailsService:
    """Blocking disk operations; the caller owns project and worker lifetimes."""

    def load(self, project: Project) -> DetailsSnapshot:
        """Read project details without writing or changing the in-memory project."""
        try:
            root = project.root.resolve()
            path = project.manifest_path
            raw = path.read_bytes()
            manifest = manifest_io.load(path)
            if path.read_bytes() != raw:
                raise _conflict("The project file changed while loading details.")
            return DetailsSnapshot(root, manifest, raw)
        except (OSError, ValueError, RuntimeError) as exc:
            raise ProjectError(
                "Could not load project details.",
                hint="Check the project path and read permissions, then reopen the details.",
                details=str(exc),
            ) from exc

    def save(
        self, project: Project, snapshot: DetailsSnapshot, slot: str, blend: Path | None
    ) -> DetailsSnapshot:
        """Persist details; the UI must publish the returned manifest after joining.

        Both the live manifest and disk bytes must still match the loaded snapshot.
        A stale live manifest (even before load) requires reopening the project first;
        merging it here could silently discard a different in-memory edit.
        """
        try:
            _check_editable(project, snapshot)
            if slot not in SLOTS:
                raise ProjectError(
                    "The selected track or arena slot is not valid.",
                    hint="Choose an original track or arena from the list.",
                )
            text = _blend_text(snapshot.root, blend)
            info = replace(snapshot.manifest.project, slot=slot, blend=text)
            manifest = replace(snapshot.manifest, project=info)
            return persist_snapshot(project, snapshot, manifest)
        except (OSError, ValueError, RuntimeError) as exc:
            raise ProjectError(
                "Could not save project details.",
                hint="Check file paths, permissions and free disk space, then reopen the details.",
                details=str(exc),
            ) from exc


def persist_snapshot(
    project: Project, snapshot: DetailsSnapshot, manifest: Manifest
) -> DetailsSnapshot:
    """Commit an edited snapshot; callers wrap disk errors and join before publishing.

    No-op saves still verify ownership, live state and exact disk bytes. Staging uses
    the same expected-content commit check as other edits; no generated/manual files move.
    """
    _check_editable(project, snapshot)
    raw = tomli_w.dumps(manifest_io.as_data(manifest)).encode("utf-8")
    if project.manifest_path.read_bytes() != snapshot.raw:
        raise _conflict("The project file changed after loading details; nothing was saved.")
    if manifest == snapshot.manifest:
        return replace(snapshot, backup=None)
    backup = fsutil.replace_with_backup(project.manifest_path, raw, expected=snapshot.raw)
    return DetailsSnapshot(snapshot.root, manifest, raw, backup)


def _check_editable(project: Project, snapshot: DetailsSnapshot) -> None:
    if project.read_only:
        raise ProjectError(
            "The project is read-only or closed; its details were not saved.",
            hint=f"{project.read_only_reason or 'No project write lock'}. Reopen it for editing.",
        )
    if project.root.resolve() != snapshot.root:
        raise _conflict("These details belong to a different project folder.")
    if project.manifest != snapshot.manifest:
        raise _conflict("The current project settings changed; its details were not saved.")


def _blend_text(root: Path, blend: Path | None) -> str | None:
    if blend is None:
        return None
    if "\x00" in str(blend) or not blend.is_absolute():
        raise ProjectError(
            "The Blender source path is not a valid absolute path.",
            hint="Choose an existing .blend file using the file chooser, or clear the source.",
        )
    if blend.suffix.casefold() != ".blend":
        raise ProjectError(
            "The Blender source must be a .blend file.", hint="Choose a file ending in .blend."
        )
    absolute = blend.resolve()
    if not absolute.is_file():
        raise ProjectError(
            "The Blender source does not exist or is not a file.",
            hint="Choose an existing .blend file, or clear the source.",
        )
    if absolute.is_relative_to(root):
        return absolute.relative_to(root).as_posix()
    return str(absolute)


def _conflict(message: str) -> ProjectError:
    return ProjectError(message, hint="Close and reopen the project before editing its details.")
