"""P5-T03i: joined launch worker, exact results, errors and shutdown delivery boundaries."""

from __future__ import annotations

import threading
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from launch_controller_helpers import LaunchWork, own_workers, writable_project
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy
from pytestqt.qtbot import QtBot

from ctstudio.core.errors import ProjectError, ToolNotFound
from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import THREAD_NAME, LaunchController, LaunchResult

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def result_of(spy: QSignalSpy, index: int = 0) -> LaunchResult:
    assert spy.count() > index, "no launch result was delivered"  # at() past the end crashes
    payload = spy.at(index)[0]
    assert isinstance(payload, LaunchResult)
    return payload


@pytest.mark.parametrize("component", [None, "kcl"])
def test_joined_dispatch_keeps_busy_and_exact_context(
    qtbot: QtBot, tmp_path: Path, component: str | None
) -> None:
    project = writable_project(tmp_path)
    root, manifest = project.root, project.manifest
    work = LaunchWork()
    owner = LaunchController(blender=work, folders=work)
    done, busy = QSignalSpy(owner.completed), QSignalSpy(owner.busy_changed)
    delivered: list[threading.Thread] = []
    owner.completed.connect(lambda _result: delivered.append(threading.current_thread()))
    baseline = own_workers()
    try:
        assert owner.start(project, component)
        assert work.entered.wait(5)
        assert owner.busy
        assert not owner.start(project, "objects")  # one request at a time
        assert len(work.calls) == 1
        called, called_component, thread = work.calls[0]
        assert called is project and called_component == component
        assert thread is not threading.main_thread() and thread.name == THREAD_NAME
        assert done.count() == 0 and busy.count() == 1 and busy.at(0) == [True]
        project.root = root / "changed"  # the result keeps the root captured at start
        work.gate.set()
        qtbot.waitUntil(lambda: not owner.busy)
        assert not thread.is_alive()  # joined before busy ended
        assert done.count() == 1
        result = result_of(done)
        assert result.project is project and result.root == root
        assert result.manifest is manifest and result.component_id == component
        expected = work.blender_receipt if component is None else work.folder_receipt
        assert result.receipt is expected and result.error is None
        assert delivered == [threading.main_thread()]
        assert busy.count() == 2 and busy.at(1) == [False]
        with pytest.raises(FrozenInstanceError):
            result.component_id = "different"  # type: ignore[misc]  # proving frozen at runtime
        assert own_workers() == baseline
    finally:
        project.root = root
        work.gate.set()
        assert owner.shutdown(10)
        project.close()


@pytest.mark.parametrize(
    "error",
    [
        ToolNotFound("Blender", "Set Blender's path on the Tools page."),
        ProjectError("Folder is missing.", hint="Build first."),
        RuntimeError("unexpected crash"),
        KeyboardInterrupt(),
    ],
    ids=["tool", "project", "crash", "interrupt"],
)
def test_every_worker_failure_reaches_the_ui_once_and_releases_the_owner(
    qtbot: QtBot, tmp_path: Path, error: BaseException
) -> None:
    project = writable_project(tmp_path)
    work = LaunchWork()
    work.error = error
    work.gate.set()
    owner = LaunchController(blender=work, folders=work)
    done = QSignalSpy(owner.completed)
    try:
        assert owner.start(project, "kcl")
        for _ in range(500):  # bounded: a stranded owner fails an assertion, not a timeout
            if not owner.busy:
                break
            qtbot.wait(10)
        assert not owner.busy, "the worker failure stranded the owner"
        assert done.count() == 1
        result = result_of(done)
        assert result.error is error  # identity preserved, not re-wrapped
        assert result.receipt is None and result.component_id == "kcl"
        assert not own_workers()
        assert owner.start(project, None)  # the owner is free again
        qtbot.waitUntil(lambda: not owner.busy)
    finally:
        assert owner.shutdown(10)
        project.close()


