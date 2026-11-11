"""P5-T06a: the watcher bridge and the app's services, with scripted watchers (no timing).

A ``ScriptedWatcher`` stands in for ``core.project.watch.ProjectWatcher``: the test calls its
``on_change``/``on_error`` from another thread, as the real one would.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from build_fakes import WAIT, FakeBuilds, fake, project
from PySide6.QtCore import QCoreApplication, SignalInstance
from pytestqt.qtbot import QtBot

from ctstudio.core.components.status import ProjectLike
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.project.watch import OnChange, OnError, WatchPlan, watch_plan
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.watcher_bridge import STOP_GRACE_S, WatcherBridge

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["fake", "project"]  # fixtures used by name


class ScriptedWatcher:
    def __init__(self, plan: WatchPlan, on_change: OnChange, on_error: OnError) -> None:
        self.plan, self.on_change, self.on_error = plan, on_change, on_error
        self.started = self.stopped = False
        self.running = False
        self.start_error: ProjectError | None = None
        self.stuck = False  # join never succeeds
        self.joined: list[float] = []
        self.broken = False  # a thread failed: alive maybe, but not watching everything

    @property
    def alive(self) -> bool:
        return self.running

    @property
    def intact(self) -> bool:
        return self.running and not self.broken and not self.stopped

    def start(self) -> None:
        if self.start_error is not None:
            raise self.start_error
        self.started = self.running = True

    def stop(self) -> None:
        self.stopped = True
        if not self.stuck:
            self.running = False

    def join(self, timeout: float) -> bool:
        self.joined.append(timeout)
        return not self.running

    def report(self, *paths: Path) -> None:
        """A change, sent from another thread like the real watcher's."""
        thread = threading.Thread(target=self.on_change, args=(frozenset(paths),))
        thread.start()
        thread.join()

    def fail(self, error: ProjectError, *, give_up: bool = True) -> None:
        """Report ``error`` from another thread; like the real watcher, it then stops whole
        (``give_up=False`` models a report arriving while a thread is still ending)."""
        self.broken = give_up
        thread = threading.Thread(target=self.on_error, args=(error,))
        thread.start()
        thread.join()


class Watchers:
    def __init__(self) -> None:
        self.made: list[ScriptedWatcher] = []
        self.next_error: ProjectError | None = None

    def __call__(self, plan: WatchPlan, on_change: OnChange, on_error: OnError) -> ScriptedWatcher:
        made = ScriptedWatcher(plan, on_change, on_error)
        made.start_error, self.next_error = self.next_error, None
        self.made.append(made)
        return made


@pytest.fixture
def watchers() -> Watchers:
    return Watchers()


def emitted(signal: SignalInstance, action: Callable[[], object]) -> list[object]:
    """What ``signal`` carried while ``action`` ran and queued deliveries were flushed."""
    got: list[object] = []

    def keep(value: object) -> None:
        got.append(value)

    signal.connect(keep)
    try:
        action()
        QCoreApplication.sendPostedEvents()
    finally:
        signal.disconnect(keep)
    return got


# --- the bridge ----------------------------------------------------------------------------------


def test_follow_watches_the_projects_plan_and_reports_changes_on_the_ui_thread(
    qtbot: QtBot, watchers: Watchers, tmp_path: Path
) -> None:
    bridge = WatcherBridge(make=watchers)
    root = tmp_path / "proj é"
    from ctstudio.core.project.manifest import ProjectInfo

    manifest = Manifest(ProjectInfo(name="T", blend=str(tmp_path / "art" / "t.blend")))
    assert bridge.follow(root, manifest)
    (made,) = watchers.made
    assert made.started
    assert made.plan == watch_plan(root, manifest)
    assert bridge.watching == root
    threads: list[threading.Thread] = []

    def where(_root: object) -> None:
        threads.append(threading.current_thread())

    bridge.changed.connect(where)
    got = emitted(bridge.changed, lambda: made.report(root / "files" / "x"))
    assert got == [root]
    assert threads == [threading.main_thread()]
    assert emitted(bridge.changed, lambda: made.report()) == []  # nothing changed


