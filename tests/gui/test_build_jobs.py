"""P5-T08c: Settings → Build, "This computer": how many build steps may run at once.

A machine setting in ``settings.json`` (``build_jobs``), shown on the Build page with or
without a project. A pick is saved at once on a worker through a fresh read (nothing is
written when the file already says so); a damaged or newer file is shown and never
overwritten. The next GUI build's runner gets the saved number (CLI: unit tests).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from build_fakes import FakeBuilds
from editor_owner_helpers import outcome
from editor_request_helpers import settled
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ctstudio.core.build import project_build
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildEvent, BuildSummary
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import Profile
from ctstudio.core.build.project_build import BuildPlan, build_project
from ctstudio.core.build.runner import BuildRequest, default_jobs
from ctstudio.core.components.status import ComponentStatus
from ctstudio.core.project import settings
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.project.settings import BUILD_IGNORED, BUILD_JOBS, UserSettings
from ctstudio.core.tools.process import CancelToken
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.build_settings import BuildJobsService
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.build_page import BuildPage

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
DONE = BuildSummary("succeeded", (), (), (), (), (), (), 0.0, None)


class HeldJobs(BuildJobsService):
    """The real service, with gates and planted failures; records each call's thread."""

    def __init__(self) -> None:
        super().__init__()
        self.load_gate: threading.Event | None = None
        self.save_gate: threading.Event | None = None
        self.save_error: Exception | None = None
        self.load_error: Exception | None = None
        self.calls: list[tuple[str, threading.Thread]] = []

    def load(self) -> int | None:
        gate = self.load_gate
        self.calls.append(("load", threading.current_thread()))
        if gate is not None:
            assert gate.wait(10)
        if self.load_error is not None:
            raise self.load_error
        return super().load()

    def save(self, jobs: int | None) -> int | None:
        gate = self.save_gate
        self.calls.append(("save", threading.current_thread()))
        if gate is not None:
            assert gate.wait(10)
        if self.save_error is not None:
            raise self.save_error
        return super().save(jobs)

    def names(self) -> list[str]:
        return [name for name, _thread in self.calls]


def no_statuses(_project: object, _tools: object) -> dict[str, ComponentStatus]:
    return {}


def no_tools(**_kwargs: object) -> tuple[()]:
    return ()


def empty_plan(root: Path, manifest: Manifest, profile: Profile, **_kw: object) -> BuildPlan:
    return BuildPlan(BuildGraph(root, []), BuildRequest(manifest, profile, {}, {}))


class Runner:
    """Stands in for ``run_build``: records how many steps at once it was given."""

    def __init__(self) -> None:
        self.jobs: list[int | None] = []

    def __call__(
        self,
        _graph: BuildGraph,
        _cache: BuildCache,
        _request: BuildRequest,
        _on_event: Callable[[BuildEvent], None],
        *,
        cancel: CancelToken,
        jobs: int | None = None,
    ) -> BuildSummary:
        assert not cancel.cancelled
        self.jobs.append(jobs)
        return DONE


def settings_file() -> Path:
    return settings.default_path()


def write(text: str) -> bytes:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path.read_bytes()


def saved_jobs() -> object:
    data = json.loads(settings_file().read_text(encoding="utf-8"))
    return data.get(BUILD_JOBS, "absent")


def files() -> list[str]:
    return sorted(p.name for p in settings_file().parent.iterdir())


@contextmanager
def page_with(
    qtbot: QtBot,
    folder: Path | None = None,
    *,
    held: HeldJobs | None = None,
    controller: BuildController | None = None,
) -> Generator[tuple[BuildPage, HeldJobs, AppServices]]:
    held = held if held is not None else HeldJobs()
    fake = FakeBuilds()
    build = (
        controller if controller is not None else BuildController(plan=fake.plan, build=fake.run)
    )
    services = AppServices(
        status=StatusService(evaluate=no_statuses, find_tools=no_tools), build=build
    )
    if folder is not None:
        services.adopt(Project.create(folder / "Jobs é", "Jobs é"))
    page = BuildPage(services, jobs_service=held)
    qtbot.addWidget(page)
    page.show()
    page.tabs.setCurrentWidget(page.jobs)
    try:
        assert settled(qtbot, lambda: not page.busy and not page.jobs.busy), "the page hung"
        yield page, held, services
    finally:
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def pick(qtbot: QtBot, page: BuildPage, jobs: int | None) -> None:
    combo = page.jobs.combo
    index = combo.findData(jobs)
    assert index >= 0, f"{jobs} is not offered"
    combo.setCurrentIndex(index)
    combo.activated.emit(index)
    assert settled(qtbot, lambda: not page.jobs.busy), "the save hung"


