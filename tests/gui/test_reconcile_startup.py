"""Native-start failures must retain the project lock until the actual worker joins."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# Verify retained worker identity, not just its public busy flag.
import threading
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from reconcile_bootstrap_helpers import BootstrapPause
from reconcile_helpers import outcome, owned, settled

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import LaunchResult

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("kind", [RuntimeError, KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("hook", ["_set_ident", "_set_native_id"])
@pytest.mark.parametrize("action", ["lock", "discard"])
def test_interrupted_bootstrap_keeps_ownership_until_join(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: type[BaseException],
    hook: str,
    action: str,
) -> None:
    with owned(tmp_path) as (services, project, work):
        owner = services.launch
        error = kind("native thread created before startup acknowledgement")
        pause = BootstrapPause(owner, error, hook)
        results: list[LaunchResult] = []
        owner.completed.connect(results.append)
        try:
            with monkeypatch.context() as patch:
                pause.install(patch)
                result = outcome(lambda: services.start_reconcile("kcl", action))
            assert result is False and owner.busy
            assert owner._thread is pause.workers[0], "native worker was abandoned"
            assert outcome(lambda: owner.shutdown(0)) is False
            assert outcome(lambda: owner.shutdown(10)) is False
            assert outcome(lambda: services.shutdown(0)) is False
            assert isinstance(outcome(services.close_project), ProjectError)
            assert project.lock is not None and services.project is project
            with Project.open(project.root) as contender:
                assert contender.read_only, "bootstrap fault released the writer lock"
            assert results == [], "startup fault published before worker join"
        finally:
            pause.finish(work.gate)
        assert settled(qtbot, lambda: not owner.busy)
        assert len(results) == 1 and results[0].error is error
        next_error = ProjectError("A later request has its own error.")
        work.error = next_error
        assert services.start_reconcile("kcl", action)
        assert settled(qtbot, lambda: not owner.busy)
        assert len(results) == 2 and results[1].error is next_error


@pytest.mark.parametrize("kind", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("action", ["lock", "discard"])
def test_interrupt_before_native_creation_is_reported_and_releases_owner(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: type[BaseException],
    action: str,
) -> None:
    with owned(tmp_path) as (services, _project, work):
        owner = services.launch
        error = kind("native creation interrupted")
        results: list[LaunchResult] = []
        owner.completed.connect(results.append)

        def interrupted(_thread: threading.Thread) -> None:
            raise error

        with monkeypatch.context() as patch:
            patch.setattr(threading.Thread, "start", interrupted)
            result = outcome(lambda: services.start_reconcile("kcl", action))
        stopped = outcome(lambda: owner.shutdown(0))
        # Drain a broken unstarted owner too, so RED never creates teardown errors.
        if owner._thread is not None and owner._thread.ident is None:
            work.gate.set()
            owner._thread.start()
            owner._thread.join(10)
        assert result is False and stopped is True
        assert len(results) == 1 and results[0].error is error
        work.gate.set()
        assert services.start_reconcile("kcl", action)
        assert settled(qtbot, lambda: not owner.busy)
