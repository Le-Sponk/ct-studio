"""P4-T03a: the build runner (``core.build.runner.run_build``) with synthetic steps.

A step starts once every step it waits for has succeeded or been skipped, and none of its
``resources`` is held by a running step; up to ``jobs`` run at once. A cache hit is skipped.
Events arrive one at a time. Failure, cancel and threads: ``test_build_runner_stops.py``.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from build_runner_helpers import build, make_root, step

from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import (
    BuildFinished,
    BuildStarted,
    LogLine,
    NodeFinished,
    NodeSkipped,
)
from ctstudio.core.build.node import BuildContext, Node, NodeResult
from ctstudio.core.build.runner import default_jobs
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.validation.issues import Issue

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_root(tmp_path)


# --- order and events -------------------------------------------------------------------------


def test_events_in_order_for_a_chain(root: Path) -> None:
    def talk(ctx: BuildContext) -> NodeResult:
        ctx.log("making b")
        return NodeResult()

    summary, rec = build(root, [step(root, "a"), step(root, "b", talk, needs=("a",))], jobs=1)
    assert rec.kinds() == [
        ("BuildStarted", ""),
        ("NodeStarted", "a"),
        ("NodeFinished", "a"),
        ("NodeStarted", "b"),
        ("LogLine", "b"),
        ("NodeFinished", "b"),
        ("BuildFinished", ""),
    ]
    assert rec.events[0] == BuildStarted(steps=("a", "b"))
    assert rec.events[4] == LogLine(node_id="b", text="making b")
    assert rec.events[-1] == BuildFinished(summary=summary)
    assert summary.outcome == "succeeded"
    assert summary.ran == ("a", "b")
    assert summary.skipped == summary.failed == summary.cancelled == summary.not_run == ()
    assert summary.duration >= 0


def test_a_step_starts_only_after_the_steps_it_waits_for(root: Path) -> None:
    nodes = [step(root, "a"), step(root, "b", needs=("a",)), step(root, "c", needs=("b",))]
    _, rec = build(root, nodes, jobs=4)
    order = [k for k in rec.kinds() if k[0] in ("NodeStarted", "NodeFinished")]
    assert order == [
        ("NodeStarted", "a"), ("NodeFinished", "a"),
        ("NodeStarted", "b"), ("NodeFinished", "b"),
        ("NodeStarted", "c"), ("NodeFinished", "c"),
    ]  # fmt: skip


def test_issues_are_reported_per_step_and_in_the_summary(root: Path) -> None:
    issue = Issue("warning", "kmp", "kmp.x", "No checkpoints.", None, "ctstudio")
    summary, rec = build(root, [step(root, "a", lambda _ctx: NodeResult(issues=(issue,)))])
    finished = [e for e in rec.events if isinstance(e, NodeFinished)]
    assert finished[0].issues == (issue,)
    assert finished[0].duration >= 0
    assert summary.issues == (issue,)
    assert summary.outcome == "succeeded"


def test_an_empty_build_succeeds(root: Path) -> None:
    summary, rec = build(root, [])
    assert rec.kinds() == [("BuildStarted", ""), ("BuildFinished", "")]
    assert summary.outcome == "succeeded"


def test_the_context_carries_the_request_and_the_cancel_token(root: Path) -> None:
    seen: list[BuildContext] = []
    token = CancelToken()
    build(root, [step(root, "a", lambda ctx: seen.append(ctx) and None)], cancel=token)
    assert seen[0].root == root
    assert seen[0].profile == "test"
    assert seen[0].cancel is token


# --- parallel ---------------------------------------------------------------------------------


def test_independent_steps_run_at_the_same_time(root: Path) -> None:
    barrier = threading.Barrier(4, timeout=10)
    nodes = [step(root, f"s{i}", lambda _ctx: barrier.wait() and None) for i in range(4)]
    summary, _ = build(root, nodes, jobs=4)
    assert summary.outcome == "succeeded", "a barrier of 4 opens only if 4 steps run at once"


def test_parallel_is_faster_than_one_at_a_time(root: Path) -> None:
    nodes = [step(root, f"s{i}", lambda _ctx: time.sleep(0.25) and None) for i in range(4)]
    started = time.monotonic()
    build(root, nodes, jobs=4)
    parallel = time.monotonic() - started
    started = time.monotonic()
    build(
        root,
        [step(root, f"t{i}", lambda _ctx: time.sleep(0.25) and None) for i in range(4)],
        jobs=1,
    )
    serial = time.monotonic() - started
    assert serial >= 1.0
    assert parallel < serial * 0.6, (parallel, serial)


def test_no_more_than_jobs_steps_run_at_once(root: Path) -> None:
    counter = Concurrency()
    build(root, [step(root, f"s{i}", counter.work) for i in range(6)], jobs=2)
    assert counter.peak == 2


def test_steps_sharing_a_resource_never_overlap(root: Path) -> None:
    blender = Concurrency()
    free = Concurrency()
    nodes = [
        *(step(root, f"b{i}", blender.work, resources=frozenset({"blender"})) for i in range(3)),
        *(step(root, f"f{i}", free.work) for i in range(3)),
    ]
    summary, _ = build(root, nodes, jobs=4)
    assert summary.outcome == "succeeded"
    assert summary.ran == ("b0", "b1", "b2", "f0", "f1", "f2"), "a freed resource is reusable"
    assert blender.peak == 1
    assert free.peak >= 2


def test_a_step_waiting_for_a_resource_does_not_hold_up_others(root: Path) -> None:
    """``blocked`` waits for ``slow``'s resource while the free step ``fast`` runs beside it."""
    running, gate = threading.Event(), threading.Event()

    def slow(_ctx: BuildContext) -> None:
        running.set()
        assert gate.wait(10), "fast never ran while slow held the resource"

    def fast(_ctx: BuildContext) -> None:
        assert running.wait(10)
        gate.set()

    nodes = [
        step(root, "slow", slow, resources=frozenset({"stage:a"})),
        step(root, "blocked", resources=frozenset({"stage:a"})),
        step(root, "fast", fast),
    ]
    summary, _ = build(root, nodes, jobs=2)
    assert summary.outcome == "succeeded"


