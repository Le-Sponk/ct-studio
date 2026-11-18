"""P5-T07e2 helpers: a missing built-in editor, a recording Tools check and a whole window."""

# pyright: reportPrivateUsage=false
# (the window opens a project through its private `_opened`, as other window helpers do)

from __future__ import annotations

import threading
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

from editor_menu_helpers import MODEL, all_ready
from editor_owner_helpers import EditorWork, outcome
from editor_request_helpers import no_tools, settled
from launch_controller_helpers import LaunchWork, writable_project
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget
from pytestqt.qtbot import QtBot

from ctstudio.core.components.state import GENERATED_DIR
from ctstudio.core.project.project import Project
from ctstudio.core.tools.doctor import Report, ToolCheck
from ctstudio.core.tools.registry import TOOL_SPECS
from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.editor_launch import EditorOption, PreparedEditors
from ctstudio.gui.launch_controller import LaunchController
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices, ToolsService
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.tools_page import ToolsPage

RII = EditorChoice("builtin", "riistudio")
CRATE = EditorChoice("builtin", "brawlcrate")
MINE = EditorChoice("custom", "mine")
LORENZI = EditorChoice("builtin", "kmp_editor_lorenzi")
FOUND = "Executable found; loading is unverified."
RII_MISSING = EditorOption(RII, "RiiStudio", "missing", "RiiStudio was not found.", "Install it.")
CRATE_FOUND = EditorOption(CRATE, "BrawlCrate", "available", FOUND, "")
MINE_MISSING = EditorOption(MINE, "My editor", "missing", "My editor is gone.", "Choose it.")
LORENZI_NO_KCL = EditorOption(LORENZI, "Lorenzi's KMP Editor", "ineligible", "No kcl.", "Add it.")


def prepared(*options: EditorOption) -> PreparedEditors:
    return PreparedEditors(Path("course 日本.brres"), ".brres", options)


class MissingWork(EditorWork):
    """Held like EditorWork, but RiiStudio is missing and the custom tool is gone."""

    def prepare(self, project: Project, document: Path) -> PreparedEditors:
        self._run("prepare", project, document, None)
        return PreparedEditors(document, ".brres", (RII_MISSING, CRATE_FOUND, MINE_MISSING))


class ToolsCheck:
    """Answers like ``doctor.diagnose`` with every registered tool missing; may be held."""

    def __init__(self) -> None:
        self.calls: list[threading.Thread] = []
        self.gate = threading.Event()
        self.gate.set()
        self.fail = False  # the next checks raise, like a broken tools probe

    def __call__(self, *, force: bool, configured: Mapping[str, Path]) -> Report:
        gate = self.gate  # read once: a test may swap it while this call waits
        self.calls.append(threading.current_thread())
        assert gate.wait(10), "the tools check was never released"
        if self.fail:
            raise OSError("synthetic tools check failure")
        checks = tuple(
            ToolCheck(spec.id, spec.name, "missing", False, "editing", fix=f"Install {spec.name}.")
            for spec in TOOL_SPECS
        )
        return Report("windows", checks)


def selected_tool(page: ToolsPage) -> str | None:
    rows = page._table.selectionModel().selectedRows()
    if len(rows) != 1:
        return None
    item = page._table.item(rows[0].row(), 0)
    return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))


def tool_row(table: QTableWidget, tool_id: str) -> int:
    """The Tools table row showing ``tool_id``."""
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == tool_id:
            return row
    raise AssertionError(f"{tool_id} has no row")


@contextmanager
def project_for(folder: Path, *, read_only: bool) -> Generator[Project]:
    """A project whose course model exists (synthetic); writable, or read-only because a
    second, still-open copy holds the project's lock (always released afterwards)."""
    folder.mkdir(parents=True, exist_ok=True)
    project = writable_project(folder)
    model = project.root / GENERATED_DIR / MODEL
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"synthetic only")
    if not read_only:
        yield project
        return
    project.close()
    holder = Project.open(project.root)  # the lock owner
    try:
        viewer = Project.open(project.root)
        assert viewer.read_only and not holder.read_only
        yield viewer
    finally:
        holder.close()


@contextmanager
def tools_window(
    qtbot: QtBot, folder: Path, check: ToolsCheck, *, read_only: bool = False
) -> Generator[tuple[MainWindow, MissingWork]]:
    """The real main window on ``project_for``'s project."""
    work = MissingWork()
    other = LaunchWork()
    other.gate.set()
    controller = LaunchController(blender=other, folders=other, editors=work)
    services = AppServices(
        launch=controller,
        status=StatusService(evaluate=all_ready, find_tools=no_tools),
        build=BuildController(),
        tools=ToolsService(settings_path=folder / "settings é.json", diagnose=check),
    )
    with project_for(folder, read_only=read_only) as project:
        window = MainWindow(services)
        qtbot.addWidget(window)
        window.show()
        try:
            assert settled(qtbot, lambda: not window.welcome.busy), "the welcome check hung"
            window._opened(project)
            card = window.dashboard.cards["course_model"]
            assert settled(qtbot, card.can_open), "the course model was never checked"
            yield window, work
        finally:
            work.gate.set()
            check.gate.set()
            services.editing = False
            page = window.tools_window.page
            if page is not None:
                assert settled(qtbot, lambda: not page.busy), "the tools check never ended"
            stopped = outcome(lambda: services.shutdown(10))
            assert stopped is True, f"cleanup shutdown gave {stopped!r}"
