"""P5-T06a: an outside edit reaches the dashboard by itself (real watcher, real statuses).

The project is synthetic: a made course model is written into ``.ctstudio/stage/`` and
recorded the way the build records it, so the card starts Ready.
"""

# pyright: reportPrivateUsage=false
# The tests read the dashboard's shown project and wait for the bridge's real watcher.

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from build_fakes import FakeBuilds
from pytestqt.exceptions import TimeoutError as WaitTimedOut
from pytestqt.qtbot import QtBot
from test_watcher_bridge import Watchers

from ctstudio.core.components.state import GENERATED_DIR, ProjectState, record, save_state
from ctstudio.core.components.status import settings_key
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.core.project.watch import WATCH_THREAD, ProjectWatcher
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.dashboard import Dashboard
from ctstudio.gui.watcher_bridge import WatcherBridge

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
NOTICE_S = 2.0  # P5-T06: an outside edit shows within 2 s
MODEL = "course_model.brres"


def no_tools(**_kw: object) -> tuple[()]:
    return ()


def made_project(folder: Path) -> Project:
    project = Project.create(folder / "Pistë 日本", "Pistë 日本")
    output = project.root / GENERATED_DIR / MODEL
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"made by CT Studio")
    key = settings_key(project.manifest, "course_model")
    made = record(project.root, key, [output], [])
    save_state(project.root, ProjectState({"course_model": made}))
    return project


def real_services(watcher: WatcherBridge | None = None) -> AppServices:
    tools = frozenset(TOOL_BY_ID)

    def all_tools(**_kw: object) -> frozenset[str]:
        return tools

    status = StatusService(find_tools=all_tools)
    return AppServices(status=status, build=BuildController(), watcher=watcher)


@contextmanager
def shown(
    qtbot: QtBot, services: AppServices, project: Project
) -> Generator[Dashboard, None, None]:
    services.adopt(project)
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        page.resize(900, 800)
        page.show()
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy, timeout=10_000)
        yield page
    finally:
        assert services.shutdown(10)


def settled(qtbot: QtBot, condition: Callable[[], bool], timeout_ms: int = 10_000) -> bool:
    """Wait for ``condition``; its final value, so a test asserts it (a timeout is a wrong
    answer, not a crash)."""
    try:
        qtbot.waitUntil(condition, timeout=timeout_ms)
    except WaitTimedOut:
        pass
    return condition()


def state_of(page: Dashboard, part: str) -> str:
    return page.cards[part].status_label.text()


def watch_threads() -> list[str]:
    import threading

    names = {WATCH_THREAD, f"{WATCH_THREAD}-outside"}
    return [t.name for t in threading.enumerate() if t.name in names]


