"""P5-T03e1: joined build ownership, startup faults and stale queued delivery."""

# pyright: reportPrivateUsage=false
# Tests inspect/inject matching worker generations to prove ownership and stale-signal safety.

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from build_fakes import THREAD, project, summary
from build_ownership_helpers import Ownership, outcome
from PySide6.QtCore import QCoreApplication

from ctstudio.core.build.events import BuildFinished
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["project"]


@pytest.fixture
def owned(qapp: object, tmp_path: Path) -> Iterator[Ownership]:
    made = Ownership(tmp_path)
    yield made
    made.close()


@pytest.mark.parametrize("error", [None, RuntimeError("build crash")], ids=["success", "failure"])
def test_completion_joins_matching_worker_before_idle_and_result(
    owned: Ownership, project: Project, monkeypatch: pytest.MonkeyPatch, error: Exception | None
) -> None:
    original = threading.Thread.join
    joined: list[tuple[threading.Thread, bool, threading.Thread | None]] = []

    def join(thread: threading.Thread, timeout: float | None = None) -> None:
        if thread.name == THREAD:
            original(thread, timeout)
            joined.append((thread, owned.controller.running, owned.controller._thread))
            owned.order.append("joined")
        else:
            original(thread, timeout)

    monkeypatch.setattr(threading.Thread, "join", join)
    owned.fake.run_error = error
    assert owned.controller.start(project)
    worker = owned.worker()
    owned.drain()
    assert joined == [(worker, True, worker)]
    assert owned.order == [True, "joined", False, "failed" if error else "finished"]
    owned.assert_idle()
    assert owned.failed == ([] if error is None else [error])


@pytest.mark.parametrize("stage", ["plan_error", "run_error"])
@pytest.mark.parametrize(
    "kind", [BaseException, KeyboardInterrupt, SystemExit, RuntimeError, ProjectError]
)
def test_worker_failure_preserves_identity_cause_and_releases_ownership(
    owned: Ownership,
    project: Project,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    kind: type[BaseException],
) -> None:
    escaped: list[threading.ExceptHookArgs] = []
    monkeypatch.setattr(threading, "excepthook", escaped.append)
    error = kind("synthetic failure")
    cause = ValueError("underlying cause")
    error.__cause__ = cause
    setattr(owned.fake, stage, error)
    delivered_on: list[threading.Thread] = []

    def delivered(_error: object) -> None:
        delivered_on.append(threading.current_thread())

    owned.controller.failed.connect(delivered)
    assert owned.controller.start(project)
    owned.drain()
    owned.assert_failure(error)
    assert error.__cause__ is cause
    assert escaped == []
    assert delivered_on == [threading.main_thread()]
    assert owned.finished == []
    owned.assert_idle()
    setattr(owned.fake, stage, None)
    assert owned.controller.start(project)
    owned.drain()
    assert len(owned.finished) == 1