def test_with_no_project_the_choice_is_shown_and_saved(qtbot: QtBot) -> None:
    with page_with(qtbot) as (page, held, _services):
        assert page.jobs.isVisibleTo(page) and page.jobs.combo.isEnabled()
        assert page.jobs.combo.currentData() is None, "automatic is not shown for no setting"
        auto = page.jobs.combo.itemText(0)
        assert "Automatic" in auto and f"{default_jobs()}" in auto, auto
        pick(qtbot, page, 3)
        assert saved_jobs() == 3, "the pick was not saved"
        assert "Saved" in page.jobs.note.text() and "3" in page.jobs.note.text()
        assert page.jobs.combo.currentData() == 3 and page.jobs.banner.isHidden()
        assert held.names() == ["load", "save"]


def test_the_saved_number_is_shown_and_automatic_removes_it(qtbot: QtBot) -> None:
    write('{"format": 1, "build_jobs": 5, "future": [1]}')
    with page_with(qtbot) as (page, _held, _services):
        assert page.jobs.combo.currentData() == 5, "the saved number is not shown"
        pick(qtbot, page, None)
        assert saved_jobs() == "absent", "automatic kept the number"
        assert json.loads(settings_file().read_text(encoding="utf-8"))["future"] == [1]
        assert "Saved" in page.jobs.note.text() and page.jobs.combo.currentData() is None


def test_picking_what_is_saved_writes_nothing(qtbot: QtBot) -> None:
    write('{"format": 1, "build_jobs": 2}')
    with page_with(qtbot) as (page, held, _services):
        pick(qtbot, page, 2)
        assert held.names() == ["load", "save"]
        assert files() == ["settings.json"], "an unchanged pick made a backup"


def test_a_number_above_the_usual_list_is_still_shown(qtbot: QtBot) -> None:
    write('{"format": 1, "build_jobs": 64}')
    with page_with(qtbot) as (page, _held, _services):
        assert page.jobs.combo.currentData() == 64, "a large saved number is not shown"
        assert page.jobs.combo.findData(1) == 1, "the numbers do not start at 1"


@pytest.mark.parametrize(
    ("text", "said"),
    [('{"format": 1, "build_jobs": 0}', BUILD_JOBS), ('{"format": 2}', "newer version")],
    ids=["damaged", "newer"],
)
def test_an_unusable_file_is_shown_and_never_overwritten(
    qtbot: QtBot, text: str, said: str
) -> None:
    before = write(text)
    with page_with(qtbot) as (page, held, _services):
        banner = page.jobs.banner.text().replace("\u200b", "")
        assert said in banner and str(settings_file()) in banner, banner
        assert page.jobs.banner.isVisibleTo(page) and not page.jobs.combo.isEnabled()
        assert page.jobs.combo.isHidden(), "a choice that can do nothing is still shown"
        assert page.jobs.label.isHidden(), "the label of a hidden choice is still shown"
        assert page.jobs.intro.isHidden(), "the intro takes room from the reason"
        page.jobs.combo.activated.emit(2)  # past Qt's own disabling
        assert settled(qtbot, lambda: not page.jobs.busy)
        assert held.names() == ["load"], "a save was started on an unusable file"
    assert settings_file().read_bytes() == before and files() == ["settings.json"]