class Concurrency:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.now = 0
        self.peak = 0

    def work(self, _ctx: BuildContext) -> None:
        with self._lock:
            self.now += 1
            self.peak = max(self.peak, self.now)
        time.sleep(0.05)
        with self._lock:
            self.now -= 1


def test_jobs_must_be_at_least_one(root: Path) -> None:
    with pytest.raises(ValueError, match="jobs must be at least 1"):
        build(root, [step(root, "a")], jobs=0)


def test_default_jobs_is_at_most_four(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("os.cpu_count", lambda: 16)
    assert default_jobs() == 4
    monkeypatch.setattr("os.cpu_count", lambda: 2)
    assert default_jobs() == 2
    monkeypatch.setattr("os.cpu_count", lambda: None)
    assert default_jobs() == 1


# --- cache ------------------------------------------------------------------------------------


def test_an_unchanged_step_is_skipped_next_time(root: Path) -> None:
    runs: list[str] = []

    def nodes() -> list[Node]:
        return [step(root, "a", lambda _c: runs.append("a")), step(root, "b", needs=("a",))]

    build(root, nodes())
    summary, rec = build(root, nodes())
    assert runs == ["a"]
    assert summary.skipped == ("a", "b")
    assert summary.ran == ()
    assert [k for k in rec.kinds() if k[1]] == [("NodeSkipped", "a"), ("NodeSkipped", "b")]
    assert NodeSkipped(node_id="a") in rec.events


def test_the_cache_is_saved_at_the_end(root: Path) -> None:
    build(root, [step(root, "a")])
    assert BuildCache.load(root).check(step(root, "a"), {}).fresh


def test_a_changed_step_runs_again_and_so_do_steps_after_it(root: Path) -> None:
    build(root, [step(root, "a"), step(root, "b", needs=("a",)), step(root, "c")])
    changed = step(root, "a", lambda _c: None, params={"level": 2})
    summary, _ = build(root, [changed, step(root, "b", needs=("a",)), step(root, "c")])
    assert summary.ran == ("a",), "b's input was rewritten with the same content"
    assert summary.skipped == ("b", "c")
