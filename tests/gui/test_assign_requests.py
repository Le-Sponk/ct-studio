"""P5-T04b: AppServices.start_assign runs assign_file on the joined launch worker."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from assign_helpers import AssignWork, assign_services, kcl_bytes, write
from pytestqt.qtbot import QtBot

from ctstudio.core.components.assign import Assigned
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import THREAD_NAME, LaunchResult
from ctstudio.gui.services import AppServices

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def opened(services: AppServices, folder: Path) -> Project:
    project = Project.create(folder / "Pistë 日本", "Pistë 日本")
    services.adopt(project)
    return project


def finish(qtbot: QtBot, services: AppServices) -> list[LaunchResult]:
    results: list[LaunchResult] = []
    services.launch.completed.connect(results.append)
    qtbot.waitUntil(lambda: not services.launch.busy)
    return results


def test_assignment_runs_on_the_launch_worker_and_arrives_after_join(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = AssignWork()
    work.gate = threading.Event()
    services = assign_services(work)
    project = opened(services, tmp_path)
    qtbot.waitUntil(lambda: not services.status.busy)
    source = write(tmp_path / "Sources été" / "mine.kcl", kcl_bytes())
    results: list[LaunchResult] = []
    alive: list[bool] = []

    def record(result: object) -> None:
        assert isinstance(result, LaunchResult)
        alive.append(work.calls[0][3].is_alive())
        results.append(result)

    services.launch.completed.connect(record)
    try:
        assert services.start_assign("kcl", source, reference=False)
        assert services.launch.busy
        with pytest.raises(ProjectError, match="still finishing"):
            services.start_assign("kmp", source)  # one request at a time
        work.gate.set()
        qtbot.waitUntil(lambda: bool(results))
        assert not services.launch.busy
        [(part, given, reference, thread)] = work.calls
        assert (part, given, reference, thread.name) == ("kcl", source, False, THREAD_NAME)
        assert thread is not threading.main_thread()
        assert alive == [False], "the worker was joined before delivery"
        [result] = results
        receipt = result.receipt
        assert isinstance(receipt, Assigned)
        assert (result.component_id, result.source, result.reference, receipt.file) == (
            "kcl",
            source,
            False,
            "files/course.kcl",
        )
        assert (result.project, result.error) == (project, None)
        assert project.manifest.components.kcl.mode == "auto", (
            "the window publishes, not the worker"
        )
    finally:
        work.gate.set()
        assert services.shutdown(10)


@pytest.mark.parametrize(
    "error",
    [ProjectError("No.", hint="Do this."), RuntimeError("boom"), KeyboardInterrupt()],
    ids=["typed", "crash", "interrupt"],
)
def test_assignment_errors_reach_the_window(
    qtbot: QtBot, tmp_path: Path, error: BaseException
) -> None:
    work = AssignWork()
    work.error = error
    services = assign_services(work)
    opened(services, tmp_path)
    qtbot.waitUntil(lambda: not services.status.busy)
    try:
        results: list[LaunchResult] = []
        services.launch.completed.connect(results.append)
        assert services.start_assign("kcl", tmp_path / "x.kcl", reference=True)
        qtbot.waitUntil(lambda: not services.launch.busy)
        [result] = results
        assert result.error is error and result.receipt is None
        assert result.reference is True
    finally:
        assert services.shutdown(10)


def test_no_project_is_refused(tmp_path: Path) -> None:
    work = AssignWork()
    services = assign_services(work)
    with pytest.raises(ProjectError, match="No project is open"):
        services.start_assign("kcl", tmp_path / "x.kcl")
    assert work.calls == []


def test_a_read_only_project_is_refused(qtbot: QtBot, tmp_path: Path) -> None:
    work = AssignWork()
    services = assign_services(work)
    with Project.create(tmp_path / "Pistë", "Pistë") as holder:
        other = Project.open(holder.root)
        assert other.read_only
        services.adopt(other)
        qtbot.waitUntil(lambda: not services.status.busy)
        try:
            with pytest.raises(ProjectError) as caught:
                services.start_assign("kcl", tmp_path / "x.kcl")
            assert caught.value.user_message == "Cannot assign a file in a read-only project."
            assert work.calls == [] and not services.launch.busy
        finally:
            assert services.shutdown(10)


def test_an_unknown_part_is_refused(qtbot: QtBot, tmp_path: Path) -> None:
    work = AssignWork()
    services = assign_services(work)
    opened(services, tmp_path)
    qtbot.waitUntil(lambda: not services.status.busy)
    try:
        with pytest.raises(ProjectError, match="unknown"):
            services.start_assign("wheels", tmp_path / "x.kcl")
        assert work.calls == []
    finally:
        assert services.shutdown(10)


@pytest.mark.parametrize("busy", ["status", "editing", "launch"])
def test_other_work_is_waited_for(qtbot: QtBot, tmp_path: Path, busy: str) -> None:
    work = AssignWork()
    services = assign_services(work)
    opened(services, tmp_path)
    qtbot.waitUntil(lambda: not services.status.busy)
    gate = threading.Event()
    try:
        if busy == "status":
            assert services.project is not None
            services.status.request(services.project)
            assert services.status.busy
        elif busy == "editing":
            services.editing = True
        else:
            work.gate = gate
            assert services.start_assign("kcl", tmp_path / "x.kcl")
            work.calls.clear()
        with pytest.raises(ProjectError):
            services.start_assign("kmp", tmp_path / "y.kmp")
        assert work.calls == []
    finally:
        gate.set()
        services.editing = False
        qtbot.waitUntil(lambda: not services.launch.busy and not services.status.busy)
        assert services.shutdown(10)


def test_closing_waits_for_a_running_assignment(qtbot: QtBot, tmp_path: Path) -> None:
    work = AssignWork()
    work.gate = threading.Event()
    services = assign_services(work)
    project = opened(services, tmp_path)
    qtbot.waitUntil(lambda: not services.status.busy)
    source = write(tmp_path / "mine.kcl", kcl_bytes())
    try:
        assert services.start_assign("kcl", source)
        assert not services.shutdown(0.05)
        assert services.project is project and project.lock is not None
        with pytest.raises(ProjectError, match="still finishing"):
            services.close_project()
    finally:
        work.gate.set()
        assert services.shutdown(10)
    assert project.lock is None
    assert (project.root / "files" / "course.kcl").read_bytes() == kcl_bytes()
