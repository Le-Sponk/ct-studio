"""P5-T03c: gated worker lifecycle, safety guards and source chooser."""

import threading
from pathlib import Path

import pytest
from details_helpers import DetailsWork, details
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialogButtonBox
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.views.project_details import WORKER_NAME, ProjectDetailsDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_choose_cancel_clear_only_changes_draft(qtbot: QtBot, tmp_path: Path) -> None:
    services = quiet_services()
    project = Project.create(tmp_path / "Chooser", "Chooser")
    services.adopt(project)
    chosen = tmp_path / "Selected é.blend"
    choices = [chosen, None]
    dialog = ProjectDetailsDialog(services, choose=lambda _parent, _root: choices.pop(0))
    qtbot.addWidget(dialog)
    dialog.open()
    try:
        qtbot.waitUntil(lambda: not dialog.busy)
        before = project.manifest_path.read_bytes()
        dialog.choose_button.click()
        assert dialog.source.text() == str(chosen)
        dialog.choose_button.click()
        assert dialog.source.text() == str(chosen)
        dialog.clear_button.click()
        assert dialog.source.text() == ""
        assert project.manifest_path.read_bytes() == before
    finally:
        dialog.reject()
        assert services.shutdown(10)


def assert_edit_in_progress(dialog: ProjectDetailsDialog) -> None:
    assert dialog.busy and dialog.progress.isVisible()
    assert not dialog.slot.isEnabled() and not dialog.source.isEnabled()
    assert not dialog.save_button.isEnabled()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).isEnabled()


@pytest.mark.parametrize("operation", ["load", "save"])
def test_worker_stays_responsive_and_cannot_close_mid_operation(
    qtbot: QtBot, tmp_path: Path, operation: str
) -> None:
    services = quiet_services()
    project = Project.create(tmp_path / "Gated", "Gated")
    services.adopt(project)
    work = DetailsWork()
    gate = threading.Event()
    if operation == "load":
        work.load_gate = gate
    dialog = ProjectDetailsDialog(services, service=work)
    qtbot.addWidget(dialog)
    dialog.open()
    try:
        if operation == "save":
            qtbot.waitUntil(lambda: not dialog.busy)
            work.save_gate = gate
            dialog.slot.setCurrentIndex(1)
            dialog.accept()
        qtbot.waitUntil(lambda: any(name == operation for name, _thread in work.calls))
        assert_edit_in_progress(dialog)
        ticked: list[bool] = []
        QTimer.singleShot(0, lambda: ticked.append(True))
        qtbot.waitUntil(lambda: bool(ticked))
        dialog.accept()
        dialog.reject()
        assert not dialog.close() and dialog.isVisible()
        assert services.editing and not project.read_only
        assert all(thread is not threading.main_thread() for _name, thread in work.calls)
    finally:
        gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        dialog.reject()
        assert services.shutdown(10)
    assert not any(thread.name == WORKER_NAME for thread in threading.enumerate())


@pytest.mark.parametrize("fault", [ProjectError("Synthetic read failure"), RuntimeError("Oops")])
def test_failed_load_offers_cancel_but_never_save(
    qtbot: QtBot, tmp_path: Path, fault: Exception
) -> None:
    work = DetailsWork()
    work.load_error = fault
    with details(qtbot, tmp_path, work) as (dialog, _services, project, _work):
        assert str(fault) in dialog.problem.text()
        assert not dialog.save_button.isEnabled()
        assert dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).isEnabled()
        before = project.manifest
        dialog.accept()
        assert not dialog.saved and project.manifest is before


def test_project_cannot_be_switched_or_closed_during_edit(qtbot: QtBot, tmp_path: Path) -> None:
    with details(qtbot, tmp_path) as (_dialog, services, project, _work):
        assert not services.shutdown(0)
        assert not project.read_only
        with pytest.raises(ProjectError, match="details"):
            services.close_project()
        other = Project.create(tmp_path / "Other", "Other")
        try:
            with pytest.raises(ProjectError, match="details"):
                services.adopt(other)
            assert services.project is project and not project.read_only
        finally:
            other.close()


