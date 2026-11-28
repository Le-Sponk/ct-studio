"""Card file-assignment requests and their joined results for the dashboard (P5-T04b).

Moved out of ``views/dashboard.py`` unchanged in behaviour (P5-T07e1, file budget). The launch
owner runs the assignment; this module asks for it and publishes the saved manifest.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

from ctstudio.core.components.assign import Assigned
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.project import Project
from ctstudio.gui.assign_text import STALE_ASSIGNMENT, assignment_detail, describe_assignment
from ctstudio.gui.launch_controller import LaunchResult

if TYPE_CHECKING:
    from ctstudio.gui.views.dashboard import Dashboard


class DashboardAssign(QObject):
    """Ask the launch owner to use a file for a part, then publish what it saved."""

    def __init__(self, page: Dashboard) -> None:
        super().__init__(page)
        self.page = page

    def request(self, part: str, source: Path, reference: bool) -> None:
        """A card asked to use ``source``; the launch owner runs it, ``completed`` reports."""
        page = self.page
        card = page.cards.get(part)
        if card is None or page.shown_project is None:
            return
        try:
            started = page.services.start_assign(part, source, reference=reference)
        except CTStudioError as exc:
            card.show_assign_note(str(exc))
            return
        if started:
            doing = "Recording" if reference else "Copying"
            where = "" if reference else " into the project"
            card.show_assign_note(f"{doing} {source.name or source}{where}…")

    def completed(self, project: Project, result: LaunchResult) -> None:
        """Publish a saved assignment (UI thread, worker joined), then check statuses again."""
        page = self.page
        card = page.cards.get(result.component_id or "")
        receipt = result.receipt
        if isinstance(receipt, Assigned):
            if result.manifest is not project.manifest:  # changed meanwhile: keep it
                if card is not None:
                    card.show_assign_note(STALE_ASSIGNMENT)
                return
            project.manifest = receipt.manifest
            page.outside_edits.bind(project)
            for each in page.cards.values():
                each.bind(project)
            page.recheck()
        page.show_launch_note("")
        if card is not None:
            card.show_assign_note(describe_assignment(result), assignment_detail(result))