def test_a_file_damaged_after_it_was_read_is_refused_on_a_pick(qtbot: QtBot) -> None:
    write('{"format": 1}')
    with page_with(qtbot) as (page, held, _services):
        before = write('{"format": 1, "build_jobs": "four"}')
        pick(qtbot, page, 4)
        assert held.names() == ["load", "save"]
        assert settings_file().read_bytes() == before, "the damaged file was overwritten"
        assert BUILD_JOBS in page.jobs.banner.text() and page.jobs.combo.isHidden()
        write('{"format": 1, "build_jobs": 4}')
        page.reload()
        assert settled(qtbot, lambda: not page.jobs.busy)
        assert page.jobs.banner.isHidden() and page.jobs.combo.isVisibleTo(page)
        assert page.jobs.combo.currentData() == 4, "a good reread did not unlock the choice"


def test_a_pick_while_reading_or_saving_saves_nothing(qtbot: QtBot) -> None:
    held = HeldJobs()
    held.load_gate = threading.Event()
    with _held_page(qtbot, held) as page:
        assert not page.jobs.combo.isEnabled() and page.jobs.busy_bar.isVisibleTo(page)
        page.jobs.combo.activated.emit(2)  # while the first read runs
        page.reload()  # a second read is not started either
        held.load_gate.set()
        assert settled(qtbot, lambda: not page.jobs.busy)
        assert held.names() == ["load"], "a pick during the read was saved"
        held.save_gate = threading.Event()
        page.jobs.combo.activated.emit(page.jobs.combo.findData(3))
        assert settled(qtbot, lambda: page.jobs.busy and len(held.calls) == 2)
        assert not page.jobs.combo.isEnabled(), "the choice is on while it is being saved"
        assert page.jobs.busy_bar.isVisibleTo(page), "no sign of the running save"
        page.jobs.combo.activated.emit(page.jobs.combo.findData(5))  # while saving
        held.save_gate.set()
        assert settled(qtbot, lambda: not page.jobs.busy)
        assert held.names() == ["load", "save"] and saved_jobs() == 3


@contextmanager
def _held_page(qtbot: QtBot, held: HeldJobs) -> Generator[BuildPage]:
    """A page whose first read is still held by ``held``."""
    fake = FakeBuilds()
    build = BuildController(plan=fake.plan, build=fake.run)
    services = AppServices(
        status=StatusService(evaluate=no_statuses, find_tools=no_tools), build=build
    )
    page = BuildPage(services, jobs_service=held)
    qtbot.addWidget(page)
    page.show()
    page.tabs.setCurrentWidget(page.jobs)
    try:
        assert settled(qtbot, lambda: len(held.calls) == 1), "the first read never started"
        yield page
    finally:
        for gate in (held.load_gate, held.save_gate):
            if gate is not None:
                gate.set()
        assert settled(qtbot, lambda: not page.jobs.busy), "a read or save hung"
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def test_reads_and_saves_run_off_the_ui_thread(qtbot: QtBot) -> None:
    with page_with(qtbot) as (page, held, _services):
        pick(qtbot, page, 2)
        assert [name for name, _ in held.calls] == ["load", "save"]
        assert all(t is not threading.main_thread() for _, t in held.calls), "work on UI thread"


def test_an_unexpected_error_is_shown_and_the_choice_goes_back(qtbot: QtBot) -> None:
    write('{"format": 1, "build_jobs": 2}')
    with page_with(qtbot) as (page, held, _services):
        held.save_error = RuntimeError()
        pick(qtbot, page, 6)
        banner = page.jobs.banner.text()
        assert "Could not save" in banner and "RuntimeError" in banner, banner
        assert page.jobs.combo.currentData() == 2, "the failed pick is still shown"
        assert page.jobs.combo.isEnabled() and saved_jobs() == 2
        held.save_error = None
        pick(qtbot, page, 6)
        assert page.jobs.banner.isHidden() and saved_jobs() == 6, "a retry did not save"


