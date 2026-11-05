"""Blocking Blender launch preparation; callers own project and worker lifetimes."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import settings
from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors


class EditorOpener(Protocol):
    def __call__(
        self, tool_id: str, document: Path, *, executable: Path | None = None
    ) -> editors.Launched: ...


class BlenderLaunchService:
    """Launch only, not a document-load receipt; invoke from a joined worker."""

    def __init__(
        self,
        *,
        settings_path: Path | None = None,
        open_editor: EditorOpener = editors.open_in,
    ) -> None:
        self._settings_path = settings_path
        self._open_editor = open_editor

    def launch(self, project: Project) -> editors.Launched:
        """Use the current source and freshly loaded machine settings without writing."""
        try:
            root, manifest = project.root, project.manifest
            if project.read_only:
                raise ProjectError(
                    "Cannot launch Blender for a read-only or closed project.",
                    hint="Reopen the project for editing before launching Blender.",
                )
            source = manifest.project.blend
            if not source:
                raise ProjectError(
                    "This project has no Blender source.",
                    hint="Choose a .blend source in the project details first.",
                )
            document = (root / Path(source)).resolve()
            configured = settings.load(self._settings_path).configured()
            if project.read_only or project.root != root or project.manifest is not manifest:
                raise ProjectError(
                    "The project changed or closed while preparing the Blender launch.",
                    hint="Reopen the current project and try launching Blender again.",
                )
            return self._open_editor("blender", document, executable=configured.get("blender"))
        except (OSError, ValueError, RuntimeError) as exc:
            raise ProjectError(
                "Could not launch Blender for this project.",
                hint="Check the source path, read permissions and Blender's Tools settings; retry.",
                details=str(exc),
            ) from exc
