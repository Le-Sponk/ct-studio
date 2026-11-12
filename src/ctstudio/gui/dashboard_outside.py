"""Memory-only routing of outside-edit choices through the existing joined owner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.gui.dashboard_reconcile import present_reconcile
from ctstudio.gui.launch_controller import LaunchResult

if TYPE_CHECKING:
    from ctstudio.gui.views.dashboard import Dashboard


@dataclass(frozen=True)
class _Request:
    project: Project
    root: Path
    manifest: Manifest
    part: str
    action: str

    def matches(self, result: LaunchResult) -> bool:
        return (
            result.project is self.project
            and result.root == self.root
            and result.manifest is self.manifest
            and result.component_id == self.part
            and result.edit_action == self.action
        )


class DashboardOutside(QObject):
    """Own only presentation context, never worker lifetime or project ownership."""

    def __init__(self, page: Dashboard) -> None:
        super().__init__(page)
        self.page = page
        self._pending: _Request | None = None
        self._root: Path | None = None
        self._manifest: Manifest | None = None

    @property
    def pending(self) -> bool:
        return self._pending is not None

    def bind(self, project: Project) -> None:
        """Capture the identity that produced the displayed cards before modal callbacks."""
        self.clear()
        self._root, self._manifest = project.root, project.manifest

    def _eligible(self, project: Project) -> bool:
        return (
            self.page.mutable and project.root == self._root and project.manifest is self._manifest
        )

    def clear(self) -> None:
        """Invalidate outstanding presentation and modal approval, not the worker."""
        self._pending = None
        self._root = self._manifest = None
        for card in self.page.cards.values():
            card.outside.clear()

    def request(self, part: str, action: str) -> None:
        page = self.page
        project = page.services.project
        card = page.cards.get(part)
        if (
            project is None
            or card is None
            or action not in ("lock", "discard")
            or not self._eligible(project)
            or not card.can_reconcile()
        ):
            return
        request = _Request(project, project.root, project.manifest, part, action)
        self._pending = request  # busy/completion callbacks can run inside start_reconcile
        card.outside.show_work(action)
        try:
            started = page.services.start_reconcile(part, action)
        except CTStudioError as exc:
            self._pending = None
            card.outside.show_work(None)
            card.outside.show_note(str(exc))
            return
        if not started and self._pending is request and not page.services.launch.busy:
            self._pending = None
            card.outside.show_work(None)
            card.outside.show_note("The outside-edit request did not start. Try again.")

    def completed(self, result: LaunchResult) -> None:
        request = self._pending
        if request is not None and not request.matches(result):
            return
        self._pending = None
        target = self.page.cards.get(result.component_id or "")
        if target is not None:
            target.outside.show_work(None)
        present_reconcile(self.page, result)
        if target is not None:
            target.outside.show_note(self.page.launch_notice.text())
