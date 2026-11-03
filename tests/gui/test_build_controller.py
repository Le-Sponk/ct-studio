"""P5-T01a: the build controller runs a whole build off the UI thread and reports it as signals.

``plan_build`` / ``build_project`` are replaced by a recording fake (``build_fakes``), so no
tool is searched for or started. Tests wait on signals, never sleep.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from build_fakes import (
    THREAD,
    WAIT,
    FakeBuilds,
    build_threads,
    fake,
    project,
    settings_with,
    summary,
)
from PySide6.QtCore import QCoreApplication
from pytestqt.qtbot import QtBot

from ctstudio.core.build.events import (
    BuildEvent,
    BuildFinished,
    BuildStarted,
    LogLine,
    NodeFinished,
    NodeStarted,
)
from ctstudio.core.errors import BuildGraphError, ProjectError, ToolNotFound
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["fake", "project"]  # fixtures used by name


_MADE: list[BuildController] = []


@pytest.fixture(autouse=True)
def _shut_down() -> Iterator[None]:
    """Every controller a test made is shut down, so no build thread outlives its test."""
    yield
    while _MADE:
        _MADE.pop().shutdown(WAIT / 1000)


def controller(qtbot: QtBot, fake: FakeBuilds, settings: Path | None = None) -> BuildController:
    made = BuildController(plan=fake.plan, build=fake.run, settings_path=settings)
    _MADE.append(made)
    return made


class Seen:
    """Everything the controller said, with the thread it was said on."""

    def __init__(self, made: BuildController) -> None:
        self.events: list[BuildEvent] = []
        self.finished: list[object] = []
        self.failed: list[object] = []
        self.notices: list[str] = []
        self.running: list[bool] = []
        self.threads: set[threading.Thread] = set()
        made.build_event.connect(lambda e: self._add(self.events, e))
        made.finished.connect(lambda s: self._add(self.finished, s))
        made.failed.connect(lambda e: self._add(self.failed, e))
        made.notice.connect(lambda t: self._add(self.notices, t))
        made.running_changed.connect(lambda r: self._add(self.running, r))

    def _add(
        self, where: list[object] | list[BuildEvent] | list[str] | list[bool], what: object
    ) -> None:
        self.threads.add(threading.current_thread())
        where.append(what)  # type: ignore[arg-type]


EVENTS: list[BuildEvent] = [
    BuildStarted(("stage:kcl", "assemble")),
    NodeStarted("stage:kcl"),
    LogLine("stage:kcl", "copied course.kcl"),
    NodeFinished("stage:kcl", 0.1, ()),
    NodeStarted("assemble"),
    NodeFinished("assemble", 0.2, ()),
    BuildFinished(summary(ran=("stage:kcl", "assemble"))),
]


# --- a build ------------------------------------------------------------------------------------


def test_every_event_arrives_in_order_on_the_ui_thread(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    fake.events = EVENTS
    made = controller(qtbot, fake)
    seen = Seen(made)
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        assert made.start(project)
    assert seen.events == EVENTS
    assert seen.finished == [EVENTS[-1].summary]  # type: ignore[union-attr]
    assert seen.failed == []
    assert seen.threads == {threading.main_thread()}


def test_planning_and_building_run_on_the_named_build_thread(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    made = controller(qtbot, fake)
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        made.start(project)
    assert len(fake.threads) == 2
    assert {thread.name for thread in fake.threads} == {THREAD}
    assert fake.threads[0] is fake.threads[1] is not threading.main_thread()


def test_the_build_gets_the_project_and_the_chosen_options(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    made = controller(qtbot, fake)
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        made.start(project, release=True, force=True, only="kcl")
    planned = fake.planned[0]
    assert planned["root"] == project.root
    assert planned["manifest"] is project.manifest
    assert planned["profile"] == "release"
    assert planned["only"] == "kcl"
    assert fake.ran[0]["force"] is True
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        made.start(project)
    assert fake.planned[1]["profile"] == "test"
    assert fake.planned[1]["only"] is None
    assert fake.ran[1]["force"] is False


def test_paths_set_in_settings_reach_the_plan(
    qtbot: QtBot, fake: FakeBuilds, project: Project, tmp_path: Path
) -> None:
    wszst = tmp_path / "tools é" / "wszst.exe"
    library = tmp_path / "auto-add ü"
    settings = settings_with(
        tmp_path, {"format": 1, "tools": {"wszst": str(wszst)}, "auto_add_library": str(library)}
    )
    made = controller(qtbot, fake, settings)
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        made.start(project)
    assert fake.planned[0]["configured"] == {"wszst": wszst}
    assert fake.planned[0]["library"] == library


def test_a_damaged_settings_file_is_reported_and_the_build_goes_on(
    qtbot: QtBot, fake: FakeBuilds, project: Project, tmp_path: Path
) -> None:
    made = controller(qtbot, fake, settings_with(tmp_path, "{not json"))
    seen = Seen(made)
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        made.start(project)
    assert fake.planned[0]["configured"] == {}
    assert fake.planned[0]["library"] is None
    assert len(seen.notices) == 1
    assert "paths set in ct studio are ignored for this build" in seen.notices[0].lower()


def test_running_is_true_from_start_until_the_result_is_shown(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    fake.gate = threading.Event()
    made = controller(qtbot, fake)
    seen = Seen(made)
    assert not made.running
    with qtbot.waitSignal(made.build_event, timeout=WAIT):
        made.start(project)
    assert made.running
    assert seen.running == [True]
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        fake.gate.set()
    assert not made.running
    assert seen.running == [True, False]


# --- refusals -----------------------------------------------------------------------------------


def test_a_second_build_is_refused_while_one_runs(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    fake.gate = threading.Event()
    made = controller(qtbot, fake)
    with qtbot.waitSignal(made.build_event, timeout=WAIT):
        assert made.start(project)
    assert not made.start(project)
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        fake.gate.set()
    assert len(fake.planned) == 1
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        assert made.start(project)  # once it ended, a new one may start


def test_a_read_only_project_is_not_built(qtbot: QtBot, fake: FakeBuilds, project: Project) -> None:
    second = Project.open(project.root)  # the first one holds the lock
    assert second.read_only
    made = controller(qtbot, fake)
    seen = Seen(made)
    with qtbot.waitSignal(made.failed, timeout=WAIT):
        assert not made.start(second)
    assert fake.planned == []
    assert not made.running
    error = seen.failed[0]
    assert isinstance(error, ProjectError)
    assert "in use" in error.user_message
    assert build_threads() == []


# --- failures -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        ToolNotFound("Wiimms SZS Tool", "Install it."),
        BuildGraphError("The Course model cannot be made in auto mode yet.", hint="Set a file."),
    ],
    ids=["missing tool", "cannot plan"],
)
def test_a_build_that_cannot_start_is_reported_as_failed(
    qtbot: QtBot, fake: FakeBuilds, project: Project, error: Exception
) -> None:
    fake.plan_error = error
    made = controller(qtbot, fake)
    seen = Seen(made)
    with qtbot.waitSignal(made.failed, timeout=WAIT):
        made.start(project)
    assert seen.failed == [error]
    assert seen.finished == []
    assert fake.ran == []
    assert not made.running
    assert seen.threads == {threading.main_thread()}


def test_an_unexpected_crash_still_reaches_the_ui(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    fake.run_error = RuntimeError("boom")
    made = controller(qtbot, fake)
    seen = Seen(made)
    with qtbot.waitSignal(made.failed, timeout=WAIT):
        made.start(project)
    assert isinstance(seen.failed[0], RuntimeError)
    assert not made.running
    with qtbot.waitSignal(made.finished, timeout=WAIT):  # and the next build still works
        fake.run_error = None
        made.start(project)


# --- stopping -----------------------------------------------------------------------------------


def test_cancel_reaches_the_running_build(qtbot: QtBot, fake: FakeBuilds, project: Project) -> None:
    fake.gate = threading.Event()
    made = controller(qtbot, fake)
    with qtbot.waitSignal(made.build_event, timeout=WAIT):
        made.start(project)
    assert not fake.cancels[0].cancelled
    made.cancel()
    assert fake.cancels[0].cancelled
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        fake.gate.set()


def test_each_build_gets_a_fresh_cancel_token(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    made = controller(qtbot, fake)
    made.cancel()  # nothing running: nothing to do, and the next build is not cancelled
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        made.start(project)
    assert not fake.cancels[0].cancelled


def test_running_changed_is_said_only_when_it_changes(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    made = controller(qtbot, fake)
    seen = Seen(made)
    assert made.shutdown(1)  # nothing running: still not running, nothing to say
    assert seen.running == []
    with qtbot.waitSignal(made.finished, timeout=WAIT):
        made.start(project)
    assert made.shutdown(1)
    assert seen.running == [True, False]


def test_shutdown_cancels_and_waits_so_no_build_thread_is_left(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    fake.gate = threading.Event()
    made = controller(qtbot, fake)
    with qtbot.waitSignal(made.build_event, timeout=WAIT):
        made.start(project)
    assert len(build_threads()) == 1
    threading.Timer(0.05, fake.gate.set).start()  # the build ends once it sees the cancel
    assert made.shutdown(WAIT / 1000)
    assert fake.cancels[0].cancelled
    assert build_threads() == []


def test_what_an_ended_build_still_had_queued_is_not_shown_after_shutdown(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    fake.events = EVENTS
    made = controller(qtbot, fake)
    seen = Seen(made)
    made.start(project)
    assert made.shutdown(WAIT / 1000)  # the build ran to its end; its signals wait in the queue
    QCoreApplication.processEvents()  # the thread has ended: all it sent is queued now
    assert seen.events == []
    assert seen.finished == []
    assert not made.running
    assert seen.running == [True, False]


def test_shutdown_reports_a_build_that_would_not_stop(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    fake.gate = threading.Event()
    made = controller(qtbot, fake)
    with qtbot.waitSignal(made.build_event, timeout=WAIT):
        made.start(project)
    assert not made.shutdown(0.05)
    fake.gate.set()
    assert made.shutdown(WAIT / 1000)


def test_a_controller_deleted_mid_build_lets_the_thread_end_quietly(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    from shiboken6 import Shiboken

    fake.gate = threading.Event()
    fake.events = EVENTS
    made = BuildController(plan=fake.plan, build=fake.run)
    with qtbot.waitSignal(made.build_event, timeout=WAIT):
        made.start(project)
    Shiboken.delete(made)  # the window went away without shutting down first
    errors: list[threading.ExceptHookArgs] = []
    previous = threading.excepthook
    threading.excepthook = errors.append
    try:
        fake.gate.set()
        qtbot.waitUntil(lambda: build_threads() == [], timeout=WAIT)
    finally:
        threading.excepthook = previous
    assert errors == []
    assert fake.cancels[0].cancelled
