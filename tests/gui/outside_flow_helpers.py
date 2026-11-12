"""Synthetic ready KCL and real watcher/worker ownership for mounted-button flows."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from assign_helpers import kcl_bytes, write
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea
from pytestqt.qtbot import QtBot
from reconcile_helpers import EditWork, settled

from ctstudio.core.components.state import ProjectState, record, save_state
from ctstudio.core.components.status import settings_key
from ctstudio.core.project.project import Project
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.gui.launch_controller import LaunchController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.dashboard import Dashboard


def all_tools(**_kwargs: object) -> frozenset[str]:
    return frozenset(TOOL_BY_ID)


@contextmanager
def live_dashboard(
    qtbot: QtBot, folder: Path
) -> Generator[tuple[Dashboard, Project, EditWork, QScrollArea], None, None]:
    project = Project.create(folder / "Pistë 日本", "T")
    stage = write(project.root / ".ctstudio/stage/course.kcl", kcl_bytes())
    entry = record(project.root, settings_key(project.manifest, "kcl"), [stage], [])
    save_state(project.root, ProjectState({"kcl": entry}))
    work = EditWork()
    work.gate.set()
    services = AppServices(
        launch=LaunchController(lock=work.lock, discard=work.discard),
        status=StatusService(find_tools=all_tools),
    )
    try:
        services.adopt(project)
        page = Dashboard(services)
        area = QScrollArea()
        qtbot.addWidget(area)
        area.setWidgetResizable(True)
        area.setWidget(page)
        area.resize(900, 600)
        page.set_project(project)
        area.show()
        area.activateWindow()
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        assert services.watcher.watching == project.root
        yield page, project, work, area
    finally:
        work.gate.set()
        services.editing = False
        assert services.shutdown(10), "the live outside-edit flow retained ownership"
        project.close()


def answer_discard(action: str, seen: list[bool]) -> None:
    dialog = QApplication.activeModalWidget()
    if isinstance(dialog, QMessageBox):
        seen.append(True)
        role = (
            QMessageBox.ButtonRole.DestructiveRole
            if action == "discard"
            else QMessageBox.ButtonRole.RejectRole
        )
        chosen = next(button for button in dialog.buttons() if dialog.buttonRole(button) == role)
        chosen.click()


def change_stage(project: Project) -> bytes:
    path = project.root / ".ctstudio/stage/course.kcl"
    changed = kcl_bytes(0x480)
    path.write_bytes(changed)
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
    return changed
