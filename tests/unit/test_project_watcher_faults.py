"""P5-T06a: the watcher with an injected ``watch`` function (no real watching, no timing)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from watch_fakes import FakeWatch, Seen, run

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import watch as watch_module
from ctstudio.core.project.watch import (
    DEBOUNCE_MS,
    WATCH_THREAD,
    ProjectWatcher,
    WatchPlan,
)

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "proj é"
    folder.mkdir()
    return folder


def test_the_project_folder_is_watched_recursively_and_outside_ones_flat(
    root: Path, tmp_path: Path
) -> None:
    art = tmp_path / "art"
    art.mkdir()
    fake = FakeWatch([])
    run(WatchPlan(root, {art: frozenset({"t.blend"})}), fake, Seen())
    calls = {paths: kwargs for paths, kwargs in fake.calls}
    assert set(calls) == {(str(root),), (str(art),)}
    inside, outside = calls[(str(root),)], calls[(str(art),)]
    assert inside["recursive"] is True
    assert outside["recursive"] is False
    for kwargs in (inside, outside):
        assert kwargs["watch_filter"] is None  # our own rules decide
        assert kwargs["debounce"] == DEBOUNCE_MS
        assert kwargs["raise_interrupt"] is False
        assert kwargs["yield_on_timeout"] is True
        assert isinstance(kwargs["stop_event"], threading.Event)


def test_no_outside_thread_without_outside_folders(root: Path) -> None:
    fake = FakeWatch([])
    watcher = ProjectWatcher(WatchPlan(root, {}), Seen().change, Seen().error, watch=fake)
    watcher.start()
    try:
        assert fake.done.acquire(timeout=5)
        names = [t.name for t in threading.enumerate() if t.name.startswith(WATCH_THREAD)]
        assert names == [WATCH_THREAD]
    finally:
        watcher.stop()
        assert watcher.join(5)
    assert [paths for paths, _ in fake.calls] == [(str(root),)]


def test_when_the_second_thread_cannot_start_the_first_is_stopped(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    art = tmp_path / "art"
    art.mkdir()
    real_start = threading.Thread.start

    def second_refused(self: threading.Thread) -> None:
        if self.name == f"{WATCH_THREAD}-outside":
            raise RuntimeError("can't start new thread")
        real_start(self)

    monkeypatch.setattr(watch_module.threading.Thread, "start", second_refused)
    fake = FakeWatch([])
    watcher = ProjectWatcher(WatchPlan(root, {art: None}), Seen().change, Seen().error, watch=fake)
    try:
        watcher.start()
        raised: Exception | None = None
    except Exception as exc:
        raised = exc
    assert isinstance(raised, ProjectError)
    assert watcher.join(5), "the project thread was left running"
    assert not watcher.intact


def test_only_relevant_changes_are_passed_on_and_empty_batches_are_not(root: Path) -> None:
    stage = root / ".ctstudio" / "stage" / "course.kcl"
    fake = FakeWatch(
        [
            set(),  # a timeout: watching has begun
            {(2, str(root / ".ctstudio" / "state.json"))},
            {(2, str(stage)), (1, str(root / "build" / "t.szs"))},
        ]
    )
    seen = Seen()
    run(WatchPlan(root, {}), fake, seen)
    assert seen.changes == [frozenset({stage})]
    assert seen.errors == []


def test_stop_sets_the_event_the_watch_loop_checks(root: Path) -> None:
    fake = FakeWatch([])
    watcher = ProjectWatcher(WatchPlan(root, {}), Seen().change, Seen().error, watch=fake)
    watcher.start()
    assert fake.done.acquire(timeout=5)
    stop_event = fake.calls[0][1]["stop_event"]
    assert not stop_event.is_set()
    assert watcher.alive
    watcher.stop()
    assert stop_event.is_set()
    assert watcher.join(5)


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (OSError(28, "No space left on device"), "No space left on device"),
        (OSError("OS file watch limit reached"), "OS file watch limit reached"),
        (RuntimeError(), "RuntimeError"),
    ],
)
def test_a_failing_watch_is_reported_with_its_reason(
    root: Path, error: Exception, reason: str
) -> None:
    seen = Seen()
    watcher = run(WatchPlan(root, {}), FakeWatch([set()], error), seen)
    (reported,) = seen.errors
    assert reported.user_message == f"CT Studio cannot notice changes in {root} ({reason})."
    assert reported.hint == "After changing files outside CT Studio, press Refresh statuses."
    assert reported.__cause__ is error
    assert not watcher.alive


def test_a_thread_that_cannot_start_is_a_project_error(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: threading.Thread) -> None:
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(watch_module.threading.Thread, "start", refuse)
    watcher = ProjectWatcher(WatchPlan(root, {}), Seen().change, Seen().error, watch=FakeWatch([]))
    with pytest.raises(Exception) as caught:
        watcher.start()
    assert isinstance(caught.value, ProjectError)
    assert "Refresh statuses" in (caught.value.hint or "")
    assert not watcher.alive


def test_thread_names(root: Path, tmp_path: Path) -> None:
    names: list[str] = []
    art = tmp_path / "art"
    art.mkdir()

    class Naming(FakeWatch):
        def __call__(self, *paths: Path, **kwargs: Any) -> Iterator[set[tuple[object, str]]]:
            names.append(threading.current_thread().name)
            return super().__call__(*paths, **kwargs)

    watcher = run(WatchPlan(root, {art: None}), Naming([]), Seen())
    assert sorted(names) == [WATCH_THREAD, f"{WATCH_THREAD}-outside"]
    # daemon threads: a watcher that will not stop never keeps CT Studio from exiting
    assert [t.daemon for t in watcher._threads] == [True, True]  # pyright: ignore[reportPrivateUsage]


def test_when_one_thread_fails_the_other_stops_and_the_watcher_is_not_intact(
    root: Path, tmp_path: Path
) -> None:
    art = tmp_path / "art"
    art.mkdir()
    outside_started, outside_stopped = threading.Event(), threading.Event()

    def watch(*paths: Path, **kwargs: Any) -> Iterator[set[tuple[object, str]]]:
        stop: threading.Event = kwargs["stop_event"]
        yield set()
        if kwargs["recursive"]:
            assert outside_started.wait(5)
            raise OSError(28, "No space left on device")  # the project folder's watch dies
        outside_started.set()
        while not stop.wait(0.01):  # the outside one would run until asked
            yield set()
        outside_stopped.set()

    seen = Seen()
    watcher = ProjectWatcher(WatchPlan(root, {art: None}), seen.change, seen.error, watch=watch)
    watcher.start()
    assert watcher.join(5), "the outside thread kept running after the project one failed"
    assert outside_stopped.is_set()
    assert len(seen.errors) == 1
    assert not watcher.intact


def test_a_watcher_that_ends_without_being_asked_is_not_intact(root: Path) -> None:
    seen = Seen()
    watcher = run(WatchPlan(root, {}), FakeWatch([set()], ended=True), seen)
    assert not watcher.intact
    assert len(seen.errors) == 1  # the user hears that changes are no longer noticed
    report = seen.errors[0].user_message
    assert report == f"CT Studio cannot notice changes in {root} (watching ended unexpectedly)."


def test_a_watcher_asked_to_stop_reports_nothing(root: Path) -> None:
    seen = Seen()
    stop_seen = threading.Event()

    def watch(*_paths: Path, **kwargs: Any) -> Iterator[set[tuple[object, str]]]:
        stop: threading.Event = kwargs["stop_event"]
        while not stop.wait(0.01):
            yield set()
        stop_seen.set()

    watcher = ProjectWatcher(WatchPlan(root, {}), seen.change, seen.error, watch=watch)
    watcher.start()
    assert watcher.wait_ready(5)
    assert watcher.intact
    watcher.stop()
    assert watcher.join(5)
    assert stop_seen.is_set()
    assert seen.errors == []


def test_ready_only_once_every_thread_is_watching(root: Path, tmp_path: Path) -> None:
    art = tmp_path / "art"
    art.mkdir()
    outside_may_start = threading.Event()

    def watch(*_paths: Path, **kwargs: Any) -> Iterator[set[tuple[object, str]]]:
        stop: threading.Event = kwargs["stop_event"]
        if not kwargs["recursive"]:
            assert outside_may_start.wait(5)  # the outside folder is slow to start watching
        while not stop.wait(0.01):
            yield set()

    seen = Seen()
    watcher = ProjectWatcher(WatchPlan(root, {art: None}), seen.change, seen.error, watch=watch)
    watcher.start()
    try:
        assert not watcher.wait_ready(0.3), "ready before the outside folder was watched"
        outside_may_start.set()
        assert watcher.wait_ready(5)
    finally:
        outside_may_start.set()
        watcher.stop()
        assert watcher.join(5)
    assert seen.errors == []


def test_a_watcher_never_started_is_not_intact(root: Path) -> None:
    watcher = ProjectWatcher(WatchPlan(root, {}), Seen().change, Seen().error, watch=FakeWatch([]))
    assert not watcher.intact
    assert not watcher.alive


def test_a_failure_after_stop_was_asked_is_not_reported(root: Path) -> None:
    def watch(*_paths: Path, **kwargs: Any) -> Iterator[set[tuple[object, str]]]:
        stop: threading.Event = kwargs["stop_event"]
        while not stop.wait(0.01):
            yield set()
        raise OSError("the handle was closed")  # e.g. the folder went while stopping

    seen = Seen()
    watcher = ProjectWatcher(WatchPlan(root, {}), seen.change, seen.error, watch=watch)
    watcher.start()
    assert watcher.wait_ready(5)
    watcher.stop()
    assert watcher.join(5)
    assert seen.errors == []


def test_a_project_folder_gone_when_the_watch_ends_says_so(root: Path) -> None:
    def watch(*_paths: Path, **_kwargs: Any) -> Iterator[set[tuple[object, str]]]:
        root.rmdir()  # it goes, and the watch then ends without a batch
        return
        yield set()

    seen = Seen()
    watcher = ProjectWatcher(WatchPlan(root, {}), seen.change, seen.error, watch=watch)
    watcher.start()
    assert watcher.join(5)
    (error,) = seen.errors
    assert error.user_message == f"CT Studio cannot notice changes in {root} (the folder is gone)."
    assert not watcher.intact
