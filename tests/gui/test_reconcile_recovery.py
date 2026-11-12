"""Saved outside-edit snapshots are delivered only after the action's worker joins."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# The inline worker probe turns a lost completion into a primary assertion, not a thread warning.
import threading
from pathlib import Path

import pytest
from assign_helpers import kcl_bytes
from launch_controller_helpers import LaunchWork
from PySide6.QtCore import QCoreApplication
from pytestqt.qtbot import QtBot
from reconcile_bootstrap_helpers import BootstrapPause
from reconcile_helpers import EditWork, outcome, owned, settled

from ctstudio.core.components.assign import Assigned, assign_file
from ctstudio.core.components.edited import discard_edit, lock_as_manual
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import LaunchResult, _Context, _Relay, _Work
from ctstudio.gui.project_details import DetailsSnapshot, ProjectDetailsService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_real_action_returns_saved_bytes_without_publishing(
    qtbot: QtBot, tmp_path: Path, action: str
) -> None:
    with owned(tmp_path) as (services, project, work):
        original = project.manifest
        results: list[LaunchResult] = []
        services.launch.completed.connect(results.append)
        assert services.start_reconcile("kcl", action)
        work.gate.set()
        assert settled(qtbot, lambda: bool(results))
        result = results[0]
        assert hasattr(result, "saved"), "joined result lost the saved manifest"
        saved = result.saved
        assert isinstance(saved, DetailsSnapshot)
        assert saved.root == project.root.resolve()
        assert saved.raw == project.manifest_path.read_bytes()
        assert saved.manifest.components.kcl.mode == ("manual" if action == "lock" else "auto")
        assert result.recovery_error is None and result.error is None
        assert result.manifest is original and project.manifest is original
        if action == "lock":
            assert isinstance(result.receipt, Assigned)
            assert result.receipt.manifest == saved.manifest
        else:
            assert isinstance(result.receipt, Path) and result.receipt.is_dir()
            backup = result.receipt / ".ctstudio/stage/course.kcl"
            assert backup.is_file()


@pytest.mark.parametrize("kind", [RuntimeError, KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("hook", ["_set_ident", "_set_native_id"])
@pytest.mark.parametrize("action", ["lock", "discard"])
def test_startup_error_keeps_post_attempt_snapshot(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: type[BaseException],
    hook: str,
    action: str,
) -> None:
    with owned(tmp_path) as (services, project, work):
        original = project.manifest
        error = kind("native startup acknowledgement interrupted")
        pause = BootstrapPause(services.launch, error, hook)
        results: list[LaunchResult] = []
        services.launch.completed.connect(results.append)
        try:
            with monkeypatch.context() as patch:
                pause.install(patch)
                accepted = outcome(lambda: services.start_reconcile("kcl", action))
            assert accepted is False and services.launch.busy
            assert results == []
        finally:
            pause.finish(work.gate)
        assert settled(qtbot, lambda: bool(results))
        result = results[0]
        assert result.error is error and result.receipt is None
        assert result.saved is not None, "startup error erased actual saved state"
        assert result.saved.raw == project.manifest_path.read_bytes()
        assert result.saved.manifest.components.kcl.mode == (
            "manual" if action == "lock" else "auto"
        )
        assert result.recovery_error is None
        assert project.manifest is original and result.manifest is original


def _inline(project: Project, action: str) -> object:
    context = _Context(
        project,
        project.root,
        project.manifest,
        None if action == "blender" else "kcl",
        source=project.root / "own.kcl" if action == "assign" else None,
        edit_action=action if action in ("lock", "discard") else None,
    )
    results: list[LaunchResult] = []
    relay = _Relay()

    def done(_generation: int, receipt: object, error: object) -> None:
        results.append(context.result(receipt, error))

    relay.done.connect(done)
    launch = LaunchWork()
    launch.gate.set()
    worker = _Work(
        1,
        relay,
        launch,
        launch,
        assign_file,
        lock_as_manual,
        discard_edit,
    )
    raised = outcome(lambda: worker.run(context))
    if raised is not None:
        return raised
    assert len(results) == 1, "worker did not send exactly one completion"
    return results[0]


@pytest.mark.parametrize("kind", [ProjectError, RuntimeError, KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("action", ["lock", "discard"])
def test_recovery_read_failure_is_a_separate_result(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: type[BaseException],
    action: str,
) -> None:
    error = kind("saved manifest could not be read")

    def unreadable(_service: ProjectDetailsService, _project: Project) -> DetailsSnapshot:
        raise error

    with owned(tmp_path) as (_services, project, _work):
        original = project.manifest
        monkeypatch.setattr(ProjectDetailsService, "load", unreadable)
        result = _inline(project, action)
        assert isinstance(result, LaunchResult), "recovery read failure lost the completion"
        assert result.error is None and result.receipt is not None
        assert result.saved is None and result.recovery_error is error
        assert project.manifest is original


@pytest.mark.parametrize("kind", [ProjectError, KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize("read_fails", [False, True])
def test_post_write_error_and_read_error_are_not_confused(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: type[BaseException],
    action: str,
    read_fails: bool,
) -> None:
    primary, secondary = kind("after write"), RuntimeError("during read")
    real_lock, real_discard = EditWork.lock, EditWork.discard

    def lock(work: EditWork, project: Project, part: str) -> Assigned:
        real_lock(work, project, part)
        raise primary

    def discard(work: EditWork, project: Project, part: str) -> Path:
        real_discard(work, project, part)
        raise primary

    def unreadable(_service: ProjectDetailsService, _project: Project) -> DetailsSnapshot:
        raise secondary

    monkeypatch.setattr(EditWork, action, lock if action == "lock" else discard)
    if read_fails:
        monkeypatch.setattr(ProjectDetailsService, "load", unreadable)
    with owned(tmp_path) as (services, project, work):
        original = project.manifest
        results: list[LaunchResult] = []
        services.launch.completed.connect(results.append)
        assert services.start_reconcile("kcl", action)
        work.gate.set()
        assert settled(qtbot, lambda: bool(results))
        result = results[0]
        assert result.error is primary and result.receipt is None
        assert result.project is project and project.manifest is original
        if read_fails:
            assert result.saved is None and result.recovery_error is secondary
        else:
            assert result.saved is not None and result.recovery_error is None
            assert result.saved.raw == project.manifest_path.read_bytes()
            assert result.saved.manifest.components.kcl.mode == (
                "manual" if action == "lock" else "auto"
            )
        if action == "lock":
            assert (project.root / "files/course.kcl").is_file()
        else:
            assert not (project.root / ".ctstudio/stage/course.kcl").exists()


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize("invalidate", [False, True])
def test_saved_read_stays_on_the_owned_worker_until_join(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    invalidate: bool,
) -> None:
    entered, release = threading.Event(), threading.Event()
    calls: list[threading.Thread] = []
    real_load = ProjectDetailsService.load

    def reading(service: ProjectDetailsService, project: Project) -> DetailsSnapshot:
        calls.append(threading.current_thread())
        entered.set()
        assert release.wait(10), "recovery reader was not released"
        return real_load(service, project)

    monkeypatch.setattr(ProjectDetailsService, "load", reading)
    with owned(tmp_path) as (services, project, work):
        original = project.manifest
        results: list[LaunchResult] = []
        services.launch.completed.connect(results.append)
        try:
            assert services.start_reconcile("kcl", action)
            work.gate.set()
            assert settled(qtbot, entered.is_set)
            assert len(work.calls) == 1, "saved state was read before the action ran"
            assert calls == [work.calls[0][3]] and calls[0] is not threading.current_thread()
            assert services.launch.busy and results == []
            assert outcome(lambda: services.launch.shutdown(0)) is False
            assert isinstance(outcome(services.close_project), ProjectError)
            assert project.manifest is original
            with Project.open(project.root) as other:
                assert other.read_only, "recovery released the writer lock"
        finally:
            release.set()
        if invalidate:
            assert services.launch.shutdown(10)
            QCoreApplication.sendPostedEvents()
            assert results == [], "invalidated recovery was published"
        else:
            assert settled(qtbot, lambda: bool(results))
            assert len(results) == 1 and results[0].saved is not None
            assert not calls[0].is_alive(), "snapshot arrived before its worker joined"
        assert project.manifest is original


@pytest.mark.parametrize("operation", ["assign", "blender", "folder"])
def test_other_request_kinds_do_not_read_recovery_state(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    reads: list[Project] = []

    def unexpected(_service: ProjectDetailsService, project: Project) -> DetailsSnapshot:
        reads.append(project)
        raise AssertionError("non-edit request read recovery state")

    monkeypatch.setattr(ProjectDetailsService, "load", unexpected)
    with owned(tmp_path) as (_services, project, _work):
        (project.root / "own.kcl").write_bytes(kcl_bytes())
        result = _inline(project, operation)
        assert isinstance(result, LaunchResult) and result.receipt is not None
        assert result.error is None and reads == []
        assert result.saved is None and result.recovery_error is None


@pytest.mark.parametrize("kind", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_unstarted_request_does_not_read_saved_state(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: type[BaseException],
) -> None:
    reads: list[Project] = []
    error = kind("native thread was never created")

    def unexpected(_service: ProjectDetailsService, project: Project) -> DetailsSnapshot:
        reads.append(project)
        raise AssertionError("unstarted request read recovery state")

    def unstarted(_thread: threading.Thread) -> None:
        raise error

    with owned(tmp_path) as (services, _project, work):
        results: list[LaunchResult] = []
        services.launch.completed.connect(results.append)
        with monkeypatch.context() as patch:
            patch.setattr(ProjectDetailsService, "load", unexpected)
            patch.setattr(threading.Thread, "start", unstarted)
            accepted = outcome(lambda: services.start_reconcile("kcl", "lock"))
        assert accepted is False and not services.launch.busy
        assert len(results) == 1 and results[0].error is not None
        assert work.calls == [] and reads == []
        assert results[0].saved is None and results[0].recovery_error is None


@pytest.mark.parametrize("damage", ["missing", "malformed"])
def test_damaged_saved_manifest_is_not_replaced_by_the_captured_input(
    qtbot: QtBot,
    tmp_path: Path,
    damage: str,
) -> None:
    with owned(tmp_path) as (services, project, work):
        original = project.manifest
        if damage == "missing":
            project.manifest_path.unlink()
        else:
            project.manifest_path.write_bytes(b"[not valid TOML")
        results: list[LaunchResult] = []
        services.launch.completed.connect(results.append)
        assert services.start_reconcile("kcl", "lock")
        work.gate.set()
        assert settled(qtbot, lambda: bool(results))
        result = results[0]
        assert result.saved is None and isinstance(result.recovery_error, ProjectError)
        assert isinstance(result.error, ProjectError) and result.receipt is None
        assert result.error is not result.recovery_error
        assert project.manifest is original