@pytest.mark.parametrize("kind", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_start_failure_before_startup_clears_state_and_allows_retry(
    owned: Ownership,
    project: Project,
    monkeypatch: pytest.MonkeyPatch,
    kind: type[BaseException],
) -> None:
    error = kind("thread could not start")
    cause = OSError("synthetic resource exhaustion")
    error.__cause__ = cause

    def fail(thread: threading.Thread) -> None:
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", fail)
        result = outcome(lambda: owned.controller.start(project))
    assert result is False
    owned.assert_failure(error)
    assert error.__cause__ is cause
    assert owned.order == ["failed"]
    owned.assert_idle()
    assert owned.fake.planned == []
    assert outcome(lambda: owned.controller.shutdown(0)) is True
    assert owned.controller.start(project)
    owned.drain()
    assert len(owned.finished) == 1
    assert owned.failed == [error]


@pytest.mark.parametrize("kind", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_start_failure_after_startup_cancels_but_keeps_live_worker_owned(
    owned: Ownership,
    project: Project,
    monkeypatch: pytest.MonkeyPatch,
    kind: type[BaseException],
) -> None:
    gate = owned.hold()
    error = kind("raised after native startup")
    original = threading.Thread.start
    started: list[threading.Thread] = []

    def fail_after_start(thread: threading.Thread) -> None:
        original(thread)
        started.append(thread)
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", fail_after_start)
        result = outcome(lambda: owned.controller.start(project))
    try:
        assert result is False
        owned.assert_cancelled_owner(started[0])
        assert owned.failed == []  # failure publication must wait for the join too
        assert outcome(lambda: owned.controller.shutdown(0)) is False
        owned.assert_cancelled_owner(started[0])
        assert not owned.controller.start(project)
    finally:
        gate.set()
        # Safe even when the broken implementation abandoned this live worker.
        started[0].join(10)
    owned.drain()
    owned.assert_failure(error)
    owned.assert_idle()
    owned.fake.gate = None
    assert owned.controller.start(project)
    owned.drain()
    assert len(owned.finished) == 1


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("error", [None, RuntimeError("old worker")], ids=["success", "failure"])
def test_reentrant_idle_shutdown_invalidates_completion_before_publication(
    owned: Ownership, project: Project, restart: bool, error: Exception | None
) -> None:
    handled: list[object] = []
    gates: list[threading.Event] = []
    owned.fake.run_error = error

    def on_running(running: bool) -> None:
        if running or handled:
            return
        handled.append(outcome(lambda: owned.controller.shutdown(0)))
        if restart:
            owned.fake.run_error = None
            gates.append(owned.hold())
            handled.append(outcome(lambda: owned.controller.start(project)))

    owned.controller.running_changed.connect(on_running)
    assert owned.controller.start(project)
    first = owned.worker()
    owned.drain()
    assert handled == ([True, True] if restart else [True])
    assert owned.finished == []
    assert owned.failed == []
    if restart:
        assert owned.controller.running
        assert owned.worker() is not first
        gates[0].set()
        owned.drain()
        assert len(owned.finished) == 1
    else:
        assert not owned.controller.running


def test_timeout_retains_running_worker_until_completion(
    owned: Ownership, project: Project
) -> None:
    gate = owned.hold()
    assert owned.controller.start(project)
    worker = owned.worker()
    assert outcome(lambda: owned.controller.shutdown(0)) is False
    owned.assert_cancelled_owner(worker)
    assert not owned.controller.start(project)
    assert owned.finished == owned.failed == []
    gate.set()
    owned.drain()
    owned.assert_idle()
    assert len(owned.finished) == 1


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("error", [None, RuntimeError("discard me")], ids=["success", "failure"])
def test_joined_shutdown_drops_all_queued_signals_even_after_immediate_restart(
    owned: Ownership, project: Project, tmp_path: Path, restart: bool, error: Exception | None
) -> None:
    settings = tmp_path / "settings é.json"
    settings.write_text("{damaged", encoding="utf-8")
    old = BuildFinished(summary(ran=("old",)))
    new = BuildFinished(summary(ran=("new",)))
    owned.fake.events = [old]
    owned.fake.run_error = error
    assert owned.controller.start(project)
    assert outcome(lambda: owned.controller.shutdown(10)) is True
    owned.assert_idle()
    owned.assert_no_delivery()
    settings.write_text("{}", encoding="utf-8")
    gate = owned.hold()
    current = None
    if restart:
        owned.fake.events = [new]
        owned.fake.run_error = None
        assert owned.controller.start(project)
        current = owned.worker()
    QCoreApplication.sendPostedEvents()
    assert all(event is new for event in owned.events)
    owned.assert_no_result()
    assert owned.controller.running is restart
    if restart:
        assert owned.worker() is current
        gate.set()
        owned.drain()
        owned.assert_delivered(new)
    else:
        assert owned.events == []


@pytest.mark.parametrize("restart", [False, True])
def test_failed_unstarted_worker_invalidates_queued_signals(
    owned: Ownership, project: Project, monkeypatch: pytest.MonkeyPatch, restart: bool
) -> None:
    original = threading.Thread.start
    error = RuntimeError("startup refusal")
    stale = BuildFinished(summary(ran=("stale",)))

    def fail(thread: threading.Thread) -> None:
        generation = owned.controller._generation
        relay = owned.controller._relay

        def send_stale() -> None:
            relay.build_event.emit(generation, stale)
            relay.notice.emit(generation, "stale notice")
            relay.done.emit(generation, stale.summary, None)

        producer = threading.Thread(target=send_stale, name="synthetic-relay")
        original(producer)
        producer.join(10)
        assert not producer.is_alive()
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", fail)
        result = outcome(lambda: owned.controller.start(project))
    assert result is False
    assert owned.failed == [error]
    gate = owned.hold()
    if restart:
        assert owned.controller.start(project)
    QCoreApplication.sendPostedEvents()
    assert stale not in owned.events
    assert owned.notices == []
    owned.assert_failure(error)
    assert owned.controller.running is restart
    if restart:
        gate.set()
        owned.drain()
        assert len(owned.finished) == 1


@pytest.mark.parametrize("timeout", [0, 10], ids=["timeout", "joined-restart"])
def test_reentrant_running_listener_sees_started_worker_and_cannot_cause_stale_start(
    owned: Ownership, project: Project, monkeypatch: pytest.MonkeyPatch, timeout: int
) -> None:
    original = threading.Thread.start
    starts: list[threading.Thread] = []
    results: list[object] = []
    gate = owned.hold() if timeout == 0 else None

    def start(thread: threading.Thread) -> None:
        original(thread)
        starts.append(thread)

    def on_running(running: bool) -> None:
        if not running or results:
            return
        thread = owned.controller._thread
        results.append(thread.ident if thread is not None else None)
        results.append(outcome(lambda: owned.controller.shutdown(timeout)))
        if timeout:
            owned.hold()
        results.append(outcome(lambda: owned.controller.start(project)))

    monkeypatch.setattr(threading.Thread, "start", start)
    owned.controller.running_changed.connect(on_running)
    result = outcome(lambda: owned.controller.start(project))
    assert result is True
    assert len(results) == 3
    assert results[0] is not None
    assert results[1:] == ([True, True] if timeout else [False, False])
    assert len(starts) == (2 if timeout else 1)
    owned.assert_active(starts[-1])
    QCoreApplication.sendPostedEvents()
    owned.assert_no_result()
    if gate is not None:
        gate.set()
    for held in owned.gates:
        held.set()
    owned.drain()
    assert len(owned.finished) == 1


def test_start_that_raises_after_worker_exit_still_delivers_its_failure(
    owned: Ownership, project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = threading.Thread.start
    error = KeyboardInterrupt("startup interrupted after worker exit")

    def fail(thread: threading.Thread) -> None:
        original(thread)
        thread.join(10)
        assert not thread.is_alive()
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", fail)
        result = outcome(lambda: owned.controller.start(project))
    assert result is False
    assert owned.controller.running
    assert owned.worker().ident is not None
    assert owned.failed == owned.finished == []
    owned.drain()
    assert owned.failed == [error]
    assert owned.finished == []
    owned.assert_idle()
