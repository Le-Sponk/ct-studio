"""P5-T01b: part statuses are worked out off the UI thread, a burst of requests at a time.

``evaluate`` and the tool finder are recording fakes, so no tool is searched for. Tests wait
on signals or on the service's state, never on a fixed sleep.
"""

from __future__ import annotations

import threading
from collections.abc import Collection, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from build_fakes import WAIT, FakeBuilds, fake, project, settings_with
from pytestqt.qtbot import QtBot

from ctstudio.core.components.status import ComponentStatus, ProjectLike, State
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import STATUS_THREAD, StatusResult, StatusService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["fake", "project"]  # fixtures used by name


class FakeStatus:
    """Answers like ``evaluate``: every part Ready, with the project's name as the reason."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, str, frozenset[str]]] = []
        self.threads: list[threading.Thread] = []
        self.gate: threading.Event | None = None
        self.error: Exception | None = None
        self.found: list[Mapping[str, Path]] = []

    def evaluate(self, project: ProjectLike, tools: Collection[str]) -> dict[str, ComponentStatus]:
        gate = self.gate  # read once: a test may swap it while this call waits
        self.threads.append(threading.current_thread())
        self.calls.append((project.root, project.manifest.project.name, frozenset(tools)))
        if gate is not None:
            assert gate.wait(WAIT / 1000)
        if self.error is not None:
            raise self.error
        return {"kcl": ComponentStatus(State.READY, (project.manifest.project.name,))}

    def tools(self, *, configured: Mapping[str, Path]) -> frozenset[str]:
        self.threads.append(threading.current_thread())
        self.found.append(dict(configured))
        return frozenset({"wszst"})


@pytest.fixture
def status() -> FakeStatus:
    return FakeStatus()


_MADE: list[StatusService] = []


@pytest.fixture(autouse=True)
def _shut_down() -> Iterator[None]:
    yield
    while _MADE:
        assert _MADE.pop().shutdown(WAIT / 1000)


def service(status: FakeStatus, settings: Path | None = None) -> StatusService:
    made = StatusService(
        evaluate=status.evaluate, find_tools=status.tools, settings_path=settings, delay_ms=20
    )
    _MADE.append(made)
    return made


def arg(signal: Any) -> Any:
    """The first argument of a signal ``qtbot.waitSignal`` caught."""
    assert signal.args is not None
    return signal.args[0]


def status_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == STATUS_THREAD]


def results(made: StatusService) -> list[Any]:
    seen: list[Any] = []
    made.updated.connect(seen.append)
    made.failed.connect(seen.append)
    return seen


# --- one request ------------------------------------------------------------------------------


def test_statuses_are_worked_out_off_the_ui_thread(
    qtbot: QtBot, status: FakeStatus, project: Project
) -> None:
    made = service(status)
    with qtbot.waitSignal(made.updated, timeout=WAIT) as signal:
        made.request(project)
    result = arg(signal)
    assert isinstance(result, StatusResult)
    assert result.root == project.root
    assert result.statuses == {"kcl": ComponentStatus(State.READY, ("Pistë",))}
    assert result.settings_problem is None
    assert status.calls == [(project.root, "Pistë", frozenset({"wszst"}))]
    assert {thread.name for thread in status.threads} == {STATUS_THREAD}


def test_nothing_is_worked_out_before_the_delay_ends(
    qtbot: QtBot, status: FakeStatus, project: Project
) -> None:
    made = StatusService(evaluate=status.evaluate, find_tools=status.tools, delay_ms=60_000)
    _MADE.append(made)
    made.request(project)
    assert made.busy  # something is coming
    qtbot.wait(50)
    assert status.calls == []


def test_paths_set_in_settings_are_used_to_find_the_tools(
    qtbot: QtBot, status: FakeStatus, project: Project, tmp_path: Path
) -> None:
    wszst = tmp_path / "outils é" / "wszst.exe"
    made = service(status, settings_with(tmp_path, {"format": 1, "tools": {"wszst": str(wszst)}}))
    with qtbot.waitSignal(made.updated, timeout=WAIT):
        made.request(project)
    assert status.found == [{"wszst": wszst}]


def test_a_damaged_settings_file_is_said_and_the_statuses_still_come(
    qtbot: QtBot, status: FakeStatus, project: Project, tmp_path: Path
) -> None:
    made = service(status, settings_with(tmp_path, "{not json"))
    with qtbot.waitSignal(made.updated, timeout=WAIT) as signal:
        made.request(project)
    assert status.found == [{}]
    assert arg(signal).settings_problem is not None
    assert "not valid json" in arg(signal).settings_problem.lower()


# --- many requests ------------------------------------------------------------------------------


def test_a_burst_of_requests_is_worked_out_once(
    qtbot: QtBot, status: FakeStatus, project: Project
) -> None:
    made = service(status)
    seen = results(made)
    for _ in range(5):
        made.request(project)
    qtbot.waitUntil(lambda: not made.busy, timeout=WAIT)
    assert len(status.calls) == 1
    assert len(seen) == 1


def test_requests_during_a_run_give_exactly_one_more_run_for_the_newest_project(
    qtbot: QtBot, status: FakeStatus, project: Project, tmp_path: Path
) -> None:
    other = Project.create(tmp_path / "Autre piste", "Autre", slot="castle_course")
    status.gate = threading.Event()
    made = service(status)
    seen = results(made)
    made.request(project)
    qtbot.waitUntil(lambda: len(status.calls) == 1, timeout=WAIT)
    assert made.busy  # running, nothing waiting
    assert not made.pending
    for _ in range(3):
        made.request(project)
    made.request(other)
    qtbot.waitUntil(lambda: made.pending, timeout=WAIT)  # the delay ended while it ran
    status.gate.set()
    qtbot.waitUntil(lambda: not made.busy, timeout=WAIT)
    other.close()
    assert [call[1] for call in status.calls] == ["Pistë", "Autre"]
    assert [result.root for result in seen] == [project.root, other.root]


def test_a_failed_evaluation_is_reported_and_the_next_one_works(
    qtbot: QtBot, status: FakeStatus, project: Project
) -> None:
    status.error = ProjectError("Could not read state.json.", hint="Delete it.")
    made = service(status)
    with qtbot.waitSignal(made.failed, timeout=WAIT) as signal:
        made.request(project)
    assert arg(signal) is status.error
    status.error = None
    with qtbot.waitSignal(made.updated, timeout=WAIT):
        made.request(project)


def test_an_unexpected_crash_is_reported_too(
    qtbot: QtBot, status: FakeStatus, project: Project
) -> None:
    status.error = RuntimeError("boom")
    made = service(status)
    with qtbot.waitSignal(made.failed, timeout=WAIT) as signal:
        made.request(project)
    assert isinstance(arg(signal), RuntimeError)
    assert not made.busy


# --- stopping -----------------------------------------------------------------------------------


def test_clear_drops_what_was_asked_and_what_is_running(
    qtbot: QtBot, status: FakeStatus, project: Project
) -> None:
    status.gate = threading.Event()
    made = service(status)
    seen = results(made)
    made.request(project)
    qtbot.waitUntil(lambda: len(status.calls) == 1, timeout=WAIT)
    made.request(project)
    qtbot.waitUntil(lambda: made.pending, timeout=WAIT)  # a second run is waiting
    made.clear()
    status.gate.set()
    qtbot.waitUntil(lambda: status_threads() == [], timeout=WAIT)
    qtbot.wait(60)  # longer than the delay: no second run starts
    assert seen == []
    assert len(status.calls) == 1
    assert not made.busy


def test_shutdown_waits_so_no_status_thread_is_left(
    qtbot: QtBot, status: FakeStatus, project: Project
) -> None:
    status.gate = threading.Event()
    made = service(status)
    made.request(project)
    qtbot.waitUntil(lambda: len(status.calls) == 1, timeout=WAIT)
    assert len(status_threads()) == 1
    assert not made.shutdown(0.05)  # still running
    status.gate.set()
    assert made.shutdown(WAIT / 1000)
    assert status_threads() == []


# --- in the app's services ----------------------------------------------------------------------


def app(status: FakeStatus, builds: FakeBuilds) -> AppServices:
    made = AppServices(
        build=BuildController(plan=builds.plan, build=builds.run),
        status=StatusService(evaluate=status.evaluate, find_tools=status.tools, delay_ms=20),
    )
    return made


def test_opening_a_project_and_each_build_ask_for_fresh_statuses(
    qtbot: QtBot, status: FakeStatus, fake: FakeBuilds, project: Project
) -> None:
    root = project.root
    project.close()
    made = app(status, fake)
    with qtbot.waitSignal(made.status.updated, timeout=WAIT):
        current = made.open_project(root)
    with qtbot.waitSignal(made.status.updated, timeout=WAIT):
        made.build.start(current)
    fake.plan_error = ProjectError("cannot", hint="no")
    with qtbot.waitSignal(made.status.updated, timeout=WAIT):
        made.build.start(current)  # a failed build may have changed files too
    assert len(status.calls) == 3
    assert made.shutdown(WAIT / 1000)


def test_closing_the_project_drops_a_status_still_to_come(
    qtbot: QtBot, status: FakeStatus, fake: FakeBuilds, project: Project
) -> None:
    root = project.root
    project.close()
    made = app(status, fake)
    seen = results(made.status)
    made.open_project(root)
    assert made.status.busy
    made.close_project()
    assert not made.status.busy
    qtbot.wait(60)
    assert seen == []
    assert made.shutdown(WAIT / 1000)
    assert status_threads() == []


def test_app_shutdown_waits_for_the_status_work_too(
    qtbot: QtBot, status: FakeStatus, fake: FakeBuilds, project: Project
) -> None:
    root = project.root
    project.close()
    status.gate = threading.Event()
    made = app(status, fake)
    current = made.open_project(root)
    qtbot.waitUntil(lambda: len(status.calls) == 1, timeout=WAIT)
    assert not made.shutdown(0.05)  # the statuses are still being worked out
    assert not current.read_only
    status.gate.set()
    assert made.shutdown(WAIT / 1000)
    assert current.read_only
    assert status_threads() == []
