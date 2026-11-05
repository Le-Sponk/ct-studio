"""Blocking location inspection; callers own worker and project lifetimes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ctstudio.core.components.registry import COMPONENT_BY_ID, ComponentSpec
from ctstudio.core.components.state import GENERATED_DIR
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.tools import folders


class FolderRevealService:
    """Inspect readable snapshots, including closed projects; invoke off the UI thread."""

    def __init__(
        self, *, open_folder: Callable[[Path], folders.OpenedFolder] = folders.open_folder
    ) -> None:
        self._open_folder = open_folder

    def reveal(self, project: Project, component_id: str) -> folders.OpenedFolder:
        """Return the adapter's dispatch receipt, not confirmation of a displayed window."""
        try:
            root, manifest = project.root, project.manifest
            spec = COMPONENT_BY_ID.get(component_id)
            if spec is None:
                raise ProjectError(
                    f"Cannot reveal unknown component '{component_id}'.",
                    hint="Select a component from the current project and try again.",
                )
            folder = _folder(root, manifest, spec).resolve()
            if project.root != root or project.manifest is not manifest:
                raise ProjectError(
                    "The project changed while preparing its component folder.",
                    hint="Select the current project and try revealing the component again.",
                )
            return self._open_folder(folder)
        except (OSError, ValueError, RuntimeError) as exc:
            raise ProjectError(
                f"Could not reveal the folder for component '{component_id}'.",
                hint="Check the component path and folder permissions, then try again.",
                details=str(exc),
            ) from exc


def _folder(root: Path, manifest: Manifest, spec: ComponentSpec) -> Path:
    if spec.manifest_table == "project":
        return (root / manifest_io.FILE_NAME).parent
    if spec.manifest_table is not None:
        table = getattr(manifest.components, spec.manifest_table)
        directory_output = bool(spec.outputs and spec.outputs[0].endswith("/"))
        if table.mode == "manual":
            if table.file:
                location = root / Path(table.file)
                return location if directory_output else location.parent
        elif spec.outputs:
            location = root / GENERATED_DIR / spec.outputs[0]
            return location if directory_output else location.parent
    raise ProjectError(
        f"{spec.name} has no single location to reveal.",
        hint="Choose a supplied file or folder for this component, or inspect the project's files.",
    )
