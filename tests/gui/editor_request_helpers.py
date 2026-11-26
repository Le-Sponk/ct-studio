"""App services and dashboards whose joined launch owner uses event-held editor work (d3)."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from editor_owner_helpers import DOCUMENT_NAME, EditorWork, outcome
from launch_controller_helpers import LaunchWork, writable_project
from pytestqt.qtbot import QtBot
from waits import settled as settled  # the one shared wait; re-exported for older imports

from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.launch_controller import LaunchController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.dashboard import Dashboard


def no_tools(**_kwargs: object) -> frozenset[str]:
    return frozenset()


def editor_services(other: LaunchWork, work: EditorWork) -> AppServices:
    status = StatusService(evaluate=lambda _project, _tools: {}, find_tools=no_tools)
    controller = LaunchController(blender=other, folders=other, editors=work)
    return AppServices(launch=controller, status=status, build=BuildController())


@contextmanager
def owned_editors(
    folder: Path,
) -> Generator[tuple[AppServices, Project, Path, EditorWork, LaunchWork]]:
    """Current writable project with a synthetic document; workers are released on exit."""
    folder.mkdir(parents=True, exist_ok=True)
    other, work = LaunchWork(), EditorWork()
    services = editor_services(other, work)
    project = writable_project(folder)
    document = project.root / DOCUMENT_NAME
    document.write_bytes(b"synthetic only")
    services.adopt(project)
    try:
        yield services, project, document, work, other
    finally:
        work.gate.set()
        other.gate.set()
        services.editing = False
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def dashboard_for(qtbot: QtBot, services: AppServices, project: Project) -> Dashboard:
    page = Dashboard(services)
    qtbot.addWidget(page)
    page.set_project(project)
    page.resize(900, 800)
    page.show()
    assert settled(qtbot, lambda: not page.busy), "the dashboard's first check did not settle"
    return page
