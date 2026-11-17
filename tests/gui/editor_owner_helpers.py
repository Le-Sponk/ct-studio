"""Event-held editor preparation/dispatch services for the joined launch owner."""

from __future__ import annotations

import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

from launch_controller_helpers import LaunchWork, writable_project
from PySide6.QtCore import QCoreApplication
from pytestqt.qtbot import QtBot

from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors
from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.gui.editor_launch import EditorLaunchService, EditorOption, PreparedEditors
from ctstudio.gui.launch_controller import LaunchController, LaunchResult

DOCUMENT_NAME = "course 日本.brres"
BUILTIN = EditorChoice("builtin", "brawlcrate")
CUSTOM = EditorChoice("custom", "brawlcrate")


def snapshot_for(document: Path) -> PreparedEditors:
    options = tuple(
        EditorOption(choice, choice.namespace, "available", "found", "")
        for choice in (BUILTIN, CUSTOM)
    )
    return PreparedEditors(document, ".brres", options)


class EditorWork(EditorLaunchService):
    """Records each blocking call and its thread; each waits for ``gate``."""

    def __init__(self) -> None:
        super().__init__()
        self.gate = threading.Event()
        self.entered = threading.Event()
        self.calls: list[tuple[str, Project, Path, EditorChoice | None, threading.Thread]] = []
        self.error: BaseException | None = None
        self.snapshots: list[PreparedEditors] = []  # the exact receipts returned
        self.launched = editors.Launched("brawlcrate", 321, Path(DOCUMENT_NAME), ("Warned.",))

    def _run(
        self, kind: str, project: Project, document: Path, choice: EditorChoice | None
    ) -> None:
        self.calls.append((kind, project, document, choice, threading.current_thread()))
        self.entered.set()
        if not self.gate.wait(10):
            raise TimeoutError("test worker was not released")
        if self.error is not None:
            raise self.error

    def prepare(self, project: Project, document: Path) -> PreparedEditors:
        self._run("prepare", project, document, None)
        snapshot = snapshot_for(document)
        self.snapshots.append(snapshot)
        return snapshot

    def dispatch(self, project: Project, choice: EditorChoice, document: Path) -> editors.Launched:
        self._run("open", project, document, choice)
        return self.launched


class Results:
    def __init__(self, owner: LaunchController) -> None:
        self.owner = owner
        self.items: list[LaunchResult] = []
        self.threads: list[threading.Thread] = []
        owner.completed.connect(self.record)

    def record(self, payload: object) -> None:
        assert isinstance(payload, LaunchResult), "completion lost its typed result"
        self.items.append(payload)
        self.threads.append(threading.current_thread())

    def settle(self, qtbot: QtBot, count: int) -> LaunchResult:
        """Wait (bounded) for ``count`` results and an idle owner; return the last one."""
        for _ in range(500):
            if len(self.items) >= count and not self.owner.busy:
                break
            qtbot.wait(10)
        assert not self.owner.busy, "the editor request stranded the owner"
        assert len(self.items) == count, f"expected {count} results, got {len(self.items)}"
        return self.items[-1]


@contextmanager
def editor_owner(
    folder: Path, work: EditorLaunchService | None = None
) -> Generator[tuple[LaunchController, Project, Path]]:
    other = LaunchWork()
    other.gate.set()
    folder.mkdir(parents=True, exist_ok=True)
    owner = LaunchController(blender=other, folders=other, editors=work or EditorWork())
    project = writable_project(folder)
    document = project.root / DOCUMENT_NAME
    document.write_bytes(b"synthetic only")
    try:
        yield owner, project, document
    finally:
        if isinstance(work, EditorWork):
            work.gate.set()
        stopped = outcome(lambda: owner.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"
        QCoreApplication.sendPostedEvents()
        project.close()


def outcome(call: Callable[[], object]) -> object:
    """The call's result, or the exception it raised (asserted on by the caller)."""
    try:
        return call()
    except BaseException as exc:  # a raise must become an assertion failure
        return exc
