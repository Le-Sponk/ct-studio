"""TD-012: secondary cleanup I/O errors must not hide the failed receiver."""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from build_runner_helpers import REQUEST, make_root, step

from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildEvent, NodeStarted
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import BuildContext, Node
from ctstudio.core.build.part_state import PartRecorder
from ctstudio.core.build.runner import run_build
from ctstudio.core.components.state import load_state
from ctstudio.core.tools.process import CancelToken

pytestmark = pytest.mark.timeout(30)


def gated_nodes(root: Path, release: threading.Event) -> list[Node]:
    def work(ctx: BuildContext) -> None:
        assert release.wait(10)
        ctx.log("completed after receiver failed")

    return [
        replace(step(root, "model", work), component="course_model"),
        replace(step(root, "collision", work), component="kcl"),
    ]


def fail_receiver(
    root: Path, nodes: list[Node], release: threading.Event, error: BaseException
) -> None:
    delivered: list[BuildEvent] = []

    def broken(event: BuildEvent) -> None:
        delivered.append(event)
        if isinstance(event, NodeStarted):
            release.set()
            raise error

    with pytest.raises(type(error)) as caught:
        run_build(
            BuildGraph(root, nodes),
            BuildCache.load(root),
            REQUEST,
            broken,
            cancel=CancelToken(),
            jobs=2,
        )
    assert caught.value is error
    assert [type(event).__name__ for event in delivered] == ["BuildStarted", "NodeStarted"]


def assert_worker_logs(root: Path, nodes: list[Node]) -> None:
    [path] = (root / ".ctstudio/logs").glob("*.log")
    text = path.read_text(encoding="utf-8")
    for node in nodes:
        assert f"[{node.id}] completed after receiver failed" in text
        assert f"[{node.id}] finished in" in text
    assert "Build succeeded" not in text


def assert_warning(caplog: pytest.LogCaptureFixture, error: Exception) -> None:
    assert any(
        record.name == "ctstudio.core.build.runner"
        and record.levelno == logging.WARNING
        and record.exc_info is not None
        and record.exc_info[1] is error
        for record in caplog.records
    )


@pytest.mark.parametrize("error", [RuntimeError("receiver failed"), KeyboardInterrupt()])
def test_record_fault_preserves_receiver_and_other_parallel_part(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: BaseException,
) -> None:
    root = make_root(tmp_path)
    release = threading.Event()
    nodes = gated_nodes(root, release)
    secondary = OSError("part output unreadable")
    attempted: list[Node] = []
    record = PartRecorder.record

    def faulty_record(self: PartRecorder, node: Node) -> None:
        attempted.append(node)
        if len(attempted) == 1:
            raise secondary
        record(self, node)

    monkeypatch.setattr(PartRecorder, "record", faulty_record)
    fail_receiver(root, nodes, release, error)
    assert len(attempted) == 2
    assert set(load_state(root).components) == {attempted[1].component}
    assert all(BuildCache.load(root).check(node, {}).fresh for node in nodes)
    assert_worker_logs(root, nodes)
    assert_warning(caplog, secondary)
    assert attempted[0].id in caplog.text


@pytest.mark.parametrize("error", [RuntimeError("receiver failed"), KeyboardInterrupt()])
@pytest.mark.parametrize("faults", [("cache",), ("parts",), ("cache", "parts")])
def test_cleanup_saves_are_independent_and_preserve_receiver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: BaseException,
    faults: tuple[str, ...],
) -> None:
    root = make_root(tmp_path)
    release = threading.Event()
    nodes = gated_nodes(root, release)
    attempted: list[str] = []
    errors = {name: OSError(f"{name} save failed") for name in faults}
    cache_save, parts_save = BuildCache.save, PartRecorder.save

    def save_cache(self: BuildCache) -> None:
        attempted.append("cache")
        if "cache" in errors:
            raise errors["cache"]
        cache_save(self)

    def save_parts(self: PartRecorder) -> None:
        attempted.append("parts")
        if "parts" in errors:
            raise errors["parts"]
        parts_save(self)

    monkeypatch.setattr(BuildCache, "save", save_cache)
    monkeypatch.setattr(PartRecorder, "save", save_parts)
    fail_receiver(root, nodes, release, error)
    assert attempted == ["cache", "parts"]
    expected = set() if "parts" in faults else {"course_model", "kcl"}
    assert set(load_state(root).components) == expected
    assert all(BuildCache.load(root).check(n, {}).fresh == ("cache" not in faults) for n in nodes)
    assert_worker_logs(root, nodes)
    for secondary in errors.values():
        assert_warning(caplog, secondary)


@pytest.mark.parametrize("operation", ["record", "cache", "parts"])
@pytest.mark.parametrize("error", [OSError("primary I/O failure"), KeyboardInterrupt()])
def test_primary_io_error_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, error: BaseException
) -> None:
    root = make_root(tmp_path)
    node = replace(step(root, "model"), component="course_model")
    delivered: list[BuildEvent] = []

    def fail(*_args: object) -> None:
        raise error

    if operation == "cache":
        monkeypatch.setattr(BuildCache, "save", fail)
    else:
        monkeypatch.setattr(PartRecorder, "record" if operation == "record" else "save", fail)
    with pytest.raises(type(error)) as caught:
        run_build(
            BuildGraph(root, [node]),
            BuildCache.load(root),
            REQUEST,
            delivered.append,
            cancel=CancelToken(),
            jobs=1,
        )
    assert caught.value is error
    assert all(type(event).__name__ != "BuildFinished" for event in delivered)


@pytest.mark.parametrize("operation", ["record", "cache", "parts"])
def test_secondary_keyboard_interrupt_is_not_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    root = make_root(tmp_path)
    release = threading.Event()
    nodes = gated_nodes(root, release)
    interrupt = KeyboardInterrupt()
    delivered: list[BuildEvent] = []

    def fail(*_args: object) -> None:
        raise interrupt

    def broken(event: BuildEvent) -> None:
        delivered.append(event)
        if isinstance(event, NodeStarted):
            release.set()
            raise RuntimeError("receiver failed first")

    if operation == "cache":
        monkeypatch.setattr(BuildCache, "save", fail)
    else:
        monkeypatch.setattr(PartRecorder, "record" if operation == "record" else "save", fail)
    with pytest.raises(KeyboardInterrupt) as caught:
        run_build(
            BuildGraph(root, nodes),
            BuildCache.load(root),
            REQUEST,
            broken,
            cancel=CancelToken(),
            jobs=2,
        )
    assert caught.value is interrupt
    assert [type(event).__name__ for event in delivered] == ["BuildStarted", "NodeStarted"]