def test_live_build_guard_disables_edit_fields(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with details(qtbot, tmp_path) as (dialog, services, _project, work):
        with monkeypatch.context() as patcher:
            patcher.setattr(type(services.build), "running", property(lambda _self: True))
            services.build.running_changed.emit(True)
            assert not dialog.save_button.isEnabled()
            dialog.accept()
            assert [name for name, _thread in work.calls] == ["load"]
        services.build.running_changed.emit(False)
        assert dialog.save_button.isEnabled()


def test_invalid_slot_and_source_show_errors_without_closing(qtbot: QtBot, tmp_path: Path) -> None:
    with details(qtbot, tmp_path) as (dialog, _services, project, _work):
        before = project.manifest_path.read_bytes()
        dialog.slot.setCurrentIndex(-1)
        dialog.accept()
        assert "Choose an original" in dialog.problem.text()
        dialog.slot.setCurrentIndex(1)
        dialog.source.setText(str(tmp_path / "missing.blend"))
        dialog.accept()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert "does not exist" in dialog.problem.text()
        assert dialog.isVisible() and not dialog.saved
        assert project.manifest_path.read_bytes() == before


def test_lost_current_project_drops_load_result(qtbot: QtBot, tmp_path: Path) -> None:
    services = quiet_services()
    project = Project.create(tmp_path / "Stale", "Stale")
    services.adopt(project)
    work = DetailsWork()
    work.load_gate = threading.Event()
    dialog = ProjectDetailsDialog(services, service=work)
    qtbot.addWidget(dialog)
    dialog.open()
    try:
        services.project = None  # simulate a stale completion, bypassing the service guard
        work.load_gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert not dialog.save_button.isEnabled()
        assert "project changed" in dialog.problem.text()
        dialog.accept()
        assert not dialog.saved
        assert [name for name, _thread in work.calls] == ["load"]
    finally:
        work.load_gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        dialog.reject()
        project.close()
        assert services.shutdown(10)


def test_worker_start_failure_is_visible_and_keeps_cancel_available(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with details(qtbot, tmp_path) as (dialog, _services, project, _work):
        before = project.manifest_path.read_bytes()

        def fail_start(_thread: threading.Thread) -> None:
            raise RuntimeError("Synthetic thread start failure")

        monkeypatch.setattr(threading.Thread, "start", fail_start)
        dialog.accept()
        assert not dialog.busy and dialog.isVisible()
        assert "Synthetic thread start failure" in dialog.problem.text()
        assert project.manifest_path.read_bytes() == before


@pytest.mark.parametrize("blocked", ["read_only", "closed", "building", "another_editor"])
def test_blocked_project_cannot_start_an_edit(
    qtbot: QtBot, tmp_path: Path, blocked: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    services = quiet_services()
    project = Project.create(tmp_path / "Blocked", "Blocked")
    services.adopt(project)
    held = None
    if blocked == "read_only":
        held = Project.open(project.root)
        services.adopt(held)
    elif blocked == "closed":
        services.close_project()
    elif blocked == "building":
        monkeypatch.setattr(type(services.build), "running", property(lambda _self: True))
    else:
        services.editing = True
    work = DetailsWork()
    dialog = ProjectDetailsDialog(services, service=work)
    qtbot.addWidget(dialog)
    dialog.open()
    try:
        assert not dialog.busy and not dialog.save_button.isEnabled()
        dialog.accept()
        assert not work.calls and not dialog.saved
        assert "cannot be edited" in dialog.problem.text()
        dialog.reject()
        assert services.editing == (blocked == "another_editor")
    finally:
        monkeypatch.undo()
        services.editing = False
        assert services.shutdown(10)
        project.close()
        if held is not None:
            held.close()
