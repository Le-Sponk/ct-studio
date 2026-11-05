"""Real-window build fixtures with deterministic owner cleanup and synthetic projects."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread

from build_fakes import FakeBuilds, summary
from PySide6.QtCore import QCoreApplication
from pytestqt.exceptions import TimeoutError as QtTimeout
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.build.events import BuildFinished, BuildStarted
from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow

_JOIN = Thread.join


def eventually(qtbot: QtBot, predicate: Callable[[], bool], message: str) -> None:
    """Report missing observable behavior as an assertion, not a polling timeout."""
    try:
        qtbot.waitUntil(predicate, timeout=5000)
    except QtTimeout:
        pass
    assert predicate(), message


def result(call: Callable[[], bool]) -> bool | str:
    try:
        return call()
    except BaseException as error:
        return type(error).__name__


@contextmanager
def build_window(qtbot: QtBot, tmp_path: Path) -> Generator[tuple[MainWindow, Project, FakeBuilds]]:
    fake = FakeBuilds()
    fake.gate = Event()
    fake.events = [
        BuildStarted(("stage:kcl", "assemble")),
        BuildFinished(summary(ran=("stage:kcl", "assemble"))),
    ]
    view = MainWindow(quiet_services(fake))
    qtbot.addWidget(view)
    view.resize(1000, 900)
    view.show()
    eventually(qtbot, lambda: not view.welcome.busy, "welcome did not settle")
    project = Project.create(tmp_path / "Build window é", "Build window é")
    view._opened(project)
    eventually(qtbot, lambda: not view.dashboard.busy, "initial status did not settle")
    view.activateWindow()
    QCoreApplication.processEvents()
    try:
        yield view, project, fake
    finally:
        assert fake.gate is not None, "fixture lost its build gate"
        fake.gate.set()
        for worker in set(fake.threads):
            _JOIN(worker, 5)
            assert not worker.is_alive(), "fixture build worker did not exit"
        closed = result(view.close)
        assert closed is True, f"window cleanup refused or raised: {closed}"


def started(qtbot: QtBot, view: MainWindow, fake: FakeBuilds) -> None:
    eventually(qtbot, lambda: bool(fake.cancels), "build action never reached the worker")
    QCoreApplication.sendPostedEvents()
    assert view.services.build.running, "held build lost ownership"


def finished(qtbot: QtBot, view: MainWindow, fake: FakeBuilds) -> None:
    assert fake.gate is not None, "fixture lost its build gate"
    fake.gate.set()
    eventually(qtbot, lambda: not view.services.build.running, "build owner did not finish")
    eventually(qtbot, lambda: not view.dashboard.busy, "post-build status did not settle")
