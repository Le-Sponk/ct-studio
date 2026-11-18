"""Memory-only routing of editor preparation/open requests through the joined owner (d3)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.gui.editor_launch import PreparedEditors
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.launch_text import describe_editor, describe_launch

if TYPE_CHECKING:
    from ctstudio.gui.views.dashboard import Dashboard


@dataclass(frozen=True)
class _Request:
    """The identity captured when a request started (memory only)."""

    project: Project
    root: Path
    manifest: Manifest
    action: str
    choice: EditorChoice | None = None
    label: str = ""

    def matches(self, result: LaunchResult) -> bool:
        return (
            result.project is self.project
            and result.root == self.root
            and result.manifest is self.manifest
            and result.editor_action == self.action
            and result.choice == self.choice
        )

    def current(self, project: Project | None) -> bool:
        if project is None or project is not self.project:
            return False
        return project.root == self.root and project.manifest is self.manifest


class DashboardEditors(QObject):
    """Own presentation context and the latest delivered choices, never the worker."""

    def __init__(self, page: Dashboard) -> None:
        super().__init__(page)
        self.page = page
        self._pending: _Request | None = None
        self._choices: tuple[_Request, PreparedEditors] | None = None

    @property
    def pending(self) -> bool:
        return self._pending is not None

    @property
    def choices(self) -> PreparedEditors | None:
        """The latest delivered choices, only while their project is unchanged and shown."""
        kept = self._choices
        if kept is None or not kept[0].current(self.page.shown_project):
            return None
        return kept[1]

    def clear(self) -> None:
        """Retire presentation context and choices (another project, or one reloaded)."""
        self._pending = self._choices = None

    def prepare(self, document: Path) -> None:
        """Ask for choices for ``document``; read-only projects may prepare (reading only)."""
        project = self.page.shown_project
        if project is None or not self.page.inspectable:
            return
        self._choices = None
        request = _Request(project, project.root, project.manifest, "prepare")
        self._start(request, lambda: self.page.services.start_prepare_editors(document))

    def open(self, choice: EditorChoice) -> None:
        """Open ``choice`` from the current delivered choices; the owner re-checks it."""
        project = self.page.shown_project
        prepared = self.choices
        if project is None or prepared is None or not self.page.mutable:
            return
        labels = [option.label for option in prepared.options if option.choice == choice]
        if len(labels) != 1:
            return
        request = _Request(project, project.root, project.manifest, "open", choice, labels[0])
        self._start(request, lambda: self.page.services.start_open_editor(prepared, choice))

    def _start(self, request: _Request, start: Callable[[], bool]) -> None:
        self._pending = request  # busy/completion callbacks can run inside the start call
        doing = "Finding editors…" if request.action == "prepare" else f"Opening {request.label}…"
        self.page.show_launch_note(doing)
        try:
            started = start()
        except CTStudioError as exc:
            self._pending = None
            self.page.show_launch_problem(exc)
            return
        if not started and self._pending is request and not self.page.services.launch.busy:
            self._pending = None
            self.page.show_launch_note("The editor request did not start. Try again.")

    def completed(self, result: LaunchResult) -> None:
        """A joined editor result for the shown project: keep choices, show the outcome."""
        request = self._pending
        if request is None or not request.matches(result):
            return
        self._pending = None
        if isinstance(result.receipt, PreparedEditors):  # `choices` re-checks the project
            self._choices = (request, result.receipt)
        label = request.label
        text = describe_editor(result, label) if label else describe_launch(result)
        self.page.show_launch_note(text)
