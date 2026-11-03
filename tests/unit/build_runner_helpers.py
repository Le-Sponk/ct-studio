"""Synthetic build steps and an event recorder shared by the build runner tests."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildEvent, BuildSummary
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import BuildContext, Node, NodeResult
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.errors import ToolFailed
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.tools.process import CancelToken

Work = Callable[[BuildContext], object]
REQUEST = BuildRequest(Manifest(project=ProjectInfo(name="T")), "test", {}, {})


def make_root(tmp_path: Path) -> Path:
    project = tmp_path / "Pistë 日本"
    project.mkdir()
    return project


def step(
    root: Path,
    node_id: str,
    work: Work | None = None,
    *,
    needs: tuple[str, ...] = (),
    resources: frozenset[str] = frozenset(),
    params: dict[str, object] | None = None,
) -> Node:
    out = root / ".ctstudio" / "stage" / node_id

    def run(ctx: BuildContext) -> NodeResult:
        result = work(ctx) if work else None
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(node_id, encoding="utf-8")
        return result if isinstance(result, NodeResult) else NodeResult()

    inputs = tuple(root / ".ctstudio" / "stage" / n for n in needs)
    return Node(node_id, inputs, (out,), params or {}, (), resources, 1, run)


class Recorder:
    def __init__(self) -> None:
        self.events: list[BuildEvent] = []
        self.overlap = 0
        self._busy = False

    def __call__(self, event: BuildEvent) -> None:
        assert not self._busy, "two events were delivered at once"
        self._busy = True
        time.sleep(0.001)
        self.events.append(event)
        self._busy = False

    def kinds(self) -> list[tuple[str, str]]:
        return [(type(e).__name__, getattr(e, "node_id", "")) for e in self.events]


def build(
    root: Path,
    nodes: list[Node],
    *,
    jobs: int = 4,
    cancel: CancelToken | None = None,
    cache: BuildCache | None = None,
    recorder: Recorder | None = None,
) -> tuple[BuildSummary, Recorder]:
    recorder = recorder or Recorder()
    summary = run_build(
        BuildGraph(root, nodes),
        cache or BuildCache.load(root),
        REQUEST,
        recorder,
        cancel=cancel or CancelToken(),
        jobs=jobs,
    )
    return summary, recorder


def fail(_ctx: BuildContext) -> None:
    raise ToolFailed(["wszst", "check"], 1, "bad kmp", None)
