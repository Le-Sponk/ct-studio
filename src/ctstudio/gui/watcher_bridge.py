"""Brings the project watcher's news to the UI thread (P5-T06a, ARCHITECTURE §10, §11).

``WatcherBridge.follow(root, manifest)`` watches what ``core.project.watch.watch_plan`` says
for that project; following the same plan again keeps the running watcher while it is intact
(a refresh or a saved setting that moves no file costs nothing), a new plan or a watcher that
failed (even half of it) is replaced. ``changed`` carries
the watched project's root, ``failed`` a ``ProjectError`` saying watching stopped; both
arrive on the UI thread, and news from a watcher that was replaced or stopped is dropped.
Watching never touches the disk on the UI thread: the watcher's threads do that.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, Signal

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.watch import (
    STEP_MS,
    TICK_MS,
    OnChange,
    OnError,
    ProjectWatcher,
    WatchPlan,
    watch_plan,
)

# A stopped watcher notices within STEP_MS, or TICK_MS while the system call waits.
STOP_GRACE_S = 2 * (STEP_MS + TICK_MS) / 1000


class Watcher(Protocol):
    plan: WatchPlan

    @property
    def alive(self) -> bool: ...

    @property
    def intact(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def join(self, timeout: float) -> bool: ...


type MakeWatcher = Callable[[WatchPlan, OnChange, OnError], Watcher]


class _Relay(QObject):
    """Emitted from watcher threads; not a child of the bridge, so it outlives it."""

    changed = Signal(int, object)  # generation, root
    failed = Signal(int, object)  # generation, ProjectError


class WatcherBridge(QObject):
    changed = Signal(object)  # the root of the project whose files changed
    failed = Signal(object)  # ProjectError: changes are no longer noticed

    def __init__(self, *, make: MakeWatcher | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self._make = make
        self._relay = _Relay()
        self._relay.changed.connect(self._changed)
        self._relay.failed.connect(self._failed)
        self._generation = 0
        self._watcher: Watcher | None = None
        self._stopping: list[Watcher] = []

    @property
    def watching(self) -> Path | None:
        """The root being watched, or None."""
        watcher = self._watcher
        return watcher.plan.root if watcher is not None else None

    def follow(self, root: Path, manifest: Manifest) -> bool:
        """Watch ``root`` as ``manifest`` says; True when a new watcher was started."""
        plan = watch_plan(root, manifest)
        current = self._watcher
        if current is not None and current.plan == plan and current.intact:
            return False
        self.stop()
        generation = self._generation
        relay = self._relay

        def changed(paths: frozenset[Path]) -> None:
            if paths:
                relay.changed.emit(generation, plan.root)

        def failed(error: ProjectError) -> None:
            relay.failed.emit(generation, error)

        make = self._make if self._make is not None else ProjectWatcher  # looked up now
        watcher = make(plan, changed, failed)
        self._watcher = watcher
        try:
            watcher.start()
        except ProjectError as exc:
            self._watcher = None
            watcher.stop()  # (it already did) a thread it started may still be ending
            self._stopping.append(watcher)
            self.failed.emit(exc)
        return True

    def stop(self) -> None:
        """Stop watching; news still on its way is dropped. Does not wait."""
        self._generation += 1
        watcher, self._watcher = self._watcher, None
        self._stopping = [w for w in self._stopping if w.alive]
        if watcher is not None:
            watcher.stop()
            self._stopping.append(watcher)

    def shutdown(self, timeout: float) -> bool:
        """``stop``, then wait up to ``timeout`` s (at least ``STOP_GRACE_S``: a watcher ends
        within moments of being asked, so a no-wait close still lets it); True when no watcher
        thread is left."""
        self.stop()
        for watcher in self._stopping:
            watcher.join(max(timeout, STOP_GRACE_S))
        self._stopping = [w for w in self._stopping if w.alive]
        return not self._stopping

    def _changed(self, generation: int, root: object) -> None:
        if generation == self._generation:
            self.changed.emit(root)

    def _failed(self, generation: int, error: object) -> None:
        if generation == self._generation:
            self.failed.emit(error)
