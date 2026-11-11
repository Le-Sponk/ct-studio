"""Scripted stand-ins for ``watchfiles.watch`` used by the watcher fault tests."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.watch import ProjectWatcher, WatchPlan


class FakeWatch:
    """Stands in for ``watchfiles.watch``: records each call, yields scripted batches, then
    (like the real one) keeps watching until the stop event is set, or raises ``error``.
    ``ended`` (when given) makes it end without being asked instead."""

    def __init__(
        self,
        batches: list[set[tuple[object, str]]],
        error: Exception | None = None,
        *,
        ended: bool = False,
    ):
        self.batches = batches
        self.error = error
        self.ended = ended
        self.calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        self.lock = threading.Lock()
        self.done = threading.Semaphore(0)  # released once per call after its batches

    def __call__(self, *paths: Path, **kwargs: Any) -> Iterator[set[tuple[object, str]]]:
        with self.lock:
            self.calls.append((tuple(str(p) for p in paths), kwargs))
        yield from self.batches
        self.done.release()
        if self.error is not None:
            raise self.error
        if self.ended:
            return
        stop: threading.Event = kwargs["stop_event"]
        while not stop.wait(0.01):
            yield set()


class Seen:
    def __init__(self) -> None:
        self.changes: list[frozenset[Path]] = []
        self.errors: list[ProjectError] = []

    def change(self, paths: frozenset[Path]) -> None:
        self.changes.append(paths)

    def error(self, error: ProjectError) -> None:
        self.errors.append(error)


def run(plan: WatchPlan, fake: FakeWatch, seen: Seen) -> ProjectWatcher:
    """Start, let every watch call play its batches, then stop and wait."""
    watcher = ProjectWatcher(plan, seen.change, seen.error, watch=fake)
    watcher.start()
    for _call in range(1 + bool(plan.outside)):
        assert fake.done.acquire(timeout=5), "a watch call never played its batches"
    if fake.error is None and not fake.ended:
        watcher.stop()
    assert watcher.join(5)
    return watcher


class OutsideScript:
    """Watches the project folder until stopped; the outside call runs ``outside``."""

    def __init__(self, outside: Callable[[dict[str, Any]], Iterator[set[tuple[object, str]]]]):
        self.outside = outside
        self.outside_calls = 0

    def __call__(self, *_paths: Path, **kwargs: Any) -> Iterator[set[tuple[object, str]]]:
        stop: threading.Event = kwargs["stop_event"]
        if not kwargs["recursive"]:
            self.outside_calls += 1
            yield from self.outside(kwargs)
            return
        while not stop.wait(0.01):
            yield set()
