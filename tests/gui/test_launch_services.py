"""P5-T03i: AppServices launch eligibility and project-lock guards (in-memory, no I/O)."""

from __future__ import annotations

from pathlib import Path

import pytest
from launch_controller_helpers import outcome, own_workers, owned_launch
from PySide6.QtTest import QSignalSpy
from pytestqt.qtbot import QtBot

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.views.project_details import ProjectDetailsDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("component", [None, "kcl", "track_info", "posteffect"])
def test_start_launch_dispatches_the_current_project(
    qtbot: QtBot, tmp_path: Path, component: str | None
) -> None:
    with owned_launch(tmp_path) as (services, project, work):
        qtbot.waitUntil(lambda: not services.status.busy)
        done = QSignalSpy(services.launch.completed)
        assert services.start_launch(component)
        assert services.launch.busy  # owned from the moment it starts
        work.gate.set()
        qtbot.waitUntil(lambda: done.count() == 1)
        assert not services.launch.busy
        payload = done.at(0)[0]
        assert isinstance(payload, LaunchResult)
        assert payload.project is project and payload.component_id == component
        assert work.calls[0][0] is project


def refusal(services_call: object) -> ProjectError:
    assert callable(services_call)
    with pytest.raises(ProjectError) as caught:
        services_call()
    assert caught.value.hint  # every refusal says what to do next
    return caught.value


def test_refusals_explain_and_start_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path / "a", source=False) as (services, _project, work):
        assert "checked" in refusal(services.start_launch).user_message  # status still busy
        qtbot.waitUntil(lambda: not services.status.busy)
        assert "no Blender source" in refusal(services.start_launch).user_message
        assert "unknown" in refusal(lambda: services.start_launch("nope")).user_message
        services.editing = True
        assert "details" in refusal(lambda: services.start_launch("kcl")).user_message
        services.editing = False
        assert not work.calls and not services.launch.busy
        services.close_project()
        assert "No project" in refusal(services.start_launch).user_message


def test_read_only_projects_may_reveal_folders_but_not_launch_blender(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with owned_launch(tmp_path) as (services, project, work):
        qtbot.waitUntil(lambda: not services.status.busy)
        viewer = Project.open(project.root)  # the lock is held, so this copy is read-only
        services.project = viewer
        try:
            assert viewer.read_only
            assert "read-only" in refusal(services.start_launch).user_message
            work.gate.set()
            assert services.start_launch("kcl")
            qtbot.waitUntil(lambda: not services.launch.busy)
            assert [(call[0], call[1]) for call in work.calls] == [(viewer, "kcl")]
        finally:
            services.project = project


def test_a_busy_launch_keeps_the_project_and_lock(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path) as (services, project, work):
        qtbot.waitUntil(lambda: not services.status.busy)
        assert services.start_launch("kcl")
        assert work.entered.wait(5)
        assert "still finishing" in refusal(lambda: services.start_launch("objects")).user_message
        assert len(work.calls) == 1  # the duplicate started nothing
        assert "still finishing" in refusal(services.close_project).user_message
        assert "still finishing" in refusal(lambda: services.start_launch(None)).user_message
        with pytest.raises(ProjectError):
            services.open_project(tmp_path / "elsewhere")
        incoming = Project.create(tmp_path / "Incoming", "Incoming")
        with pytest.raises(ProjectError):
            services.adopt(incoming)
        assert incoming.read_only  # given back, not left locked by nobody
        with pytest.raises(ProjectError):
            services.adopt(project)  # the same project: refused but not closed
        assert services.project is project and not project.read_only
        assert outcome(lambda: services.shutdown(0)) is False  # reports; never raises
        assert services.project is project and not project.read_only
        assert services.launch.busy  # ownership kept, not abandoned
        work.gate.set()
        assert services.shutdown(10) is True
        assert services.project is None and project.read_only
        assert not own_workers()
        with Project.open(project.root) as again:
            assert not again.read_only


def test_project_details_cannot_open_during_a_launch(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path) as (services, _project, work):
        qtbot.waitUntil(lambda: not services.status.busy)
        assert services.start_launch("kcl")
        assert work.entered.wait(5)
        dialog = ProjectDetailsDialog(services)
        qtbot.addWidget(dialog)
        assert not services.editing  # it did not take the edit ownership
        assert "cannot be edited now" in dialog.problem.text()
        assert not dialog.save_button.isEnabled()
        work.gate.set()
        qtbot.waitUntil(lambda: not services.launch.busy)
        dialog.reject()
