"""Failed and foreign completions must never publish component-mode drafts."""

import threading
from dataclasses import replace
from pathlib import Path

import pytest
from mode_helpers import ModeWork, assert_unchanged, modes
from PySide6.QtWidgets import QDialogButtonBox
from pytestqt.qtbot import QtBot

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.project_details import DetailsSnapshot

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


class WrongProjectWork(ModeWork):
    def __init__(self, operation: str, root: Path) -> None:
        super().__init__()
        self.operation = operation
        self.root = root

    def load(self, project: Project) -> DetailsSnapshot:
        result = super().load(project)
        return replace(result, root=self.root) if self.operation == "load" else result

    def save(
        self, project: Project, snapshot: DetailsSnapshot, component_id: str, mode: str
    ) -> DetailsSnapshot:
        result = super().save(project, snapshot, component_id, mode)
        return replace(result, root=self.root)


@pytest.mark.parametrize("operation", ["load", "save"])
def test_snapshot_for_another_root_is_not_adopted(
    qtbot: QtBot, tmp_path: Path, operation: str
) -> None:
    work = WrongProjectWork(operation, tmp_path / "Other root")
    with modes(qtbot, tmp_path, work) as (dialog, services, project, _work):
        current = project.manifest
        if operation == "save":
            dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
            dialog.save_button.click()
            qtbot.waitUntil(lambda: not dialog.busy)
        assert not dialog.saved and project.manifest is current and services.editing
        assert "project changed" in dialog.problem.text()
        assert dialog.isVisible()
        if operation == "load":
            assert not dialog.save_button.isEnabled()


@pytest.mark.parametrize("operation", ["load", "save"])
@pytest.mark.parametrize("fault", [ProjectError("Synthetic access denied"), RuntimeError("Oops")])
def test_failed_operations_keep_live_state_and_offer_explicit_cancel(
    qtbot: QtBot, tmp_path: Path, operation: str, fault: Exception
) -> None:
    work = ModeWork()
    if operation == "load":
        work.load_error = fault
    with modes(qtbot, tmp_path, work) as (dialog, services, project, work):
        current = project.manifest
        before = project.manifest_path.read_bytes()
        if operation == "save":
            work.save_error = fault
            dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
            dialog.save_button.click()
            qtbot.waitUntil(lambda: not dialog.busy)
        assert f"Could not {operation} component mode. {fault}" in dialog.problem.text()
        assert (dialog.isVisible(), dialog.saved, services.editing) == (True, False, True)
        assert dialog.save_button.isEnabled() == (operation == "save")
        assert_unchanged(project, current, before)
        if operation == "save":
            work.save_error = None
            dialog.save_button.click()
            qtbot.waitUntil(lambda: not dialog.busy)
            assert dialog.saved
        else:
            dialog.accept()
            assert [name for name, _thread in work.calls] == ["load"]
            dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
            assert not services.editing


def test_load_thread_start_failure_releases_ownership_on_cancel(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_start(_thread: threading.Thread) -> None:
        raise RuntimeError("Synthetic thread start failure")

    with monkeypatch.context() as patcher:
        patcher.setattr(threading.Thread, "start", fail_start)
        with modes(qtbot, tmp_path) as (dialog, services, _project, work):
            assert not dialog.busy and not dialog.save_button.isEnabled()
            assert "Could not load component mode" in dialog.problem.text()
            assert "Synthetic thread start failure" in dialog.problem.text()
            assert not work.calls
            dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
            assert not services.editing


def test_save_thread_start_failure_keeps_draft_and_can_retry(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with modes(qtbot, tmp_path) as (dialog, _services, project, work):
        before = project.manifest_path.read_bytes()
        dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))

        def fail_start(_thread: threading.Thread) -> None:
            raise RuntimeError("Synthetic thread start failure")

        with monkeypatch.context() as patcher:
            patcher.setattr(threading.Thread, "start", fail_start)
            dialog.save_button.click()
        assert not dialog.busy and dialog.isVisible() and not dialog.saved
        assert "Could not save component mode" in dialog.problem.text()
        assert "Synthetic thread start failure" in dialog.problem.text()
        assert dialog.mode.currentData() == "manual"
        assert project.manifest_path.read_bytes() == before and not work.save_args
        dialog.save_button.click()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert dialog.saved


@pytest.mark.parametrize("operation", ["load", "save"])
def test_lost_current_project_discards_queued_result(
    qtbot: QtBot, tmp_path: Path, operation: str
) -> None:
    work = ModeWork()
    gate = threading.Event()
    if operation == "load":
        work.load_gate = gate
    with modes(qtbot, tmp_path, work, wait_loaded=False) as (dialog, services, project, work):
        current = project.manifest
        if operation == "save":
            qtbot.waitUntil(lambda: not dialog.busy)
            work.save_gate = gate
            dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
            dialog.accept()
        qtbot.waitUntil(lambda: any(name == operation for name, _thread in work.calls))
        services.project = None  # deliberately bypass guarded service calls
        gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert "project changed" in dialog.problem.text()
        assert not dialog.saved and project.manifest is current
        assert not dialog.mode.isEnabled() and not dialog.save_button.isEnabled()
        assert services.editing and not project.read_only
        dialog.accept()
        assert [name for name, _thread in work.calls].count(operation) == 1
        dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        assert not services.editing


@pytest.mark.parametrize("conflict", ["disk", "live", "closed"])
def test_changed_project_during_save_is_not_published_or_overwritten(
    qtbot: QtBot, tmp_path: Path, conflict: str
) -> None:
    with modes(qtbot, tmp_path) as (dialog, _services, project, work):
        work.save_gate = threading.Event()
        dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
        dialog.save_button.click()
        qtbot.waitUntil(lambda: bool(work.save_args))
        if conflict == "disk":
            project.manifest_path.write_bytes(
                project.manifest_path.read_bytes() + b"\n# external edit"
            )
        elif conflict == "live":
            project.manifest = replace(
                project.manifest, project=replace(project.manifest.project, name="External change")
            )
        else:
            project.close()
        before = project.manifest_path.read_bytes()
        current = project.manifest
        work.save_gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert "Could not save component mode" in dialog.problem.text()
        assert not dialog.saved and project.manifest is current
        assert project.manifest_path.read_bytes() == before
        assert manifest_io.load(project.manifest_path).components.course_model.mode == "auto"
        assert not tuple(project.root.glob("*.bak"))
