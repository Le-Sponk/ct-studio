"""Synchronous busy/idle callbacks must not bypass joined request ownership."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from pytestqt.qtbot import QtBot
from reconcile_helpers import outcome, owned, settled

from ctstudio.core.errors import ProjectError
from ctstudio.gui.launch_controller import LaunchResult

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_busy_callback_cannot_join_unstarted_worker(
    qtbot: QtBot, tmp_path: Path, action: str
) -> None:
    with owned(tmp_path) as (services, _project, work):
        observed: list[object] = []

        def on_busy(busy: bool) -> None:
            if busy:
                observed.append(outcome(lambda: services.launch.shutdown(0)))

        services.launch.busy_changed.connect(on_busy)
        try:
            assert services.start_reconcile("kcl", action)
            assert work.entered.wait(5)
        finally:
            services.launch.busy_changed.disconnect(on_busy)
            work.gate.set()
        assert observed == [False], f"startup shutdown must refuse safely: {observed!r}"
        assert settled(qtbot, lambda: not services.launch.busy)


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize("application", [False, True])
def test_shutdown_refuses_callback_started_replacement(
    qtbot: QtBot, tmp_path: Path, action: str, application: bool
) -> None:
    with owned(tmp_path) as (services, project, work):
        work.error = ProjectError("First action intentionally refused.")
        assert services.start_reconcile("kcl", action)
        assert work.entered.wait(5)
        first_gate = work.gate
        work.gate = threading.Event()
        started: list[object] = []

        def on_idle(busy: bool) -> None:
            if not busy and not started:
                started.append("entered")
                started.append(outcome(lambda: services.start_reconcile("kcl", action)))

        owner = services.launch
        owner.busy_changed.connect(on_idle)
        try:
            first_gate.set()
            result = outcome(lambda: services.shutdown(10) if application else owner.shutdown(10))
            assert started == ["entered", True]
            assert result is False, f"replacement worker must retain ownership: {result!r}"
            assert owner.busy and services.project is project and project.lock is not None
        finally:
            owner.busy_changed.disconnect(on_idle)
            work.gate.set()
        assert settled(qtbot, lambda: not owner.busy)


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize("startup_failure", [False, True])
def test_idle_shutdown_invalidates_pending_delivery(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    startup_failure: bool,
) -> None:
    with owned(tmp_path) as (services, _project, work):
        owner = services.launch
        results: list[LaunchResult] = []
        stopped: list[object] = []
        owner.completed.connect(results.append)

        def on_idle(busy: bool) -> None:
            if not busy:
                stopped.append(outcome(lambda: owner.shutdown(0)))

        def refuse(_thread: threading.Thread) -> None:
            raise RuntimeError("Synthetic thread creation failure")

        owner.busy_changed.connect(on_idle)
        try:
            with monkeypatch.context() as patch:
                if startup_failure:
                    patch.setattr(threading.Thread, "start", refuse)
                assert services.start_reconcile("kcl", action) is not startup_failure
            work.gate.set()
            assert settled(qtbot, lambda: not owner.busy)
            QCoreApplication.sendPostedEvents()
        finally:
            owner.busy_changed.disconnect(on_idle)
        assert stopped == [True]
        assert results == [], "shutdown invalidated completion before publication"
