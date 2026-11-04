"""TD-012: a broken progress receiver must not strand cached work without part records."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest
from build_runner_helpers import REQUEST, build, make_root, step

from ctstudio.core.build.cache import BuildCache, Lookup
from ctstudio.core.build.events import (
    BuildEvent,
    BuildFinished,
    BuildStarted,
    LogLine,
    NodeFinished,
    NodeStarted,
)
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import BuildContext, Node, StepFailed
from ctstudio.core.build.runner import run_build
from ctstudio.core.components.state import STATE_FILE, load_state
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.validation.issues import Issue

pytestmark = pytest.mark.timeout(30)


@pytest.mark.parametrize("error", [RuntimeError("progress receiver broke"), KeyboardInterrupt()])
def test_callback_error_records_workers_that_finish_during_cleanup(
    tmp_path: Path, error: BaseException
) -> None:
    root = make_root(tmp_path)
    release = threading.Event()

    def work(_ctx: BuildContext) -> None:
        assert release.wait(10)

    node = replace(step(root, "model", work), component="course_model")

    def broken(event: BuildEvent) -> None:
        if isinstance(event, NodeStarted):
            release.set()
            raise error

    with pytest.raises(type(error)) as caught:
        run_build(
            BuildGraph(root, [node]),
            BuildCache.load(root),
            REQUEST,
            broken,
            cancel=CancelToken(),
            jobs=1,
        )
    assert caught.value is error
    assert BuildCache.load(root).check(node, {}).fresh
    assert "course_model" in load_state(root).components


def test_completed_worker_log_is_kept_without_retrying_the_broken_callback(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    release = threading.Event()
    delivered: list[BuildEvent] = []

    def work(ctx: BuildContext) -> None:
        assert release.wait(10)
        ctx.log("worker finished after receiver failed")

    def broken(event: BuildEvent) -> None:
        delivered.append(event)
        if isinstance(event, NodeStarted):
            release.set()
            raise RuntimeError("stop receiving")

    node = replace(step(root, "model", work), component="course_model")
    with pytest.raises(RuntimeError, match="stop receiving"):
        run_build(
            BuildGraph(root, [node]),
            BuildCache.load(root),
            REQUEST,
            broken,
            cancel=CancelToken(),
            jobs=1,
        )
    assert [type(event).__name__ for event in delivered] == ["BuildStarted", "NodeStarted"]
    [path] = (root / ".ctstudio/logs").glob("*.log")
    text = path.read_text(encoding="utf-8")
    assert "worker finished after receiver failed" in text
    assert "[model] finished in" in text
    assert text.count("[model] started") == 1
    assert "Build succeeded" not in text


def assert_no_workers() -> None:
    assert not [t for t in threading.enumerate() if t.name.startswith("ctstudio-build")]


def test_parallel_cleanup_records_only_success_and_never_starts_waiting_work(
    tmp_path: Path,
) -> None:
    root = make_root(tmp_path)
    release = threading.Event()
    seen: list[str] = []

    def work(ctx: BuildContext) -> None:
        assert release.wait(10)
        seen.append("ran")
        ctx.log("completed during cleanup")

    issue = Issue(
        "error", "minimap", "cleanup.failed", "Cannot make the map.", "Fix it.", "ctstudio"
    )

    def fail(_ctx: BuildContext) -> None:
        assert release.wait(10)
        raise StepFailed(issue)

    nodes = [
        replace(step(root, "model", work), component="course_model"),
        replace(step(root, "collision", work), component="kcl"),
        replace(step(root, "bad", fail), component="minimap"),
        replace(step(root, "later", work), component="skybox"),
    ]

    def broken(event: BuildEvent) -> None:
        if isinstance(event, NodeStarted):
            release.set()
            raise RuntimeError("receiver failed")

    with pytest.raises(RuntimeError, match="receiver failed"):
        run_build(
            BuildGraph(root, nodes),
            BuildCache.load(root),
            REQUEST,
            broken,
            cancel=CancelToken(),
            jobs=3,
        )
    assert set(load_state(root).components) == {"course_model", "kcl"}
    assert [BuildCache.load(root).check(n, {}).fresh for n in nodes] == [True, True, False, False]
    assert not nodes[3].outputs[0].exists()
    assert seen == ["ran", "ran"]
    assert "[bad]" in log_text(root) and "Cannot make the map." in log_text(root)
    summary, _ = build(root, nodes[:2])
    assert summary.skipped == ("model", "collision")
    assert seen == ["ran", "ran"]
    assert_no_workers()


def log_text(root: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in (root / ".ctstudio/logs").glob("*.log"))


def test_queued_cache_hit_restores_deleted_part_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_root(tmp_path)
    cached = replace(step(root, "cached"), component="course_model")
    build(root, [cached])
    (root / STATE_FILE).unlink()
    release = threading.Event()
    original_check = BuildCache.check

    def delayed_check(self: BuildCache, node: Node, versions: Mapping[str, str | None]) -> Lookup:
        if node.id == "cached":
            assert release.wait(10)
        return original_check(self, node, versions)

    def broken(event: BuildEvent) -> None:
        if isinstance(event, NodeStarted):
            release.set()
            raise RuntimeError("receiver failed")

    monkeypatch.setattr(BuildCache, "check", delayed_check)
    trigger = replace(step(root, "trigger"), component="kcl")
    with pytest.raises(RuntimeError, match="receiver failed"):
        run_build(
            BuildGraph(root, [trigger, cached]),
            BuildCache.load(root),
            REQUEST,
            broken,
            cancel=CancelToken(),
            jobs=2,
        )
    assert set(load_state(root).components) == {"course_model", "kcl"}
    assert "[cached] skipped" in log_text(root)
    assert_no_workers()


@pytest.mark.parametrize("when", [BuildStarted, BuildFinished, LogLine, NodeFinished])
def test_errors_at_other_callback_boundaries_preserve_completed_work(
    tmp_path: Path, when: type[BuildStarted | BuildFinished | LogLine | NodeFinished]
) -> None:
    root = make_root(tmp_path)
    error = RuntimeError("original callback error")
    ran: list[bool] = []

    def work(ctx: BuildContext) -> None:
        ran.append(True)
        ctx.log("work message")

    def broken(event: BuildEvent) -> None:
        if isinstance(event, when):
            raise error

    node = replace(step(root, "model", work), component="course_model")
    with pytest.raises(type(error)) as caught:
        run_build(
            BuildGraph(root, [node]),
            BuildCache.load(root),
            REQUEST,
            broken,
            cancel=CancelToken(),
            jobs=1,
        )
    assert caught.value is error
    expected = set() if when is BuildStarted else {"course_model"}
    assert set(load_state(root).components) == expected
    assert bool(ran) == (when is not BuildStarted)
    assert_no_workers()
