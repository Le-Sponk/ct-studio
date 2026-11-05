"""Event-held launch services for tests; no discovery, settings, or desktop processes."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors, folders
from ctstudio.gui.blender_launch import BlenderLaunchService
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.folder_reveal import FolderRevealService
from ctstudio.gui.launch_controller import THREAD_NAME, LaunchController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService

SOURCE = "source 日本.blend"


class LaunchWork(BlenderLaunchService, FolderRevealService):
    """Both blocking services; each call waits for ``gate`` and records its thread."""

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.entered = threading.Event()
        self.calls: list[tuple[Project, str | None, threading.Thread]] = []
        self.error: BaseException | None = None
        self.blender_receipt = editors.Launched("blender", 123, Path(SOURCE), ("Old Blender.",))
        self.folder_receipt = folders.OpenedFolder(Path("folder 日本"), 456)

    def _run(self, project: Project, component: str | None) -> None:
        self.calls.append((project, component, threading.current_thread()))
        self.entered.set()
        if not self.gate.wait(10):
            raise TimeoutError("test worker was not released")
        if self.error is not None:
            raise self.error

    def launch(self, project: Project) -> editors.Launched:
        self._run(project, None)
        return self.blender_receipt

    def reveal(self, project: Project, component_id: str) -> folders.OpenedFolder:
        self._run(project, component_id)
        return self.folder_receipt


def services_with(work: LaunchWork) -> AppServices:
    status = StatusService(evaluate=lambda _project, _tools: {}, find_tools=lambda **_kw: ())
    controller = LaunchController(blender=work, folders=work)
    return AppServices(launch=controller, status=status, build=BuildController())


def writable_project(folder: Path, *, source: bool = True) -> Project:
    blend = None
    if source:
        blend = folder / SOURCE  # beside, not inside: a new project needs an empty folder
        blend.write_bytes(b"synthetic")
    return Project.create(folder / "Launch 日本", "Launch 日本", blend=blend)


@contextmanager
def owned_launch(
    folder: Path, *, source: bool = True
) -> Iterator[tuple[AppServices, Project, LaunchWork]]:
    work = LaunchWork()
    services = services_with(work)
    project = writable_project(folder, source=source)
    services.adopt(project)
    try:
        yield services, project, work
    finally:
        work.gate.set()
        services.editing = False
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def own_workers() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == THREAD_NAME]


def outcome(call: Callable[[], bool]) -> bool | str:
    """The call's result, or the name of what it raised (so a raise fails an assertion)."""
    try:
        return call()
    except Exception as exc:  # recorded, then asserted against
        return type(exc).__name__
