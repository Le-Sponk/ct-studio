"""Native bootstrap and reentrant shutdown regressions; synthetic builds only."""

# pyright: reportPrivateUsage=false
# Inspect worker/token ownership and hold CPython bootstrap before its acknowledgement.

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest
from build_fakes import THREAD, project
from build_ownership_helpers import Ownership, outcome
from PySide6.QtCore import QCoreApplication

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["project"]


@pytest.fixture
def owned(qapp: object, tmp_path: Path) -> Iterator[Ownership]:
    made = Ownership(tmp_path)
    yield made
    made.close()


class BootstrapPause:
    """Hold a real native worker, then interrupt start's bootstrap acknowledgement wait."""

    def __init__(self, owned: Ownership, error: BaseException, hook: str) -> None:
        self.owned, self.error = owned, error
        self.hook = hook
        self.reached, self.release = threading.Event(), threading.Event()
        self.workers: list[threading.Thread] = []
        # Dynamic lookup keeps these CPython-only test hooks out of static Thread typing;
        # production uses public threading APIs and does not access private attributes.
        self.original_hook = cast(Callable[[threading.Thread], None], vars(threading.Thread)[hook])
        self.original_wait = threading.Event.wait

    def bootstrap(self, thread: threading.Thread) -> None:
        if thread.name == THREAD:
            self.workers.append(thread)
            self.reached.set()
            assert self.original_wait(self.release, 10)
        self.original_hook(thread)

    def wait(self, event: threading.Event, timeout: float | None = None) -> bool:
        worker = self.owned.controller._thread
        if worker is not None and event is vars(worker)["_started"]:
            assert self.original_wait(self.reached, 10)
            raise self.error
        return self.original_wait(event, timeout)

    def install(self, patch: pytest.MonkeyPatch) -> None:
        # Set class functions, not bound methods (the descriptor supplies thread/event).
        def bootstrap(thread: threading.Thread) -> None:
            self.bootstrap(thread)

        def wait(event: threading.Event, timeout: float | None = None) -> bool:
            return self.wait(event, timeout)

        patch.setattr(threading.Thread, self.hook, bootstrap)
        patch.setattr(threading.Event, "wait", wait)

    def assert_owned(self, result: object) -> None:
        worker = self.workers[0]
        assert (worker.ident is None) is (self.hook == "_set_ident")
        assert result is False
        assert self.owned.controller._thread is worker, "native bootstrap worker was abandoned"
        assert self.owned.controller.running
        assert self.owned.controller._cancels.current.cancelled
        assert self.owned.failed == [], "startup error published before join"
        assert self.owned.finished == []

    def assert_locked(self, service: AppServices, project: Project) -> None:
        assert outcome(lambda: self.owned.controller.shutdown(0)) is False
        assert outcome(lambda: self.owned.controller.shutdown(10)) is False
        assert outcome(lambda: service.shutdown(0)) is False
        assert isinstance(outcome(service.close_project), ProjectError)
        assert service.project is project
        assert not project.read_only
        assert not self.owned.controller.start(project)
        assert self.owned.fake.planned == []
        with Project.open(project.root) as contender:
            assert contender.read_only

    def finish(self, gate: threading.Event) -> None:
        self.release.set()
        gate.set()
        assert self.reached.wait(10)
        worker = self.workers[0]
        started = cast(threading.Event, vars(worker)["_started"])
        assert started.wait(10)
        worker.join(10)
        assert not worker.is_alive()
        QCoreApplication.sendPostedEvents()


@pytest.mark.parametrize("kind", [KeyboardInterrupt, SystemExit, RuntimeError])
@pytest.mark.parametrize("hook", ["_set_ident", "_set_native_id"])
def test_interrupted_native_bootstrap_keeps_cancelled_owner_and_project_lock(
    owned: Ownership,
    project: Project,
    monkeypatch: pytest.MonkeyPatch,
    kind: type[BaseException],
    hook: str,
) -> None:
    gate = owned.hold()
    error = kind("native created before bootstrap acknowledgement")
    pause = BootstrapPause(owned, error, hook)
    service = AppServices(build=owned.controller, status=StatusService())
    service.project = project
    try:
        with monkeypatch.context() as patch:
            pause.install(patch)
            result = outcome(lambda: owned.controller.start(project))
        pause.assert_owned(result)
        pause.assert_locked(service, project)
    finally:
        # Drain even an abandoned native worker, so RED cannot leak a thread or lock user.
        pause.finish(gate)
    assert owned.fake.cancels[0].cancelled
    owned.assert_failure(error)
    owned.assert_idle()
    owned.fake.gate = None
    assert owned.controller.start(project)
    owned.drain()
    assert len(owned.finished) == 1
    assert service.shutdown(10)
    with Project.open(project.root) as reopened:
        assert not reopened.read_only


def test_confirmed_native_creation_failure_allows_retry(
    owned: Ownership, project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = RuntimeError("synthetic native thread resource exhaustion")
    # Exercise Thread.start's real registry cleanup on both supported CPython versions.
    native_hook = (
        "_start_joinable_thread"
        if hasattr(threading, "_start_joinable_thread")
        else "_start_new_thread"
    )

    def fail(*_args: object, **_kwargs: object) -> None:
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(threading, native_hook, fail)
        result = outcome(lambda: owned.controller.start(project))
    assert result is False
    owned.assert_failure(error)
    owned.assert_idle()
    assert owned.controller.shutdown(0)
    assert owned.controller.start(project)
    owned.drain()
    assert len(owned.finished) == 1


def test_shutdown_refuses_callback_created_live_worker(owned: Ownership, project: Project) -> None:
    gate = owned.hold()
    assert owned.controller.start(project)
    first = owned.worker()
    restarts: list[object] = []

    def restart(running: bool) -> None:
        if running or restarts:
            return
        restarts.append("entered")
        owned.hold()
        restarts.append(outcome(lambda: owned.controller.start(project)))

    owned.controller.running_changed.connect(restart)
    try:
        gate.set()
        result = outcome(lambda: owned.controller.shutdown(10))
        assert restarts == ["entered", True]
        assert owned.worker() is not first
        assert owned.controller.running
        assert result is False, "shutdown reported success with a callback-created live worker"
    finally:
        owned.controller.running_changed.disconnect(restart)


def test_app_shutdown_returns_bool_and_keeps_lock_after_callback_restart(
    owned: Ownership, project: Project
) -> None:
    service = AppServices(build=owned.controller, status=StatusService())
    service.project = project
    gate = owned.hold()
    assert owned.controller.start(project)
    restarts: list[object] = []

    def restart(running: bool) -> None:
        if running or restarts:
            return
        restarts.append("entered")
        owned.hold()
        restarts.append(outcome(lambda: owned.controller.start(project)))

    owned.controller.running_changed.connect(restart)
    try:
        gate.set()
        result = outcome(lambda: service.shutdown(10))
        assert restarts == ["entered", True]
        assert result is False, f"shutdown must refuse with a bool, not {result!r}"
        assert service.project is project and not project.read_only
        assert owned.controller.running
    finally:
        owned.controller.running_changed.disconnect(restart)
        for held in owned.gates:
            held.set()
        assert service.shutdown(10)
