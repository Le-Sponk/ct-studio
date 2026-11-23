"""TD-017: Python's cyclic garbage collector runs only on the GUI thread.

Automatic collection runs on whichever thread happens to allocate. When that is a worker
(the file watcher), it can free Qt objects that belong to the GUI thread, with their signal
connections, while the GUI thread is connecting signals: a crash or a GIL/Qt-mutex deadlock
(measured with a synthetic reproduction: default collection crashed or froze within seconds,
collection on the GUI thread only ran clean). The app and the test session therefore turn
automatic collection off and collect on the GUI thread.
"""

from __future__ import annotations

import gc
import threading
import weakref
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from reconcile_helpers import settled

from ctstudio.gui import gc_policy
from ctstudio.gui.gc_policy import GuiThreadCollector, collect_if_due


class Cycle:
    """Garbage only the cyclic collector can free."""

    def __init__(self) -> None:
        self.me = self


def _allocate_cycles(count: int) -> None:
    for _ in range(count):
        Cycle()


@pytest.fixture
def collections() -> Generator[list[int]]:
    """Thread ids of every collection that starts while the test runs."""
    started: list[int] = []

    def record(phase: str, _info: dict[str, int]) -> None:
        if phase == "start":
            started.append(threading.get_ident())

    gc.collect()  # leave no earlier test's garbage for a worker to free
    gc.callbacks.append(record)
    try:
        yield started
    finally:
        gc.callbacks.remove(record)
        gc.disable()  # the test session's policy (tests/conftest.py)


def _in_worker(target: Callable[[], object]) -> None:
    worker = threading.Thread(target=target, name="ctstudio-test-allocator")
    worker.start()
    worker.join(30)
    assert not worker.is_alive(), "allocating worker did not finish"


def test_with_the_collector_running_a_worker_never_starts_a_collection(
    qtbot: QtBot, collections: list[int]
) -> None:
    gc.enable()  # Python's default, as when the app starts
    collector = GuiThreadCollector()
    collector.start()
    try:
        _in_worker(lambda: _allocate_cycles(50_000))
        worker_runs = list(collections)
        assert worker_runs == [], "a collection started on the worker thread"
        assert not gc.isenabled(), "automatic collection is still on"
        canary = Cycle()
        alive = weakref.ref(canary)
        del canary
        assert alive() is not None, "the cycle was freed without a collection"
        assert settled(qtbot, lambda: alive() is None), "the GUI thread's timer never collected"
        main = threading.get_ident()
        assert collections, "no collection ran at all"
        assert set(collections) == {main}, "a collection ran off the GUI thread"
    finally:
        collector.stop()


def test_collect_if_due_does_nothing_off_the_gui_thread(collections: list[int]) -> None:
    gc.disable()
    _allocate_cycles(5_000)
    results: list[int | None] = []
    _in_worker(lambda: results.append(collect_if_due()))
    assert results == [None], "a worker was allowed to collect"
    assert collections == [], "a collection started on the worker thread"


def test_collect_if_due_follows_the_generation_thresholds(
    collections: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    gc.disable()  # the fixture has just collected; nothing is due yet
    monkeypatch.setattr(gc_policy.gc, "get_threshold", lambda: (10**9, 10, 10))
    _allocate_cycles(2_000)
    assert collect_if_due() is None, "collected before the youngest generation was due"
    assert collections == [], "a collection started before it was due"
    monkeypatch.setattr(gc_policy.gc, "get_count", lambda: (701, 3, 2))
    monkeypatch.setattr(gc_policy.gc, "get_threshold", lambda: (700, 10, 10))
    assert collect_if_due() == 0, "the due youngest generation was not collected"
    monkeypatch.setattr(gc_policy.gc, "get_count", lambda: (701, 11, 2))
    assert collect_if_due() == 1, "the due middle generation was not collected"
    monkeypatch.setattr(gc_policy.gc, "get_count", lambda: (701, 11, 11))
    assert collect_if_due() == 2, "the due oldest generation was not collected"
    monkeypatch.setattr(gc_policy.gc, "get_count", lambda: (700, 11, 11))
    assert collect_if_due() is None, "collected at, not above, the threshold"
    monkeypatch.setattr(gc_policy.gc, "get_count", lambda: (5000, 11, 11))
    monkeypatch.setattr(gc_policy.gc, "get_threshold", lambda: (0, 10, 10))
    assert collect_if_due() is None, "a threshold of 0 (collection off) still collected"


def test_stop_restores_the_collection_state_found_at_start(
    qtbot: QtBot, collections: list[int]
) -> None:
    gc.enable()
    collector = GuiThreadCollector()
    collector.start()
    assert not gc.isenabled(), "start left automatic collection on"
    collector.stop()
    assert gc.isenabled(), "stop did not turn automatic collection back on"
    gc.disable()
    collector = GuiThreadCollector()
    collector.start()
    collector.stop()
    assert not gc.isenabled(), "stop turned on collection that was off before start"
    gc.enable()
    collector = GuiThreadCollector()
    collector.start()
    collector.stop(restore=False)
    assert not gc.isenabled(), "stop(restore=False) turned automatic collection back on"


def test_the_app_starts_the_collector_before_its_window_and_leaves_collection_off(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from PySide6.QtWidgets import QApplication

    from ctstudio.gui import app

    calls: list[str] = []

    class Recording(GuiThreadCollector):
        def start(self) -> None:
            calls.append("start")
            super().start()

        def stop(self, *, restore: bool = True) -> None:
            calls.append(f"stop restore={restore}")
            super().stop(restore=restore)

    real_window = app.MainWindow

    def recorded_window() -> object:
        calls.append("window")
        return real_window()

    def running_app(_argv: list[str]) -> object:
        return QApplication.instance()

    monkeypatch.setattr(app, "QApplication", running_app)
    monkeypatch.setattr(app, "GuiThreadCollector", Recording)
    monkeypatch.setattr(app, "MainWindow", recorded_window)
    gc.enable()  # Python's default when the app starts
    try:
        assert app.run_gui(tmp_path / "écran.png") == 0
        left_on = gc.isenabled()
    finally:
        gc.disable()  # the test session's policy (tests/conftest.py)
    assert calls == ["start", "window", "stop restore=False"], "collector order is wrong"
    assert not left_on, "the app turned automatic collection back on at exit"