def test_following_the_same_plan_again_keeps_the_watcher(
    watchers: Watchers, tmp_path: Path
) -> None:
    from ctstudio.core.project.manifest import ProjectInfo

    bridge = WatcherBridge(make=watchers)
    root = tmp_path / "p"
    assert bridge.follow(root, Manifest(ProjectInfo(name="T")))
    assert not bridge.follow(root, Manifest(ProjectInfo(name="renamed")))  # same folders
    assert len(watchers.made) == 1
    assert bridge.follow(root, Manifest(ProjectInfo(name="T", blend=str(tmp_path / "a.blend"))))
    first, second = watchers.made
    assert first.stopped and not second.stopped


def test_a_watcher_that_died_is_replaced_on_the_next_follow(
    watchers: Watchers, tmp_path: Path
) -> None:
    from ctstudio.core.project.manifest import ProjectInfo

    bridge = WatcherBridge(make=watchers)
    manifest = Manifest(ProjectInfo(name="T"))
    bridge.follow(tmp_path, manifest)
    watchers.made[0].running = False  # it gave up (e.g. the folder could not be watched)
    assert bridge.follow(tmp_path, manifest)
    assert len(watchers.made) == 2
    half = watchers.made[1]
    half.broken = True  # one thread failed, the other still runs (still alive)
    assert bridge.follow(tmp_path, manifest), "a half-dead watcher must be replaced"
    assert len(watchers.made) == 3
    assert half.stopped


def test_news_from_a_replaced_or_stopped_watcher_is_dropped(
    qtbot: QtBot, watchers: Watchers, tmp_path: Path
) -> None:
    from ctstudio.core.project.manifest import ProjectInfo

    bridge = WatcherBridge(make=watchers)
    bridge.follow(tmp_path / "a", Manifest(ProjectInfo(name="A")))
    bridge.follow(tmp_path / "b", Manifest(ProjectInfo(name="B")))
    old, new = watchers.made
    assert old.stopped
    assert emitted(bridge.changed, lambda: old.report(tmp_path / "a" / "x")) == []
    error = ProjectError("old")
    assert emitted(bridge.failed, lambda: old.fail(error)) == []
    assert emitted(bridge.changed, lambda: new.report(tmp_path / "b" / "x")) == [tmp_path / "b"]
    bridge.stop()
    assert new.stopped
    assert bridge.watching is None
    assert emitted(bridge.changed, lambda: new.report(tmp_path / "b" / "x")) == []


def test_failures_arrive_on_the_ui_thread_and_a_start_failure_is_not_raised(
    qtbot: QtBot, watchers: Watchers, tmp_path: Path
) -> None:
    from ctstudio.core.project.manifest import ProjectInfo

    bridge = WatcherBridge(make=watchers)
    manifest = Manifest(ProjectInfo(name="T"))
    bridge.follow(tmp_path, manifest)
    error = ProjectError("cannot watch", hint="Refresh")
    assert emitted(bridge.failed, lambda: watchers.made[0].fail(error)) == [error]
    refused = ProjectError("no threads left")
    watchers.next_error = refused
    watchers.made[0].running = False
    try:
        got = emitted(bridge.failed, lambda: bridge.follow(tmp_path, manifest))
    except ProjectError as exc:  # raised on the UI thread: the wrong answer, not a crash
        got = [exc, "raised"]
    assert got == [refused]
    assert bridge.watching is None
    half_started = watchers.made[-1]
    half_started.running = True  # its first thread was still ending when start gave up
    assert bridge.shutdown(0) is False  # so shutdown still waits for it
    assert half_started.stopped
    half_started.running = False
    assert bridge.shutdown(0) is True


def test_shutdown_waits_and_reports_a_watcher_that_would_not_stop(
    watchers: Watchers, tmp_path: Path
) -> None:
    from ctstudio.core.project.manifest import ProjectInfo

    bridge = WatcherBridge(make=watchers)
    bridge.follow(tmp_path / "a", Manifest(ProjectInfo(name="A")))
    watchers.made[0].stuck = True
    bridge.follow(tmp_path / "b", Manifest(ProjectInfo(name="B")))
    assert bridge.shutdown(0) is False  # the first is still running
    # A watcher ends within moments of being asked: even a no-wait close gives it that.
    assert watchers.made[0].joined == [STOP_GRACE_S]
    assert bridge.shutdown(30) is False
    assert watchers.made[0].joined[-1] == 30
    watchers.made[0].running = False
    assert bridge.shutdown(0) is True
    assert bridge.watching is None


