"""P5-T02b: welcome work never blocks Qt, missing history is explicit, locks are handed over."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QObject
from PySide6.QtWidgets import QLabel, QListWidget, QProgressBar, QPushButton, QWidget
from pytestqt.qtbot import QtBot

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.recent_projects import RecentProject, RecentProjects, RecentResult
from ctstudio.gui.views import welcome_page
from ctstudio.gui.views.welcome_page import WelcomePage

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
WAIT = 10000


class History(RecentProjects):
    def __init__(self) -> None:
        super().__init__()
        self.result = RecentResult(())
        self.calls: list[tuple[str, Path | None]] = []
        self.threads: list[threading.Thread] = []
        self.gate: threading.Event | None = None
        self.error: Exception | None = None

    def check(self) -> RecentResult:
        self.calls.append(("check", None))
        self.threads.append(threading.current_thread())
        if self.gate is not None:
            assert self.gate.wait(WAIT / 1000)
        if self.error is not None:
            raise self.error
        return self.result

    def remember(self, root: Path) -> RecentResult:
        self.calls.append(("remember", root))
        return self.check()

    def remove(self, root: Path) -> RecentResult:
        self.calls.append(("remove", root))
        self.result = RecentResult(tuple(e for e in self.result.entries if e.root != root))
        return self.check()


def widget[T: QObject](page: WelcomePage, kind: type[T], name: str) -> T:
    found = page.findChild(kind, name)
    assert found is not None
    return found


def button(page: WelcomePage, name: str) -> QPushButton:
    return widget(page, QPushButton, name)


def rows(page: WelcomePage) -> QListWidget:
    return widget(page, QListWidget, "recentProjects")


def problem(page: WelcomePage) -> str:
    return widget(page, QLabel, "welcomeProblem").text()


def make(
    qtbot: QtBot,
    history: History,
    *,
    choose_folder: Callable[[QWidget], Path | None] = lambda _parent: None,
    open_project: Callable[[Path], Project] = Project.open,
) -> WelcomePage:
    page = WelcomePage(history, choose_folder=choose_folder, open_project=open_project)
    qtbot.addWidget(page)
    page.show()
    qtbot.waitUntil(lambda: not page.busy, timeout=WAIT)
    return page


def assert_recent_labels(page: WelcomePage) -> None:
    first, second = rows(page).item(0), rows(page).item(1)
    assert first is not None and second is not None
    assert "Piste é" in first.text()
    assert "Missing folder" in second.text()


def test_loads_off_thread_and_marks_missing(qtbot: QtBot, tmp_path: Path) -> None:
    history = History()
    history.result = RecentResult(
        (RecentProject(tmp_path / "Piste é", False), RecentProject(tmp_path / "Gone", True))
    )
    page = make(qtbot, history)
    assert history.threads[0] is not threading.main_thread()
    assert rows(page).count() == 2
    assert not widget(page, QLabel, "recentEmpty").isVisible()
    assert_recent_labels(page)
    rows(page).setCurrentRow(1)
    assert not button(page, "openRecent").isEnabled()
    assert button(page, "removeRecent").isEnabled()
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        button(page, "removeRecent").click()
    assert rows(page).count() == 1
    assert ("remove", tmp_path / "Gone") in history.calls


def test_new_and_cancelled_folder_choice(qtbot: QtBot) -> None:
    history = History()
    page = make(qtbot, history, choose_folder=lambda _parent: None)
    with qtbot.waitSignal(page.new_requested):
        button(page, "welcomeNew").click()
    before = list(history.calls)
    button(page, "welcomeOpen").click()
    assert not page.busy
    assert history.calls == before
    assert "No recent projects" in widget(page, QLabel, "recentEmpty").text()


def test_open_recent_hands_over_project_on_ui_thread(qtbot: QtBot, tmp_path: Path) -> None:
    root = tmp_path / "Piste é"
    Project.create(root, "Piste é").close()
    history = History()
    history.result = RecentResult((RecentProject(root, False),))
    worker: list[threading.Thread] = []
    ui: list[threading.Thread] = []
    opened: list[Project] = []

    def load(path: Path) -> Project:
        worker.append(threading.current_thread())
        return Project.open(path)

    page = make(qtbot, history, open_project=load)
    page.opened.connect(lambda p: (opened.append(p), ui.append(threading.current_thread())))
    rows(page).setCurrentRow(0)
    with qtbot.waitSignal(page.opened, timeout=WAIT):
        button(page, "openRecent").click()
    try:
        assert opened[0].root == root
        assert not opened[0].read_only
        assert worker[0] is not threading.main_thread()
        assert ui == [threading.main_thread()]
        assert ("remember", root) in history.calls
        assert not page.busy
    finally:
        opened[0].close()


@pytest.mark.parametrize(
    "error", [ProjectError("Cannot open.", hint="Choose another folder."), RuntimeError("boom")]
)
def test_failed_open_keeps_history_and_shows_next_step(
    qtbot: QtBot, tmp_path: Path, error: Exception
) -> None:
    history = History()
    history.result = RecentResult((RecentProject(tmp_path, False),))

    def fail(_path: Path) -> Project:
        raise error

    page = make(qtbot, history, open_project=fail, choose_folder=lambda _parent: tmp_path)
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        button(page, "welcomeOpen").click()
    assert rows(page).count() == 1
    assert problem(page)
    assert "another folder" in problem(page).lower() or "try again" in problem(page).lower()
    assert not any(action == "remember" for action, _root in history.calls)


def test_damaged_settings_disable_remove_but_allow_open(qtbot: QtBot) -> None:
    history = History()
    history.result = RecentResult((), "Settings damaged. Fix the settings file.")
    page = make(qtbot, history)
    assert "Settings damaged" in problem(page)
    assert button(page, "welcomeOpen").isEnabled()
    assert not button(page, "removeRecent").isEnabled()


def assert_busy_controls(page: WelcomePage) -> None:
    assert page.busy
    assert not button(page, "welcomeNew").isEnabled()
    assert not button(page, "welcomeOpen").isEnabled()
    assert not rows(page).isEnabled()
    assert widget(page, QProgressBar, "welcomeBusy").isVisible()


def test_busy_refuses_duplicate_work_and_shutdown_releases_pending_open(
    qtbot: QtBot, tmp_path: Path
) -> None:
    history = History()
    page = make(qtbot, history)
    root = tmp_path / "Pending"
    Project.create(root, "Pending").close()
    history.gate = threading.Event()
    page.open_path(root)
    qtbot.waitUntil(lambda: ("remember", root) in history.calls, timeout=WAIT)
    assert_busy_controls(page)
    page.open_path(root)
    assert not page.shutdown(0)
    history.gate.set()
    assert page.shutdown(WAIT / 1000)
    assert len([c for c in history.calls if c == ("remember", root)]) == 1
    with Project.open(root) as project:
        assert not project.read_only
    delivered: list[Project] = []
    page.opened.connect(delivered.append)
    checked: list[bool] = []
    page.checked.connect(lambda: checked.append(True))
    QCoreApplication.processEvents()
    assert not page.busy
    assert delivered == []
    assert checked == []


def test_history_save_error_does_not_lose_successful_open(qtbot: QtBot, tmp_path: Path) -> None:
    history = History()
    root = tmp_path / "Opened"
    Project.create(root, "Opened").close()
    page = make(qtbot, history)
    history.error = ProjectError("Could not save recent projects.", hint="Check permissions.")
    with qtbot.waitSignal(page.opened, timeout=WAIT) as signal:
        page.open_path(root)
    assert signal.args is not None
    project = signal.args[0]
    assert isinstance(project, Project)
    assert "permissions" in problem(page)
    project.close()


class _SlowTail(threading.Thread):
    def run(self) -> None:
        super().run()
        time.sleep(0.2)  # deliberate lingering worker: join must precede delivery


def test_result_delivery_waits_for_worker_end(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = History()
    monkeypatch.setattr(welcome_page, "threading", SimpleNamespace(Thread=_SlowTail))
    page = WelcomePage(history)
    qtbot.addWidget(page)
    alive: list[bool] = []
    page.checked.connect(lambda: alive.append(history.threads[0].is_alive()))
    qtbot.waitUntil(lambda: bool(alive), timeout=WAIT)
    assert alive == [False]