def test_an_edited_made_file_shows_on_its_card_within_two_seconds(
    qtbot: QtBot, tmp_path: Path
) -> None:
    services = real_services()
    with shown(qtbot, services, made_project(tmp_path)) as page:
        assert state_of(page, "course_model") == "ready"
        project = page._project
        assert project is not None
        assert services.watcher.watching == project.root
        real = services.watcher._watcher
        assert isinstance(real, ProjectWatcher)
        assert real.wait_ready(10), "the watcher never started watching"
        output = project.root / GENERATED_DIR / MODEL
        begun = time.monotonic()
        output.write_bytes(b"edited in BrawlCrate")
        st = output.stat()
        os.utime(output, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
        qtbot.waitUntil(
            lambda: state_of(page, "course_model") == "edited outside CT Studio", timeout=10_000
        )
        took = time.monotonic() - begun
        assert took < NOTICE_S, f"the card changed after {took:.2f} s"
        assert f"{MODEL} was changed outside CT Studio" in page.cards["course_model"].summary.text()
        assert page.notice.text() == "Statuses checked."
    assert watch_threads() == []


def test_a_change_starts_a_visible_check_but_not_during_a_build(
    qtbot: QtBot, tmp_path: Path
) -> None:
    import threading

    watchers, builds = Watchers(), FakeBuilds()
    services = AppServices(
        status=StatusService(evaluate=lambda _p, _t: {}, find_tools=no_tools),
        build=BuildController(plan=builds.plan, build=builds.run),
        watcher=WatcherBridge(make=watchers),
    )
    with shown(qtbot, services, made_project(tmp_path)) as page:
        assert page._project is not None
        root = page._project.root
        services.watcher.changed.emit(root)
        assert page.busy  # an outside change starts a visible check
        assert page.checking.isVisible()
        qtbot.waitUntil(lambda: not page.busy, timeout=10_000)
        services.watcher.changed.emit(root.parent / "another project")
        assert not page.busy
        builds.gate = threading.Event()
        with qtbot.waitSignal(services.build.build_event, timeout=10_000):
            assert services.start_build()
        services.watcher.changed.emit(root)
        assert not page.busy  # the build's own refresh will show the change
        with qtbot.waitSignal(services.build.finished, timeout=10_000):
            builds.gate.set()
        assert page.busy  # ... and here it is
        qtbot.waitUntil(lambda: not page.busy, timeout=10_000)


def test_watching_problems_have_their_own_notice_until_a_refresh_watches_again(
    qtbot: QtBot, tmp_path: Path
) -> None:
    watchers = Watchers()
    services = AppServices(
        status=StatusService(evaluate=lambda _p, _t: {}, find_tools=no_tools),
        build=BuildController(),
        watcher=WatcherBridge(make=watchers),
    )
    with shown(qtbot, services, made_project(tmp_path)) as page:
        notice = page.watch.notice
        assert notice.isHidden()
        error = ProjectError("CT Studio cannot notice changes in X (gone).", hint="Refresh.")
        first = watchers.made[-1]
        first.fail(error, give_up=False)  # (as if the watcher had not stopped yet)
        assert settled(qtbot, notice.isVisible), "the watching problem is not shown"
        assert notice.text() == str(error)
        assert notice.toolTip() == str(error)
        assert notice.accessibleDescription() == str(error)
        page.refresh()  # the old watcher is still intact: nothing new, the notice stays
        qtbot.waitUntil(lambda: not page.busy, timeout=10_000)
        assert notice.text() == str(error)
        assert page.notice.text() == "Some parts were not checked; try Refresh."  # its own label
        first.broken = True  # it gave up, as a failed watcher does
        page.refresh()
        assert len(watchers.made) == 2
        assert notice.isHidden()
        assert notice.text() == notice.toolTip() == notice.accessibleDescription() == ""
        qtbot.waitUntil(lambda: not page.busy, timeout=10_000)
        watchers.made[-1].running = False
        refused = ProjectError("no threads left", hint="Restart CT Studio.")
        watchers.next_error = refused
        try:
            page.refresh()  # a failure while starting again shows at once
        except ProjectError as exc:  # raised on the UI thread instead: a wrong answer
            pytest.fail(f"raised: {exc}")
        assert notice.isVisible()
        assert notice.text() == str(refused)


def test_publishing_a_manifest_with_an_outside_blend_watches_its_folder(
    qtbot: QtBot, tmp_path: Path
) -> None:
    import dataclasses

    watchers = Watchers()
    services = AppServices(
        status=StatusService(evaluate=lambda _p, _t: {}, find_tools=no_tools),
        build=BuildController(),
        watcher=WatcherBridge(make=watchers),
    )
    project = made_project(tmp_path)
    with shown(qtbot, services, project) as page:
        assert len(watchers.made) == 1
        blend = tmp_path / "Art é" / "track.blend"
        info = dataclasses.replace(project.manifest.project, blend=str(blend))
        project.manifest = dataclasses.replace(project.manifest, project=info)
        page.set_project(project, changed=True)  # as the details dialog publishes a save
        assert len(watchers.made) == 2
        assert watchers.made[0].stopped
        assert watchers.made[1].plan.outside == {blend.parent: frozenset({"track.blend"})}


def test_a_rebind_to_another_project_clears_the_watch_notice(qtbot: QtBot, tmp_path: Path) -> None:
    watchers = Watchers()
    services = AppServices(
        status=StatusService(evaluate=lambda _p, _t: {}, find_tools=no_tools),
        build=BuildController(),
        watcher=WatcherBridge(make=watchers),
    )
    with shown(qtbot, services, made_project(tmp_path)) as page:
        watchers.made[-1].fail(ProjectError("cannot watch"))
        assert settled(qtbot, page.watch.notice.isVisible)
        other = Project.create(tmp_path / "Autre é", "Autre")
        services.adopt(other)
        page.set_project(other)
        assert page.watch.notice.isHidden()
        assert services.watcher.watching == other.root


def test_a_watcher_check_cut_short_by_a_published_result_does_not_leave_it_checking(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Review of P5-T06a: a change starts a check; a saved assignment then clears the status
    work and refreshes. The dashboard must check again, not wait for a result never coming."""
    watchers = Watchers()
    services = AppServices(
        status=StatusService(evaluate=lambda _p, _t: {}, find_tools=no_tools),
        build=BuildController(),
        watcher=WatcherBridge(make=watchers),
    )
    with shown(qtbot, services, made_project(tmp_path)) as page:
        project = page._project
        assert project is not None
        watchers.made[-1].report(project.root / "files" / "course.kmp")
        qtbot.waitUntil(lambda: page.busy, timeout=5_000)
        page.recheck()  # what a published assignment does
        assert settled(qtbot, lambda: not page.busy, 5_000), "still checking"
        assert page.refresh_button.isEnabled()


def test_a_change_during_an_assignment_still_ends_in_checked_statuses(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """The copy into files/ is noticed while the assignment's result is still on its way;
    publishing it must not leave the dashboard checking with Refresh disabled."""
    from assign_helpers import AssignWork, kcl_bytes, write

    from ctstudio.gui.launch_controller import LaunchController

    watchers, work = Watchers(), AssignWork()
    work.release = threading.Event()
    services = AppServices(
        status=StatusService(evaluate=lambda _p, _t: {}, find_tools=no_tools, delay_ms=200),
        build=BuildController(),
        launch=LaunchController(assign=work),
        watcher=WatcherBridge(make=watchers),
    )
    with shown(qtbot, services, made_project(tmp_path)) as page:
        project = page._project
        assert project is not None
        services.start_assign("kcl", write(tmp_path / "mine.kcl", kcl_bytes()))
        assert work.done.wait(10)
        watchers.made[-1].report(project.root / "files" / "course.kcl")
        qtbot.waitUntil(lambda: page.busy, timeout=5_000)  # the change's check is waiting
        work.release.set()  # the result is published before that check answers
        qtbot.waitUntil(lambda: not services.launch.busy, timeout=10_000)
        assert settled(qtbot, lambda: not page.busy, 5_000), "still checking"
        assert page.refresh_button.isEnabled()
        assert project.manifest.components.kcl.file == "files/course.kcl"
