"""Shared pieces of the build controller GUI tests (P5-T01a): a recording planner and runner."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from ctstudio.core.build.events import BuildEvent, BuildFinished, BuildSummary
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.project_build import BuildPlan
from ctstudio.core.build.runner import BuildRequest
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.tools.process import CancelToken

WAIT = 10_000  # ms
THREAD = "ctstudio-build"


def summary(outcome: str = "succeeded", **kw: Any) -> BuildSummary:
    fields: dict[str, Any] = {
        "ran": ("stage:kcl", "assemble", "validate"),
        "skipped": (),
        "failed": (),
        "cancelled": (),
        "not_run": (),
        "issues": (),
        "duration": 0.5,
        "log": None,
    }
    fields.update(kw)
    return BuildSummary(outcome, **fields)  # type: ignore[arg-type]


class FakeBuilds:
    """Stands in for ``plan_build`` and ``build_project``; records threads and arguments.

    ``events`` are replayed through ``on_event`` and the last one's summary is returned.
    ``gate`` holds the build open (after its first event) until the test sets it.
    """

    def __init__(self) -> None:
        self.planned: list[dict[str, Any]] = []
        self.ran: list[dict[str, Any]] = []
        self.threads: list[threading.Thread] = []
        self.events: list[BuildEvent] = [BuildFinished(summary())]
        self.gate: threading.Event | None = None
        self.plan_error: BaseException | None = None
        self.run_error: BaseException | None = None
        self.cancels: list[CancelToken] = []

    def plan(self, root: Path, manifest: Manifest, profile: str, **kw: Any) -> BuildPlan:
        self.threads.append(threading.current_thread())
        self.planned.append({"root": root, "manifest": manifest, "profile": profile, **kw})
        if self.plan_error is not None:
            raise self.plan_error
        request = BuildRequest(manifest, profile, {}, {})  # type: ignore[arg-type]
        return BuildPlan(BuildGraph(root, []), request)

    def run(
        self, plan: BuildPlan, on_event: Callable[[BuildEvent], None], **kw: Any
    ) -> BuildSummary:
        gate = self.gate  # read once: a test may swap it while this build waits
        self.threads.append(threading.current_thread())
        self.ran.append({"plan": plan, **kw})
        self.cancels.append(kw["cancel"])
        for number, event in enumerate(self.events):
            on_event(event)
            if number == 0 and gate is not None:
                assert gate.wait(WAIT / 1000)
        if self.run_error is not None:
            raise self.run_error
        last = self.events[-1]
        assert isinstance(last, BuildFinished)
        return last.summary


@pytest.fixture
def fake() -> FakeBuilds:
    return FakeBuilds()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Project]:
    """A real, locked project in a non-ASCII folder, with the user folders kept in tmp_path."""
    users = tmp_path / "users"
    for name in ("WIN_PD_OVERRIDE_LOCAL_APPDATA", "WIN_PD_OVERRIDE_APPDATA"):
        monkeypatch.setenv(name, str(users / name))
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(users / name))
    made = Project.create(tmp_path / "Pistë 日本", "Pistë", slot="castle_course")
    yield made
    made.close()


def build_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == THREAD]


def settings_with(folder: Path, data: Mapping[str, object] | str) -> Path:
    """A user settings file in ``folder``: JSON from a mapping, or the text given as is."""
    import json

    path = folder / "settings é.json"
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return path
