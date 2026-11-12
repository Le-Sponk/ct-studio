"""Outside-edit requests retain project ownership until joined, including failure and close."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy
from pytestqt.qtbot import QtBot
from reconcile_helpers import outcome, owned, settled

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import LaunchResult

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_one_request_owns_the_project_and_every_other_mutating_entry_waits(
    qtbot: QtBot, tmp_path: Path, action: str
) -> None:
    with owned(tmp_path) as (services, project, work):
        assert services.start_reconcile("kcl", action)
        assert work.entered.wait(5)
        calls = [
            lambda: services.start_reconcile("kcl", "discard"),
            lambda: services.start_assign("kcl", tmp_path / "missing.kcl"),
            lambda: services.start_build(),
            lambda: services.start_launch("kcl"),
            services.close_project,
            lambda: services.open_project(tmp_path / "other"),
            lambda: services.adopt(project),
        ]
        for call in calls:
            error = outcome(call)
            assert isinstance(error, ProjectError), f"owner bypassed: {error!r}"
            assert "still finishing" in error.user_message
        assert outcome(lambda: services.shutdown(0)) is False
        assert services.project is project and project.lock is not None
        incoming = Project.create(tmp_path / "Incoming", "Incoming")
        assert isinstance(outcome(lambda: services.adopt(incoming)), ProjectError)
        assert incoming.read_only
        assert len(work.calls) == 1
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy)
        assert services.project is project and project.lock is not None


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize(
    "error", [ProjectError("No.", hint="Fix this."), RuntimeError(), KeyboardInterrupt()]
)
def test_worker_failure_identity_reaches_the_ui_and_owner_can_retry(
    qtbot: QtBot, tmp_path: Path, action: str, error: BaseException
) -> None:
    with owned(tmp_path) as (services, project, work):
        manifest = project.manifest
        work.error = error
        work.gate.set()
        done = QSignalSpy(services.launch.completed)
        assert services.start_reconcile("kcl", action)
        assert settled(qtbot, lambda: not services.launch.busy)
        assert done.count() == 1
        payload = done.at(0)[0]
        assert isinstance(payload, LaunchResult)
        assert payload.error is error and payload.receipt is None
        assert payload.edit_action == action
        assert project.manifest is manifest
        work.error = None
        assert services.start_reconcile("kcl", action)
        assert settled(qtbot, lambda: not services.launch.busy)
        assert done.count() == 2
        result = done.at(1)[0]
        assert isinstance(result, LaunchResult) and result.receipt is not None


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_shutdown_joins_then_drops_the_queued_outside_edit_result(
    qtbot: QtBot, tmp_path: Path, action: str
) -> None:
    with owned(tmp_path) as (services, project, work):
        owner = services.launch
        done = QSignalSpy(owner.completed)
        assert services.start_reconcile("kcl", action)
        assert work.entered.wait(5)
        work.gate.set()
        assert outcome(lambda: owner.shutdown(10)) is True
        assert not owner.busy
        QCoreApplication.sendPostedEvents()
        assert done.count() == 0
        assert not work.calls[0][3].is_alive()
        assert project.lock is not None


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_editing_and_building_refuse_before_outside_edit_work(
    qtbot: QtBot, tmp_path: Path, action: str
) -> None:
    with owned(tmp_path) as (services, _project, work):
        services.editing = True
        error = outcome(lambda: services.start_reconcile("kcl", action))
        assert isinstance(error, ProjectError) and "details" in error.user_message
        services.editing = False
        # Hold the real build owner using the existing test planner/runner (no tool work).
        from build_fakes import FakeBuilds

        from ctstudio.gui.build_controller import BuildController

        builds = FakeBuilds()
        builds.gate = threading.Event()
        services.build = BuildController(plan=builds.plan, build=builds.run)
        try:
            assert services.start_build()
            assert services.build.running
            error = outcome(lambda: services.start_reconcile("kcl", action))
            assert isinstance(error, ProjectError) and "being built" in error.user_message
            assert not work.calls and not services.launch.busy
        finally:
            builds.gate.set()
            assert services.build.shutdown(10)


def test_invalid_action_on_direct_controller_cannot_fall_through_to_discard(tmp_path: Path) -> None:
    with owned(tmp_path) as (services, project, work):
        error = outcome(lambda: services.launch.reconcile(project, "kcl", "erase"))
        assert isinstance(error, ProjectError) and error.hint
        assert not services.launch.busy and not work.calls


def test_a_refused_start_names_its_action_without_losing_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned(tmp_path) as (services, _project, work):
        refused = RuntimeError("can't start new thread")

        def refuse(_thread: threading.Thread) -> None:
            raise refused

        done = QSignalSpy(services.launch.completed)
        with monkeypatch.context() as patch:
            patch.setattr(threading.Thread, "start", refuse)
            assert not services.start_reconcile("kcl", "lock")
        assert not services.launch.busy and not work.calls
        assert done.count() == 1
        payload = done.at(0)[0]
        assert isinstance(payload, LaunchResult) and payload.edit_action == "lock"
        assert isinstance(payload.error, ProjectError) and payload.error.__cause__ is refused
