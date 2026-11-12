"""Gated real Lock/Discard work and assertion-friendly waits for outside-edit GUI tests."""

from __future__ import annotations

import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

from assign_helpers import kcl_bytes, write
from pytestqt.exceptions import TimeoutError as WaitTimedOut
from pytestqt.qtbot import QtBot

from ctstudio.core.components.assign import Assigned
from ctstudio.core.components.edited import discard_edit, lock_as_manual
from ctstudio.core.components.state import ProjectState, record, save_state
from ctstudio.core.components.status import settings_key
from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import LaunchController
from ctstudio.gui.services import AppServices


def edited_project(folder: Path) -> Project:
    project = Project.create(folder / "Pistë 日本", "T")
    path = write(project.root / ".ctstudio/stage/course.kcl", kcl_bytes())
    entry = record(project.root, settings_key(project.manifest, "kcl"), [path], [])
    save_state(project.root, ProjectState({"kcl": entry}))
    path.write_bytes(kcl_bytes(0x480))  # a different size, even on coarse Windows clocks
    return project


class EditWork:
    def __init__(self) -> None:
        self.gate = threading.Event()
        self.entered = threading.Event()
        self.error: BaseException | None = None
        self.calls: list[tuple[Project, str, str, threading.Thread]] = []

    def _call(self, project: Project, part: str, action: str) -> None:
        self.calls.append((project, part, action, threading.current_thread()))
        self.entered.set()
        assert self.gate.wait(10), "test did not release its worker"
        if self.error is not None:
            raise self.error

    def lock(self, project: Project, part: str) -> Assigned:
        self._call(project, part, "lock")
        return lock_as_manual(project, part)

    def discard(self, project: Project, part: str) -> Path:
        self._call(project, part, "discard")
        return discard_edit(project, part)


def settled(qtbot: QtBot, condition: Callable[[], bool]) -> bool:
    try:
        qtbot.waitUntil(condition, timeout=5000)
    except WaitTimedOut:
        pass
    return condition()


def outcome(call: Callable[[], object]) -> object:
    try:
        return call()
    except BaseException as exc:  # a crash is an assertion failure at the caller
        return exc


@contextmanager
def owned(folder: Path) -> Generator[tuple[AppServices, Project, EditWork], None, None]:
    work = EditWork()
    services = AppServices(launch=LaunchController(lock=work.lock, discard=work.discard))
    project = edited_project(folder)
    services.project = project  # no startup status job; exercise the request's own guards
    try:
        yield services, project, work
    finally:
        work.gate.set()
        services.editing = False
        assert services.shutdown(10), "outside-edit request retained ownership after release"
        project.close()
