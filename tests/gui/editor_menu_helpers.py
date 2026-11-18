"""Dashboards whose status check reports every part ready and whose editor work is held (e1)."""

from __future__ import annotations

from collections.abc import Collection, Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

from editor_owner_helpers import EditorWork, outcome
from editor_request_helpers import dashboard_for, no_tools, settled
from launch_controller_helpers import LaunchWork, writable_project
from PySide6.QtCore import QCoreApplication, QEvent
from pytestqt.qtbot import QtBot

from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.components.state import GENERATED_DIR
from ctstudio.core.components.status import ComponentStatus, ProjectLike, State, single_file
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.editor_launch import EditorLaunchService
from ctstudio.gui.launch_controller import LaunchController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.dashboard import Dashboard
from ctstudio.gui.views.editor_choices import EditorChoices

MODEL = "course_model.brres"


def all_ready(project: ProjectLike, _tools: Collection[str]) -> Mapping[str, ComponentStatus]:
    """Every part Ready; a single-file part is present exactly when its file exists."""
    return {
        spec.id: ComponentStatus(
            State.READY, present=(file := single_file(spec, project)) is not None and file.is_file()
        )
        for spec in COMPONENTS
    }


def ready_services(
    work: EditorLaunchService, *, build: BuildController | None = None
) -> tuple[AppServices, LaunchWork]:
    other = LaunchWork()
    other.gate.set()
    status = StatusService(evaluate=all_ready, find_tools=no_tools)
    controller = LaunchController(blender=other, folders=other, editors=work)
    services = AppServices(launch=controller, status=status, build=build or BuildController())
    return services, other


@contextmanager
def menu_board(
    qtbot: QtBot, folder: Path, work: EditorLaunchService | None = None
) -> Generator[tuple[Dashboard, AppServices, Project, EditorWork, Path]]:
    """A shown dashboard for a writable project whose course model exists (synthetic)."""
    folder.mkdir(parents=True, exist_ok=True)
    held = EditorWork()
    services, _other = ready_services(work or held)
    project = writable_project(folder)
    model = project.root / GENERATED_DIR / MODEL
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"synthetic only")
    services.adopt(project)
    try:
        page = dashboard_for(qtbot, services, project)
        assert settled(qtbot, lambda: page.cards["course_model"].can_open()), "never checked"
        yield page, services, project, held, model
    finally:
        held.gate.set()
        services.editing = False
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def offered(qtbot: QtBot, page: Dashboard) -> EditorChoices:
    """Wait (bounded, never raising) for the choice dialog and return it."""
    assert settled(qtbot, lambda: page.editors.dialog is not None), "no choice dialog appeared"
    dialog = page.editors.dialog
    assert dialog is not None
    return dialog


def flush_deletes() -> None:
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def row_texts(dialog: EditorChoices) -> list[str]:
    return [dialog.choices.item(row).text() for row in range(dialog.choices.count())]