def test_a_keyboard_pick_keeps_the_keyboard_on_the_choice(qtbot: QtBot) -> None:
    with page_with(qtbot) as (page, _held, _services):
        combo = page.jobs.combo
        page.activateWindow()
        QApplication.processEvents()
        combo.setFocus()
        assert combo.hasFocus(), "the choice could not take the focus"
        QTest.keyClick(combo, Qt.Key.Key_Down)
        assert settled(qtbot, lambda: not page.jobs.busy and saved_jobs() == 1)
        assert combo.hasFocus(), "the save moved the keyboard elsewhere"


def test_the_choice_label_sits_above_it(qtbot: QtBot) -> None:
    with page_with(qtbot) as (page, _held, _services):
        label = page.jobs.label
        assert label.buddy() is page.jobs.combo, "the label's shortcut does not reach it"
        assert label.geometry().bottom() <= page.jobs.combo.geometry().top(), "beside it"


def test_the_next_gui_build_runs_the_picked_number_of_steps(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = Runner()
    monkeypatch.setattr(project_build, "run_build", runner)
    controller = BuildController(plan=empty_plan, build=build_project)
    with page_with(qtbot, tmp_path, controller=controller) as (page, _held, services):
        summaries: list[BuildSummary] = []
        services.build.finished.connect(summaries.append)

        def finished(count: int) -> Callable[[], bool]:
            return lambda: len(summaries) == count

        for count, jobs in enumerate((None, 2, None), start=1):
            if jobs is not None or summaries:
                pick(qtbot, page, jobs)
            assert settled(qtbot, lambda: not services.status.busy), "the status check hung"
            assert services.start_build() is True, "the build did not start"
            assert settled(qtbot, finished(count)), "the build never finished"
        assert runner.jobs == [None, 2, None], "a build did not get the saved number"


def test_a_gui_build_with_a_damaged_file_says_so_and_lets_the_runner_choose(
    qtbot: QtBot, tmp_path: Path
) -> None:
    fake = FakeBuilds()
    controller = BuildController(plan=fake.plan, build=fake.run)
    with page_with(qtbot, tmp_path, controller=controller) as (_page, _held, services):
        notices: list[str] = []
        services.build.notice.connect(notices.append)
        before = write('{"format": 1, "build_jobs": 100}')
        assert settled(qtbot, lambda: not services.status.busy), "the status check hung"
        assert services.start_build() is True
        assert settled(qtbot, lambda: len(fake.ran) == 1 and not services.build.running)
        assert fake.ran[0]["jobs"] is None, "a damaged number reached the build"
        assert notices and BUILD_IGNORED in notices[0], notices
        assert settings_file().read_bytes() == before


def test_the_service_reads_fresh_and_skips_an_unchanged_save(tmp_path: Path) -> None:
    path = tmp_path / "s é" / "settings.json"
    service = BuildJobsService(settings_path=path)
    assert service.load() is None and not path.exists()
    assert service.save(None) is None and not path.exists(), "automatic wrote a new file"
    assert service.save(4) == 4 and settings.load(path).build_jobs() == 4
    settings.save(UserSettings().with_build_jobs(7), path)  # changed outside meanwhile
    assert service.load() == 7
    before = sorted(p.name for p in path.parent.iterdir())
    assert service.save(7) == 7
    assert sorted(p.name for p in path.parent.iterdir()) == before, "an unchanged save wrote"


def test_a_read_that_fails_unexpectedly_leaves_the_choice_off(qtbot: QtBot) -> None:
    held = HeldJobs()
    held.load_error = RuntimeError("synthetic read failure")
    with page_with(qtbot, held=held) as (page, _held, _services):
        banner = page.jobs.banner.text()
        assert "Could not read" in banner and "synthetic read failure" in banner, banner
        assert not page.jobs.combo.isEnabled(), "a choice that was never read is on"
        page.jobs.combo.activated.emit(2)  # past Qt's own disabling
        assert settled(qtbot, lambda: not page.jobs.busy)
        assert held.names() == ["load"], "a pick before any good read was saved"
        held.load_error = None
        page.reload()
        assert settled(qtbot, lambda: not page.jobs.busy and page.jobs.combo.isEnabled())
        assert page.jobs.banner.isHidden(), "a good reread kept the old error"
