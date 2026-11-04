"""Shared dashboard test setup; all projects and settings are temporary and synthetic."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from build_fakes import FakeBuilds
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.project.project import Project
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.dashboard import Dashboard


@contextmanager
def overview(
    qtbot: QtBot, folder: Path, builds: FakeBuilds | None = None
) -> Iterator[tuple[Dashboard, AppServices, Project]]:
    services = quiet_services(builds)
    project = Project.create(folder / "Pistë 日本", "Pistë 日本")
    services.adopt(project)
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        page.resize(900, 800)
        page.show()
        qtbot.waitUntil(lambda: not page.busy)
        yield page, services, project
    finally:
        assert services.shutdown(10)