def test_shutdown_timeout_keeps_ownership_then_drops_the_queued_result(
    qtbot: QtBot, tmp_path: Path
) -> None:
    project = writable_project(tmp_path)
    work = LaunchWork()
    owner = LaunchController(blender=work, folders=work)
    done, busy = QSignalSpy(owner.completed), QSignalSpy(owner.busy_changed)
    try:
        assert owner.start(project)
        assert work.entered.wait(5)
        assert not owner.shutdown(0)  # still running: keep the owner and its worker
        assert owner.busy and len(own_workers()) == 1
        work.gate.set()
        assert owner.shutdown(10)
        assert not owner.busy and not own_workers()
        QCoreApplication.sendPostedEvents()  # the joined worker's queued delivery, now
        assert done.count() == 0
        assert [busy.at(i) for i in range(busy.count())] == [[True], [False]]
    finally:
        work.gate.set()
        assert owner.shutdown(10)
        project.close()


def test_a_refused_thread_start_reports_and_frees_the_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = writable_project(tmp_path)
    work = LaunchWork()
    owner = LaunchController(blender=work, folders=work)
    done, busy = QSignalSpy(owner.completed), QSignalSpy(owner.busy_changed)
    refused = RuntimeError("can't start new thread")

    def refuse(_self: threading.Thread) -> None:
        raise refused

    monkeypatch.setattr(threading.Thread, "start", refuse)
    try:
        assert not owner.start(project, "kcl")
        assert not owner.busy and not work.calls
        assert done.count() == 1
        error = result_of(done).error
        assert isinstance(error, ProjectError) and error.hint
        assert error.__cause__ is refused
        assert [busy.at(i) for i in range(busy.count())] == [[True], [False]]
    finally:
        monkeypatch.undo()
        assert owner.shutdown(10)
        project.close()


def test_an_old_queued_result_never_reports_as_the_next_request(
    qtbot: QtBot, tmp_path: Path
) -> None:
    project = writable_project(tmp_path)
    first, second = LaunchWork(), LaunchWork()
    first.gate.set()
    owner = LaunchController(blender=second, folders=first)
    done = QSignalSpy(owner.completed)
    try:
        assert owner.start(project, "kcl")
        assert first.entered.wait(5)
        assert owner.shutdown(10)  # joined; its result is still queued, undelivered
        assert owner.start(project, None)  # the next request starts before that delivery
        assert second.entered.wait(5)
        QCoreApplication.sendPostedEvents()  # the first worker was joined; deliver it now
        assert owner.busy and done.count() == 0
        second.gate.set()
        qtbot.waitUntil(lambda: not owner.busy)
        assert done.count() == 1 and result_of(done).receipt is second.blender_receipt
    finally:
        second.gate.set()
        assert owner.shutdown(10)
        project.close()


def test_delivery_joins_the_worker_before_reporting(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = writable_project(tmp_path)
    work = LaunchWork()
    work.gate.set()
    owner = LaunchController(blender=work, folders=work)
    events: list[str] = []
    original_join = threading.Thread.join

    def recording_join(thread: threading.Thread, timeout: float | None = None) -> None:
        if thread.name == THREAD_NAME:
            events.append("joined")
        original_join(thread, timeout)

    monkeypatch.setattr(threading.Thread, "join", recording_join)
    owner.completed.connect(lambda _result: events.append("completed"))
    owner.busy_changed.connect(lambda busy: events.append(f"busy={busy}"))
    try:
        assert owner.start(project, "kcl")
        qtbot.waitUntil(lambda: "completed" in events)
        assert events == ["busy=True", "joined", "busy=False", "completed"]
    finally:
        monkeypatch.undo()
        assert owner.shutdown(10)
        project.close()


def test_a_closed_project_still_runs_and_reports_its_own_context(
    qtbot: QtBot, tmp_path: Path
) -> None:
    project: Project = writable_project(tmp_path)
    project.close()
    work = LaunchWork()
    work.gate.set()
    owner = LaunchController(blender=work, folders=work)
    done = QSignalSpy(owner.completed)
    assert owner.start(project, "kcl")  # services decide eligibility; the owner only runs it
    qtbot.waitUntil(lambda: not owner.busy)
    assert result_of(done).project is project
    assert owner.shutdown(10)
