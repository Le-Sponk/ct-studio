"""Run a build graph: bounded parallel steps, shared resources, cache skips (ARCHITECTURE §7).

A step starts once every step it waits for has succeeded or been skipped and none of its
``resources`` (``blender``, ``stage:<file>``) is held by a running step; up to ``jobs`` run
at once, in worker threads. A step whose cache entry is fresh is skipped. After the first
failure, or once the user cancels, nothing new starts; running steps finish (they see the
cancel through ``ctx.cancel``). Events are delivered one at a time on the calling thread,
which also does the scheduling, so the caller is busy until the build ends: the GUI calls
this from its build worker thread. Every worker thread has ended when this returns.
"""

from __future__ import annotations

import logging
import os
import queue
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import (
    BuildEvent,
    BuildFinished,
    BuildStarted,
    BuildSummary,
    LogLine,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
    Outcome,
)
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import BuildContext, Node, Profile
from ctstudio.core.errors import BuildError, Cancelled, CTStudioError
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.validation.issues import Issue

_LOG = logging.getLogger(__name__)
type Status = Literal["ran", "skipped", "failed", "cancelled"]


@dataclass(frozen=True)
class BuildRequest:
    manifest: Manifest
    profile: Profile
    tools: Mapping[str, ToolLocation]
    versions: Mapping[str, str | None]  # tool id -> version for the cache key (None: unknown)


def default_jobs() -> int:
    return min(4, os.cpu_count() or 1)


def run_build(
    graph: BuildGraph,
    cache: BuildCache,
    request: BuildRequest,
    on_event: Callable[[BuildEvent], None],
    *,
    cancel: CancelToken,
    jobs: int | None = None,
) -> BuildSummary:
    """Run every step of ``graph`` that is not fresh in ``cache``, then save the cache.

    An exception from ``on_event`` stops the build: running steps finish, then it propagates.
    """
    workers = default_jobs() if jobs is None else jobs
    if workers < 1:
        raise ValueError("jobs must be at least 1")
    return _Build(graph, cache, request, on_event, cancel, workers).run()


@dataclass(frozen=True)
class _Done:
    node_id: str
    status: Status
    event: BuildEvent
    issues: tuple[Issue, ...] = ()


class _Build:
    def __init__(
        self,
        graph: BuildGraph,
        cache: BuildCache,
        request: BuildRequest,
        on_event: Callable[[BuildEvent], None],
        cancel: CancelToken,
        jobs: int,
    ) -> None:
        self.graph, self.cache, self.request = graph, cache, request
        self.on_event, self.cancel, self.jobs = on_event, cancel, jobs
        self._queue: queue.SimpleQueue[BuildEvent | _Done] = queue.SimpleQueue()
        self._waiting = list(graph.nodes)
        self._running: dict[str, Node] = {}
        self._held: set[str] = set()
        self._status: dict[str, Status] = {}
        self._issues: dict[str, tuple[Issue, ...]] = {}

    def run(self) -> BuildSummary:
        started = time.monotonic()
        self.on_event(BuildStarted(tuple(node.id for node in self.graph.nodes)))
        try:
            with ThreadPoolExecutor(self.jobs, thread_name_prefix="ctstudio-build") as pool:
                self._loop(pool)
        finally:
            self.cache.save()
        summary = self._summary(time.monotonic() - started)
        self.on_event(BuildFinished(summary))
        return summary

    def _loop(self, pool: ThreadPoolExecutor) -> None:
        while True:
            self._start_ready(pool)
            if not self._running:
                return
            item = self._queue.get()
            if isinstance(item, _Done):
                self._finish(item)
                item = item.event
            self.on_event(item)

    def _start_ready(self, pool: ThreadPoolExecutor) -> None:
        if self._stopping():
            return
        for node in list(self._waiting):
            if len(self._running) >= self.jobs:
                return
            if self._ready(node):
                self._waiting.remove(node)
                self._running[node.id] = node
                self._held |= node.resources
                pool.submit(self._work, node)

    def _stopping(self) -> bool:
        stopped = {"failed", "cancelled"} & set(self._status.values())
        return bool(stopped) or self.cancel.cancelled

    def _ready(self, node: Node) -> bool:
        # A failed or cancelled need also means _stopping(), so nothing starts after it anyway.
        done = all(
            self._status.get(need) in ("ran", "skipped") for need in self.graph.needs(node.id)
        )
        return done and not node.resources & self._held

    def _finish(self, done: _Done) -> None:
        node = self._running.pop(done.node_id)
        self._held -= node.resources
        self._status[done.node_id] = done.status
        self._issues[done.node_id] = done.issues

    def _work(self, node: Node) -> None:
        """One step in a worker thread; always ends with exactly one ``_Done``."""
        try:
            done = self._attempt(node)
        except Exception as exc:  # reported as NodeFailed; the build itself must not crash
            done = self._failure(node, exc)
        self._queue.put(done)

    def _attempt(self, node: Node) -> _Done:
        lookup = self.cache.check(node, self.request.versions)
        if lookup.fresh:
            return _Done(node.id, "skipped", NodeSkipped(node.id))
        self._queue.put(NodeStarted(node.id))
        started = time.monotonic()
        result = node.run(self._context(node))
        self.cache.store(node, lookup)
        finished = NodeFinished(node.id, time.monotonic() - started, result.issues)
        return _Done(node.id, "ran", finished, result.issues)

    def _context(self, node: Node) -> BuildContext:
        def log(text: str) -> None:
            self._queue.put(LogLine(node.id, text))

        request = self.request
        return BuildContext(
            self.graph.root, request.manifest, request.profile, request.tools, log, self.cancel
        )

    def _failure(self, node: Node, exc: Exception) -> _Done:
        cancelled = isinstance(exc, Cancelled) and self.cancel.cancelled
        if isinstance(exc, CTStudioError):
            error = exc
        else:
            _LOG.error("build step %s failed unexpectedly", node.id, exc_info=exc)
            error = BuildError(node.id, "an unexpected error happened")
        event = NodeFailed(node.id, error.user_message, error.hint, cancelled)
        return _Done(node.id, "cancelled" if cancelled else "failed", event)

    def _summary(self, duration: float) -> BuildSummary:
        order = [node.id for node in self.graph.nodes]

        def having(status: Status) -> tuple[str, ...]:
            return tuple(i for i in order if self._status.get(i) == status)

        not_run = tuple(node.id for node in self._waiting)
        issues = tuple(issue for i in having("ran") for issue in self._issues[i])
        return BuildSummary(
            _outcome(having("failed"), having("cancelled"), not_run, self.cancel),
            having("ran"),
            having("skipped"),
            having("failed"),
            having("cancelled"),
            not_run,
            issues,
            duration,
        )


def _outcome(
    failed: tuple[str, ...],
    cancelled: tuple[str, ...],
    not_run: tuple[str, ...],
    token: CancelToken,
) -> Outcome:
    if failed:
        return "failed"
    if cancelled or (not_run and token.cancelled):
        return "cancelled"
    return "succeeded"
