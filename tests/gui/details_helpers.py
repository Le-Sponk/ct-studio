"""Synthetic, gated project-details service shared by the dialog/window tests."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.project.project import Project
from ctstudio.gui.project_details import DetailsSnapshot, ProjectDetailsService
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.project_details import ProjectDetailsDialog


class DetailsWork(ProjectDetailsService):
    def __init__(self) -> None:
        self.load_gate: threading.Event | None = None
        self.save_gate: threading.Event | None = None
        self.load_error: Exception | None = None
        self.save_error: Exception | None = None
        self.calls: list[tuple[str, threading.Thread]] = []

    def load(self, project: Project) -> DetailsSnapshot:
        self.calls.append(("load", threading.current_thread()))
        gate = self.load_gate
        if gate is not None:
            assert gate.wait(10)
        if self.load_error is not None:
            raise self.load_error
        return super().load(project)

    def save(
        self, project: Project, snapshot: DetailsSnapshot, slot: str, blend: Path | None
    ) -> DetailsSnapshot:
        self.calls.append(("save", threading.current_thread()))
        gate = self.save_gate
        if gate is not None:
            assert gate.wait(10)
        if self.save_error is not None:
            raise self.save_error
        return super().save(project, snapshot, slot, blend)


@contextmanager
def details(
    qtbot: QtBot, folder: Path, work: DetailsWork | None = None
) -> Iterator[tuple[ProjectDetailsDialog, AppServices, Project, DetailsWork]]:
    services = quiet_services()
    project = Project.create(folder / "Détails 日本", "Détails 日本")
    services.adopt(project)
    work = work if work is not None else DetailsWork()
    dialog = ProjectDetailsDialog(services, service=work)
    qtbot.addWidget(dialog)
    dialog.open()
    try:
        qtbot.waitUntil(lambda: not dialog.busy)
        yield dialog, services, project, work
    finally:
        for gate in (work.load_gate, work.save_gate):
            if gate is not None:
                gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        dialog.reject()
        assert services.shutdown(10)