# --- in the app's services -----------------------------------------------------------------------


def _no_tools(**_kw: object) -> tuple[()]:
    return ()


class CountingStatus(StatusService):
    def __init__(self) -> None:
        super().__init__(evaluate=lambda _p, _t: {}, find_tools=_no_tools, delay_ms=20)
        self.asked: list[Path] = []

    def request(self, project: ProjectLike) -> None:
        self.asked.append(project.root)
        super().request(project)


def services(watchers: Watchers, builds: FakeBuilds) -> tuple[AppServices, CountingStatus]:
    status = CountingStatus()
    made = AppServices(
        build=BuildController(plan=builds.plan, build=builds.run),
        status=status,
        watcher=WatcherBridge(make=watchers),
    )
    return made, status


def test_opening_watches_the_project_and_closing_stops_it(
    watchers: Watchers, fake: FakeBuilds, project: Project, tmp_path: Path
) -> None:
    root = project.root
    project.close()
    made, _status = services(watchers, fake)
    opened = made.open_project(root)
    assert made.watcher.watching == root
    assert watchers.made[0].plan == watch_plan(root, opened.manifest)
    other = tmp_path / "Autre é"
    Project.create(other, "Autre").close()
    made.open_project(other)
    assert watchers.made[0].stopped
    assert made.watcher.watching == other
    made.close_project()
    assert watchers.made[1].stopped
    assert made.watcher.watching is None
    assert made.follow_files() is False  # nothing open: nothing watched
    assert made.shutdown(1)


def test_adopting_a_project_watches_it(
    watchers: Watchers, fake: FakeBuilds, project: Project
) -> None:
    made, _status = services(watchers, fake)
    made.adopt(project)
    assert made.watcher.watching == project.root
    assert made.shutdown(1)


def test_a_change_asks_for_statuses_but_not_while_building(
    qtbot: QtBot, watchers: Watchers, fake: FakeBuilds, project: Project
) -> None:
    made, status = services(watchers, fake)
    made.adopt(project)
    qtbot.waitUntil(lambda: not made.status.busy, timeout=WAIT)
    status.asked.clear()
    watcher = watchers.made[0]
    emitted(made.watcher.changed, lambda: watcher.report(project.root / "files" / "x"))
    assert status.asked == [project.root]
    qtbot.waitUntil(lambda: not made.status.busy, timeout=WAIT)
    fake.gate = threading.Event()
    with qtbot.waitSignal(made.build.build_event, timeout=WAIT):
        made.start_build()
    status.asked.clear()
    emitted(made.watcher.changed, lambda: watcher.report(project.root / "files" / "x"))
    assert status.asked == []  # the build's own refresh follows
    with qtbot.waitSignal(made.build.finished, timeout=WAIT):
        fake.gate.set()
    assert status.asked == [project.root]
    assert made.shutdown(WAIT / 1000)


def test_a_change_for_another_root_asks_nothing(
    qtbot: QtBot, watchers: Watchers, fake: FakeBuilds, project: Project, tmp_path: Path
) -> None:
    made, status = services(watchers, fake)
    made.adopt(project)
    status.asked.clear()
    made.watcher.changed.emit(tmp_path / "elsewhere")
    assert status.asked == []
    assert made.shutdown(1)


def test_shutdown_reports_a_watcher_still_stopping_and_keeps_the_project(
    watchers: Watchers, fake: FakeBuilds, project: Project
) -> None:
    made, _status = services(watchers, fake)
    made.adopt(project)
    watchers.made[0].stuck = True
    assert made.shutdown(0) is False
    assert made.project is project
    assert not project.read_only
    watchers.made[0].running = False
    assert made.shutdown(0) is True
    assert made.project is None
