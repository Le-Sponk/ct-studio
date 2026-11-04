"""Blocking component-mode persistence; call from a joined GUI worker."""

from __future__ import annotations

from dataclasses import replace

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.project_details import DetailsSnapshot, ProjectDetailsService, persist_snapshot


class ComponentModeService:
    """Return snapshots, never publish them or start builds; callers own busy/lock lifetimes."""

    def load(self, project: Project) -> DetailsSnapshot:
        """Reuse the stable, exact-byte read used by project details (blocking)."""
        return ProjectDetailsService().load(project)

    def save(
        self, project: Project, snapshot: DetailsSnapshot, component_id: str, mode: str
    ) -> DetailsSnapshot:
        """Change a mode without assigning/copying files or changing inactive settings."""
        spec = COMPONENT_BY_ID.get(component_id)
        if spec is None or spec.manifest_table in (None, "project"):
            raise ProjectError(
                "This component has no editable mode settings.",
                hint="Choose a component with a mode listed in its settings.",
            )
        if mode not in spec.modes:
            raise ProjectError(
                f"The mode {mode!r} is not supported for {spec.name}.",
                hint=f"Choose one of: {', '.join(spec.modes)}.",
            )
        table = spec.manifest_table
        part = getattr(snapshot.manifest.components, table)
        components = replace(snapshot.manifest.components, **{table: replace(part, mode=mode)})
        try:
            return persist_snapshot(
                project, snapshot, replace(snapshot.manifest, components=components)
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise ProjectError(
                f"Could not save the mode for {spec.name}.",
                hint="Check project permissions and free disk space, then reopen the project.",
                details=str(exc),
            ) from exc
