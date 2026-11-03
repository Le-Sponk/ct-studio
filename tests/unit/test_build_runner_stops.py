"""P4-T03a: the build runner when a step fails, when the user cancels, and its threads.

After the first failure nothing new starts and running steps finish; a cancel works the
same way, and running steps see it through ``ctx.cancel``. Every worker thread has ended
when ``run_build`` returns, also when the event handler raises.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from build_runner_helpers import REQUEST, Recorder, build, fail, make_root, step

from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildEvent, NodeFailed, NodeFinished
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import BuildContext, Node, NodeResult
from ctstudio.core.build.runner import run_build
from ctstudio.core.errors import BuildError, Cancelled
from ctstudio.core.tools.process import CancelToken

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_root(tmp_path)


# --- failure ----------------------------------------------------------------------------------


def test_a_failure_stops_new_steps_and_names_the_step(root: Path) -> None:
    nodes = [step(root, "a", fail), step(root, "b", needs=("a",)), step(root, "c")]
    summary, rec = build(root, nodes, jobs=1)
    failed = [e for e in rec.events if isinstance(e, NodeFailed)]
    assert len(failed) == 1
    assert failed[0].node_id == "a"
    assert "wszst" in failed[0].message
    assert failed[0].hint
    assert not failed[0].cancelled
    assert summary.outcome == "failed"
    assert summary.failed == ("a",)
    assert summary.not_run == ("b", "c")
    assert ("NodeStarted", "c") not in rec.kinds()


def test_running_steps_finish_after_another_fails(root: Path) -> None:
    started, failed = threading.Event(), threading.Event()

    def slow(_ctx: BuildContext) -> None:
        started.set()
        assert failed.wait(10), "bad's failure was seen while slow still ran"

    def fail_soon(_ctx: BuildContext) -> None:
        assert started.wait(10)
        fail(_ctx)

    class Watch(Recorder):
        def __call__(self, event: BuildEvent) -> None:
            super().__call__(event)
            if isinstance(event, NodeFailed):
                failed.set()

    nodes = [step(root, "slow", slow), step(root, "bad", fail_soon), step(root, "later")]
    summary, _ = build(root, nodes, jobs=2, recorder=Watch())
    assert summary.failed == ("bad",)
    assert summary.ran == ("slow",)
    assert summary.not_run == ("later",)
    assert BuildCache.load(root).check(nodes[0], {}).fresh, "finished work is kept"


def test_a_step_that_does_not_write_its_output_fails(root: Path) -> None:
    out = root / ".ctstudio" / "stage" / "x"
    lazy = Node("lazy", (), (out,), {}, (), frozenset(), 1, lambda _ctx: NodeResult())
    summary, rec = build(root, [lazy])
    assert summary.failed == ("lazy",)
    failed = next(e for e in rec.events if isinstance(e, NodeFailed))
    assert "did not write .ctstudio/stage/x" in failed.message


def test_an_unexpected_error_is_a_failure_not_a_crash(
    root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def bug(_ctx: BuildContext) -> None:
        raise ZeroDivisionError("oops")

    summary, rec = build(root, [step(root, "a", bug)])
    failed = next(e for e in rec.events if isinstance(e, NodeFailed))
    assert failed.message == BuildError("a", "an unexpected error happened").user_message
    assert "ZeroDivisionError" in caplog.text
    assert summary.outcome == "failed"


# --- cancel -----------------------------------------------------------------------------------


def test_cancel_stops_new_steps_and_running_ones_see_it(root: Path) -> None:
    token = CancelToken()

    def waits(ctx: BuildContext) -> None:
        token.cancel()  # the user presses Cancel while this step runs
        assert ctx.cancel.cancelled
        raise Cancelled("wszst")

    nodes = [step(root, "a", waits), step(root, "b")]
    summary, rec = build(root, nodes, jobs=1, cancel=token)
    failed = next(e for e in rec.events if isinstance(e, NodeFailed))
    assert failed.cancelled
    assert summary.outcome == "cancelled"
    assert summary.cancelled == ("a",)
    assert summary.failed == ()
    assert summary.not_run == ("b",)


def test_a_cancel_before_the_build_runs_nothing(root: Path) -> None:
    token = CancelToken()
    token.cancel()
    summary, rec = build(root, [step(root, "a")], cancel=token)
    assert summary.outcome == "cancelled"
    assert summary.not_run == ("a",)
    assert rec.kinds() == [("BuildStarted", ""), ("BuildFinished", "")]


def test_a_step_that_finishes_despite_a_cancel_counts(root: Path) -> None:
    token = CancelToken()
    summary, _ = build(
        root, [step(root, "a", lambda _c: token.cancel()), step(root, "b")], jobs=1, cancel=token
    )
    assert summary.ran == ("a",)
    assert summary.not_run == ("b",)
    assert summary.outcome == "cancelled"


def test_a_cancel_after_the_last_step_still_succeeds(root: Path) -> None:
    token = CancelToken()
    summary, _ = build(root, [step(root, "a", lambda _c: token.cancel())], cancel=token)
    assert summary.outcome == "succeeded"


def test_a_failure_wins_over_a_cancel(root: Path) -> None:
    token = CancelToken()

    def fail_and_cancel(ctx: BuildContext) -> None:
        token.cancel()
        fail(ctx)

    summary, _ = build(
        root, [step(root, "a", fail_and_cancel), step(root, "b")], jobs=1, cancel=token
    )
    assert summary.outcome == "failed"


def test_cancelled_raised_without_a_cancel_is_a_failure(root: Path) -> None:
    def odd(_ctx: BuildContext) -> None:
        raise Cancelled("wszst")

    summary, _ = build(root, [step(root, "a", odd)])
    assert summary.failed == ("a",)
    assert summary.outcome == "failed"


# --- threads ----------------------------------------------------------------------------------


def _build_threads() -> list[str]:
    return [t.name for t in threading.enumerate() if t.name.startswith("ctstudio-build")]


def test_no_thread_is_left_running(root: Path) -> None:
    # Only the build's own threads: other tests' threads may end at any time (CI saw one go).
    seen: list[list[str]] = []

    def busy(_ctx: BuildContext) -> NodeResult:
        seen.append(_build_threads())
        return NodeResult()

    nodes = [step(root, f"s{i}", busy) for i in range(8)]
    build(root, [*nodes, step(root, "bad", fail)], jobs=4)
    build(root, [step(root, f"t{i}") for i in range(8)], jobs=4)
    assert seen and all(names for names in seen), "the steps ran in the build's named threads"
    assert _build_threads() == []


def test_an_event_handler_error_still_stops_cleanly(root: Path) -> None:
    before = threading.active_count()

    def broken(event: BuildEvent) -> None:
        if isinstance(event, NodeFinished):
            raise RuntimeError("GUI bug")

    with pytest.raises(RuntimeError, match="GUI bug"):
        run_build(
            BuildGraph(root, [step(root, f"s{i}") for i in range(4)]),
            BuildCache.load(root),
            REQUEST,
            broken,
            cancel=CancelToken(),
            jobs=2,
        )
    assert threading.active_count() == before
