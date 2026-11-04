"""P5-T03f: real mode service save/error and modal worker ownership through cards."""

import threading
from pathlib import Path

import pytest
from component_window_helpers import window_with_mode_service
from mode_helpers import ModeWork
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialogButtonBox
from pytestqt.qtbot import QtBot
from test_dashboard_states import ready

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.views.component_card import ComponentCard
from ctstudio.gui.views.component_mode import ComponentModeDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def assert_saved_part(project: Project, card: ComponentCard, component: str, before: bytes) -> None:
    assert getattr(project.manifest.components, component).mode == "manual"
    assert manifest_io.load(project.manifest_path) == project.manifest
    assert card.mode_label.text() == "Mode: manual"
    assert card.path is None
    assert not card.copy_button.isEnabled()
    backups = list(project.root.glob("*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before


def assert_workers_finished(work: ModeWork) -> None:
    assert [op for op, _thread in work.calls] == ["load", "save"]
    assert all(
        thread is not threading.main_thread() and not thread.is_alive()
        for _op, thread in work.calls
    )


def assert_failed_dialog(dialog: ComponentModeDialog) -> None:
    assert dialog.isVisible()
    assert not dialog.saved
    assert "Could not save" in dialog.problem.text()


def assert_kept_card(card: ComponentCard, mode: str, path: Path | None) -> None:
    assert card.mode_label.text() == mode
    assert card.path == path
    assert card.status_label.text() == "ready"


def assert_busy_window(window: MainWindow, project: Project) -> None:
    assert not window.close()
    assert project.lock is not None
    assert window.services.editing
    assert not window.open_project_action.isEnabled()
    assert not window.dashboard.refresh_button.isEnabled()
    window.dashboard.refresh()
    assert not window.dashboard.busy
    with pytest.raises(ProjectError, match="details"):
        window.services.close_project()
    assert not window.services.shutdown(0)
    window._edit_component("skybox", "template")
    window._edit_project()
    assert len(window.findChildren(ComponentModeDialog)) == 1


@pytest.mark.parametrize("component", ["course_model", "kcl", "minimap", "skybox", "posteffect"])
@pytest.mark.parametrize("menu", [False, True])
def test_card_save_updates_manifest_mode_paths_and_refreshes_status(
    qtbot: QtBot, tmp_path: Path, component: str, menu: bool
) -> None:
    work = ModeWork()
    window = window_with_mode_service(qtbot, tmp_path, work)
    project = window.services.project
    assert project is not None
    before = project.manifest_path.read_bytes()
    updates: list[object] = []
    window.services.status.updated.connect(updates.append)
    card = window.dashboard.cards[component]
    try:
        if menu:
            card.mode_actions["manual"].trigger()
        else:
            card.mode_button.click()
        dialog = window.findChild(ComponentModeDialog, "componentModeDialog")
        assert dialog is not None and dialog.isVisible()
        qtbot.waitUntil(lambda: not dialog.busy)
        if menu:
            assert dialog.mode.currentData() == "manual"
        dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
        dialog.save_button.click()
        qtbot.waitUntil(lambda: not window.services.editing and not window.dashboard.busy)
        assert_saved_part(project, card, component, before)
        assert updates
        assert window.open_project_action.isEnabled() and card.mode_button.isEnabled()
        assert_workers_finished(work)
    finally:
        window.close()


@pytest.mark.parametrize("failure", ["service", "external"])
def test_failed_mode_save_retains_last_good_card_and_project(
    qtbot: QtBot, tmp_path: Path, failure: str
) -> None:
    work = ModeWork()
    window = window_with_mode_service(qtbot, tmp_path, work)
    project = window.services.project
    assert project is not None
    original = project.manifest
    before = project.manifest_path.read_bytes()
    window.services.status.updated.emit(ready(project.root))
    card = window.dashboard.cards["kcl"]
    old_mode, old_path = card.mode_label.text(), card.path
    try:
        card.mode_actions["manual"].trigger()
        dialog = window.findChild(ComponentModeDialog, "componentModeDialog")
        assert dialog is not None
        qtbot.waitUntil(lambda: not dialog.busy)
        if failure == "service":
            work.save_error = ProjectError("Synthetic write refused.", hint="Try again.")
        else:
            project.manifest_path.write_bytes(before + b"\n# external edit\n")
        retained = project.manifest_path.read_bytes()
        dialog.save_button.click()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert_failed_dialog(dialog)
        assert project.manifest is original
        assert_kept_card(card, old_mode, old_path)
        assert project.manifest_path.read_bytes() == retained
        dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        assert not window.services.editing
        assert card.mode_actions["auto"].isChecked()
        assert not card.mode_actions["manual"].isChecked()
    finally:
        window.close()


@pytest.mark.parametrize("phase", ["load", "save"])
def test_busy_mode_editor_refuses_close_switch_and_refresh(
    qtbot: QtBot, tmp_path: Path, phase: str
) -> None:
    work = ModeWork()
    gate = threading.Event()
    setattr(work, f"{phase}_gate", gate)
    window = window_with_mode_service(qtbot, tmp_path, work)
    project = window.services.project
    assert project is not None
    dialog: ComponentModeDialog | None = None
    try:
        window.dashboard.cards["kcl"].mode_button.click()
        dialog = window.findChild(ComponentModeDialog, "componentModeDialog")
        assert dialog is not None
        if phase == "save":
            qtbot.waitUntil(lambda: not dialog.busy)
            dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
            dialog.accept()
        qtbot.waitUntil(lambda: any(op == phase for op, _thread in work.calls))
        ticks: list[bool] = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        qtbot.waitUntil(lambda: bool(ticks))
        assert_busy_window(window, project)
    finally:
        gate.set()
        if dialog is not None:
            active = dialog
            qtbot.waitUntil(lambda: not active.busy)
        assert window.close()
    assert window.services.project is None and not window.services.editing
