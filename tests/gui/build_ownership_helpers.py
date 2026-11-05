"""Deterministic worker ownership observations; all builds are synthetic."""

# pyright: reportPrivateUsage=false
# Ownership proofs intentionally inspect the worker/token rather than race its visible state.

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from build_fakes import WAIT, FakeBuilds, build_threads
from PySide6.QtCore import QCoreApplication

from ctstudio.core.build.events import BuildFinished
from ctstudio.gui.build_controller import BuildController

_JOIN = threading.Thread.join


def outcome[T](call: Callable[[], T]) -> T | BaseException:
    """Turn unexpected public-API raises into assertion failures, not test errors."""
    try:
        return call()
    except BaseException as exc:
        return exc


class Ownership:
    def __init__(self, folder: Path) -> None:
        self.fake = FakeBuilds()
        self.gates: list[threading.Event] = []
        self.controller = BuildController(
            plan=self.fake.plan, build=self.fake.run, settings_path=folder / "settings é.json"
        )
        self.events: list[object] = []
        self.notices: list[str] = []
        self.finished: list[object] = []
        self.failed: list[object] = []
        self.order: list[object] = []
        self.controller.build_event.connect(self.events.append)
        self.controller.notice.connect(self.notices.append)
        self.controller.finished.connect(self.finished.append)
        self.controller.failed.connect(self.failed.append)
        self.controller.running_changed.connect(self._running)
        self.controller.finished.connect(self._finished)
        self.controller.failed.connect(self._failed)

    def _running(self, value: bool) -> None:
        self.order.append(value)

    def _finished(self, _summary: object) -> None:
        self.order.append("finished")

    def _failed(self, _error: object) -> None:
        self.order.append("failed")

    def hold(self) -> threading.Event:
        gate = threading.Event()
        self.gates.append(gate)
        self.fake.gate = gate
        return gate

    def worker(self) -> threading.Thread:
        thread = self.controller._thread
        assert thread is not None, "controller lost worker ownership"
        return thread

    def drain(self) -> None:
        """Wait for producer exit without recording a controller join, then flush delivery."""
        _JOIN(self.worker(), WAIT / 1000)
        assert not self.worker().is_alive(), "synthetic worker did not exit"
        QCoreApplication.sendPostedEvents()

    def assert_idle(self) -> None:
        assert not self.controller.running, "controller remained running"
        assert self.controller._thread is None, "controller retained a completed worker"
        assert build_threads() == [], "named build worker leaked"

    def assert_failure(self, error: BaseException) -> None:
        assert len(self.failed) == 1, f"expected exactly one failure: {self.failed!r}"
        assert self.failed[0] is error, "failure lost exception identity"
        assert self.finished == [], f"unexpected successful completion: {self.finished!r}"

    def assert_active(self, worker: threading.Thread) -> None:
        assert self.controller.running, "live worker lost running state"
        assert self.worker() is worker, "live worker lost thread ownership"
        assert build_threads() == [worker], "expected exactly the matching named worker"

    def assert_cancelled_owner(self, worker: threading.Thread) -> None:
        self.assert_active(worker)
        assert self.controller._cancels.current.cancelled, "worker did not receive cancellation"

    def assert_no_result(self) -> None:
        assert self.notices == [], f"unexpected notices: {self.notices!r}"
        assert self.finished == [], f"unexpected completions: {self.finished!r}"
        assert self.failed == [], f"unexpected failures: {self.failed!r}"

    def assert_no_delivery(self) -> None:
        assert self.events == [], f"unexpected build events: {self.events!r}"
        self.assert_no_result()

    def assert_delivered(self, event: BuildFinished) -> None:
        assert self.events == [event], f"wrong events: {self.events!r}"
        assert self.finished == [event.summary], f"wrong completion: {self.finished!r}"
        assert self.failed == [], f"unexpected failures: {self.failed!r}"
        assert self.notices == [], f"unexpected notices: {self.notices!r}"

    def close(self) -> None:
        for gate in self.gates:
            gate.set()
        for worker in set(self.fake.threads):
            _JOIN(worker, WAIT / 1000)  # also drain a mutant's abandoned worker
            assert not worker.is_alive(), "synthetic worker did not stop during cleanup"
        # A broken startup may have stored an unstarted thread: do not obscure the failure.
        thread = self.controller._thread
        if thread is not None and thread.ident is not None:
            result = outcome(lambda: self.controller.shutdown(WAIT / 1000))
            assert result is True, f"cleanup shutdown failed: {result!r}"
        assert build_threads() == [], "named build worker leaked"
