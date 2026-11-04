"""Joined component-mode workers retain modal edit and project-lock ownership."""

import threading
from pathlib import Path

import pytest
from mode_helpers import ModeWork, assert_busy, modes
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.component_mode import WORKER_NAME, ComponentModeDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def assert_editor_owns_project(services: AppServices, project: Project, folder: Path) -> None:
    assert not services.shutdown(0) and not project.read_only
    for action in (services.close_project, lambda: services.open_project(project.root)):
        with pytest.raises(ProjectError, match="details"):
            action()
    other = Project.create(folder / "Other", "Other")
    with pytest.raises(ProjectError, match="details"):
        services.adopt(other)
    assert other.read_only and services.project is project


@pytest.mark.parametrize("operation", ["load", "save"])
def test_busy_worker_is_responsive_and_refuses_buttons_keys_close_and_lock_release(
    qtbot: QtBot, tmp_path: Path, operation: str
) -> None:
    work = ModeWork()
    gate = threading.Event()
    if operation == "load":
        work.load_gate = gate
    with modes(qtbot, tmp_path, work, wait_loaded=False) as (dialog, services, project, work):
        if operation == "save":
            qtbot.waitUntil(lambda: not dialog.busy)
            work.save_gate = gate
            dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
            dialog.save_button.click()
        qtbot.waitUntil(lambda: any(name == operation for name, _thread in work.calls))
        assert_busy(dialog)
        cancel = dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        ticked: list[bool] = []
        QTimer.singleShot(0, lambda: ticked.append(True))
        qtbot.waitUntil(lambda: bool(ticked))
        dialog.save_button.click()
        cancel.click()
        QTest.keyClick(dialog, Qt.Key.Key_Return)
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        dialog.accept()
        dialog.reject()
        assert not dialog.close() and dialog.isVisible()
        assert services.editing and not dialog.saved
        assert_editor_owns_project(services, project, tmp_path)
        assert all(
            t is not threading.main_thread() and t.name == WORKER_NAME for _, t in work.calls
        )
    assert not any(t.name == WORKER_NAME for t in threading.enumerate())


def test_save_publishes_on_ui_thread_strictly_after_join(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with modes(qtbot, tmp_path) as (dialog, _services, project, work):
        events: list[tuple[str, threading.Thread]] = []
        original_join = threading.Thread.join
        original_setattr = Project.__setattr__

        def joined(worker: threading.Thread, timeout: float | None = None) -> None:
            original_join(worker, timeout)
            if worker.name == WORKER_NAME:
                assert not worker.is_alive()
                events.append(("joined", threading.current_thread()))

        def published(target: Project, name: str, value: object) -> None:
            if target is project and name == "manifest":
                events.append(("published", threading.current_thread()))
            original_setattr(target, name, value)

        monkeypatch.setattr(threading.Thread, "join", joined)
        monkeypatch.setattr(Project, "__setattr__", published)
        dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
        dialog.save_button.click()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert [event for event, _thread in events] == ["joined", "published"]
        assert all(thread is threading.main_thread() for _event, thread in events)
        saved_project, snapshot, component_id, selected = work.save_args[0]
        assert saved_project is project and snapshot.manifest.components.course_model.mode == "auto"
        assert component_id == "course_model" and selected == "manual"
        assert dialog.saved


@pytest.mark.parametrize("blocked", ["read_only", "closed", "building", "another_editor"])
def test_unavailable_project_never_starts_or_steals_edit_ownership(
    qtbot: QtBot, tmp_path: Path, blocked: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    services = quiet_services()
    project = Project.create(tmp_path / "Blocked", "Blocked")
    services.adopt(project)
    if blocked == "read_only":
        services.adopt(Project.open(project.root))
    elif blocked == "closed":
        services.close_project()
    elif blocked == "building":
        monkeypatch.setattr(type(services.build), "running", property(lambda _self: True))
    else:
        services.editing = True
    work = ModeWork()
    dialog = ComponentModeDialog(services, "course_model", service=work)
    qtbot.addWidget(dialog)
    dialog.open()
    try:
        assert (
            not dialog.busy and not dialog.mode.isEnabled() and not dialog.save_button.isEnabled()
        )
        assert "Component mode cannot be edited" in dialog.problem.text()
        dialog.accept()
        assert not work.calls and not dialog.saved
        dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        assert services.editing == (blocked == "another_editor")
    finally:
        monkeypatch.undo()
        services.editing = False
        assert services.shutdown(10)
        project.close()


def test_running_build_disables_mode_draft_until_finished(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with modes(qtbot, tmp_path) as (dialog, services, _project, work):
        with monkeypatch.context() as patcher:
            patcher.setattr(type(services.build), "running", property(lambda _self: True))
            services.build.running_changed.emit(True)
            assert not dialog.mode.isEnabled() and not dialog.save_button.isEnabled()
            dialog.accept()
            assert [name for name, _thread in work.calls] == ["load"]
        services.build.running_changed.emit(False)
        assert dialog.mode.isEnabled() and dialog.save_button.isEnabled()
