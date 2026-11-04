"""Synthetic, event-gated component-mode work for dialog and window tests."""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtWidgets import QDialogButtonBox
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.gui.component_modes import ComponentModeService
from ctstudio.gui.project_details import DetailsSnapshot
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.component_mode import ComponentModeDialog


class ModeWork(ComponentModeService):
    def __init__(self) -> None:
        self.load_gate: threading.Event | None = None
        self.save_gate: threading.Event | None = None
        self.load_error: Exception | None = None
        self.save_error: Exception | None = None
        self.calls: list[tuple[str, threading.Thread]] = []
        self.save_args: list[tuple[Project, DetailsSnapshot, str, str]] = []

    def load(self, project: Project) -> DetailsSnapshot:
        self.calls.append(("load", threading.current_thread()))
        gate = self.load_gate
        if gate is not None:
            assert gate.wait(10)
        if self.load_error is not None:
            raise self.load_error
        return super().load(project)

    def save(
        self, project: Project, snapshot: DetailsSnapshot, component_id: str, mode: str
    ) -> DetailsSnapshot:
        self.calls.append(("save", threading.current_thread()))
        self.save_args.append((project, snapshot, component_id, mode))
        gate = self.save_gate
        if gate is not None:
            assert gate.wait(10)
        if self.save_error is not None:
            raise self.save_error
        return super().save(project, snapshot, component_id, mode)


def assert_unchanged(project: Project, manifest: Manifest, raw: bytes) -> None:
    assert project.manifest is manifest
    assert project.manifest_path.read_bytes() == raw
    assert not tuple(project.root.glob("*.bak"))


def assert_busy(dialog: ComponentModeDialog) -> None:
    assert dialog.busy and dialog.progress.isVisible()
    assert not dialog.mode.isEnabled() and not dialog.save_button.isEnabled()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).isEnabled()


@contextmanager
def modes(
    qtbot: QtBot,
    folder: Path,
    work: ModeWork | None = None,
    *,
    component_id: str = "course_model",
    initial_mode: str | None = None,
    wait_loaded: bool = True,
) -> Generator[tuple[ComponentModeDialog, AppServices, Project, ModeWork]]:
    services = quiet_services()
    project = Project.create(folder / "Mode café 日本", "Mode draft")
    services.adopt(project)
    work = work if work is not None else ModeWork()
    dialog = ComponentModeDialog(services, component_id, initial_mode=initial_mode, service=work)
    qtbot.addWidget(dialog)
    dialog.open()
    try:
        if wait_loaded:
            qtbot.waitUntil(lambda: not dialog.busy)
        yield dialog, services, project, work
    finally:
        for gate in (work.load_gate, work.save_gate):
            if gate is not None:
                gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        dialog.reject()
        services.project = project
        assert services.shutdown(10)
