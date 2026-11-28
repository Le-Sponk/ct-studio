"""One background job at a time, delivered after its thread has ended (Deep Clean #1 f)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import NoReturn

import pytest
from PySide6.QtCore import QCoreApplication
from pytestqt.qtbot import QtBot
from waits import settled

from ctstudio.core.errors import CTStudioError
from ctstudio.gui.joined_worker import JoinedWorker

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
_LOG = logging.getLogger("ctstudio.test.joined_worker")
NAME = "ctstudio-test-worker"


class Seen:
    def __init__(self) -> None:
        self.payloads: list[object] = []
        self.alive: list[bool] = []
        self.threads: list[str] = []
        self.worker: JoinedWorker | None = None

    def deliver(self, payload: object) -> None:
        self.payloads.append(payload)
        self.threads.append(threading.current_thread().name)
        self.alive.append(any(t.name == NAME for t in threading.enumerate()))


def worker(seen: Seen, expected: tuple[type[Exception], ...] = ()) -> JoinedWorker:
    made = JoinedWorker(
        NAME, seen.deliver, logger=_LOG, failure="the probe failed", expected=expected
    )
    seen.worker = made
    return made


def _slow(value: object) -> Callable[[], object]:
    def work() -> object:
        assert threading.current_thread().name == NAME
        time.sleep(0.1)
        return value

    return work


def test_the_result_comes_back_on_the_gui_thread_after_the_thread_ended(qtbot: QtBot) -> None:
    seen = Seen()
    job = worker(seen)
    job.start(_slow("made"))
    assert job.busy
    assert settled(qtbot, lambda: seen.payloads == ["made"])
    assert seen.threads == [threading.main_thread().name]
    assert seen.alive == [False], "delivered while its thread was still running"
    assert not job.busy


def test_an_unexpected_failure_is_logged_and_delivered(
    qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    seen = Seen()

    def broken() -> NoReturn:
        raise RuntimeError("disk gone")

    with caplog.at_level(logging.ERROR, logger=_LOG.name):
        worker(seen).start(broken)
        assert settled(qtbot, lambda: len(seen.payloads) == 1)
    assert isinstance(seen.payloads[0], RuntimeError)
    assert [r.getMessage() for r in caplog.records] == ["the probe failed"]
    assert caplog.records[0].exc_info is not None


def test_an_expected_failure_is_delivered_without_a_log(
    qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    seen = Seen()

    def refused() -> NoReturn:
        raise CTStudioError("That folder already has files.")

    with caplog.at_level(logging.ERROR, logger=_LOG.name):
        worker(seen, expected=(CTStudioError,)).start(refused)
        assert settled(qtbot, lambda: len(seen.payloads) == 1)
    assert isinstance(seen.payloads[0], CTStudioError) and caplog.records == []


def test_a_thread_that_cannot_start_reports_at_once_and_frees_its_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = Seen()
    job = worker(seen)

    def no_threads(_thread: threading.Thread) -> NoReturn:
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, "start", no_threads)
    job.start(lambda: "never")
    assert len(seen.payloads) == 1 and isinstance(seen.payloads[0], RuntimeError)
    assert not job.busy


def test_shutdown_waits_and_then_delivers_nothing(qtbot: QtBot) -> None:
    seen = Seen()
    job = worker(seen)
    gate = threading.Event()
    job.start(lambda: gate.wait(5))
    assert not job.shutdown(0.05), "a running job was reported finished"
    assert job.busy
    gate.set()
    assert job.shutdown(5)
    assert not job.busy
    QCoreApplication.sendPostedEvents()  # the result's queued signal arrives now
    assert seen.payloads == [], "a result was delivered after shutdown"


def test_after_a_shutdown_it_starts_and_delivers_again(qtbot: QtBot) -> None:
    """A refused window close keeps the services, so their workers must stay usable."""
    seen = Seen()
    job = worker(seen)
    job.start(_slow("first"))
    assert settled(qtbot, lambda: seen.payloads == ["first"])
    assert job.shutdown(5)
    job.start(_slow("again"))
    assert settled(qtbot, lambda: len(seen.payloads) == 2)
    assert seen.payloads == ["first", "again"] and not job.busy


def test_a_result_still_on_its_way_at_shutdown_is_dropped(qtbot: QtBot) -> None:
    seen = Seen()
    job = worker(seen)
    done = threading.Event()

    def quick() -> object:
        done.set()
        return "old"

    job.start(quick)
    assert done.wait(5)
    assert job.shutdown(5)  # joined; its result is still queued, not yet delivered
    job.start(_slow("new"))
    assert settled(qtbot, lambda: bool(seen.payloads))
    QCoreApplication.sendPostedEvents()
    assert seen.payloads == ["new"], "a result from before the shutdown was delivered"
    assert not job.busy
