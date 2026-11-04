"""P5-T03c: dashboard entry, project ownership and save/close integration."""

import threading
from pathlib import Path

import pytest
from details_helpers import DetailsWork
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.views.project_details import ProjectDetailsDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def window_with_details(qtbot: QtBot, folder: Path, work: DetailsWork) -> MainWindow:
    window = MainWindow(
        quiet_services(),
        edit_project=lambda services, parent: ProjectDetailsDialog(
            services, service=work, parent=parent
        ),
    )
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    window._opened(Project.create(folder / "Editable é", "Editable é"))
    qtbot.waitUntil(lambda: not window.dashboard.busy)
    return window


def assert_navigation_disabled(window: MainWindow) -> None:
    assert not window.new_project_action.isEnabled()
    assert not window.open_project_action.isEnabled()
    assert not window.home_action.isEnabled()
    assert not window.dashboard_action.isEnabled()
    assert not window.dashboard.edit_button.isEnabled()


def test_dashboard_details_save_refreshes_header_and_statuses(qtbot: QtBot, tmp_path: Path) -> None:
    work = DetailsWork()
    window = window_with_details(qtbot, tmp_path, work)
    try:
        window.dashboard.edit_button.click()
        dialog = window.findChild(ProjectDetailsDialog, "projectDetailsDialog")
        assert dialog is not None and dialog.isVisible()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert_navigation_disabled(window)
        dialog.slot.setCurrentIndex(1)
        slot = dialog.slot.currentData()
        source = tmp_path / "New source é.blend"
        source.write_bytes(b"synthetic source")
        dialog.source.setText(str(source))
        dialog.accept()
        qtbot.waitUntil(lambda: not window.services.editing)
        assert window.dashboard.slot_label.text() == f"{slot}.szs"
        assert window.dashboard.source_label.text() == str(source)
        qtbot.waitUntil(lambda: not window.dashboard.busy)
        assert window.dashboard.edit_button.isEnabled()
        assert window.new_project_action.isEnabled()
    finally:
        window.close()


def test_main_close_refuses_until_edit_worker_finishes(qtbot: QtBot, tmp_path: Path) -> None:
    work = DetailsWork()
    work.load_gate = threading.Event()
    window = window_with_details(qtbot, tmp_path, work)
    window.dashboard.edit_button.click()
    dialog = window.findChild(ProjectDetailsDialog, "projectDetailsDialog")
    assert dialog is not None
    try:
        qtbot.waitUntil(lambda: bool(work.calls))
        assert not window.close()
        assert window.services.project is not None and not window.services.project.read_only
        assert dialog.isVisible() and "Wait" in dialog.problem.text()
        window._edit_project()  # direct invocation cannot create a second editor
        assert len(window.findChildren(ProjectDetailsDialog)) == 1
    finally:
        work.load_gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert window.close()
    assert not window.services.editing and window.services.project is None


def test_details_cancel_restores_navigation_without_rebinding_cards(
    qtbot: QtBot, tmp_path: Path
) -> None:
    from test_dashboard_states import ready

    window = window_with_details(qtbot, tmp_path, DetailsWork())
    project = window.services.project
    assert project is not None
    window.services.status.updated.emit(ready(project.root))
    try:
        window.dashboard.edit_button.click()
        dialog = window.findChild(ProjectDetailsDialog, "projectDetailsDialog")
        assert dialog is not None
        qtbot.waitUntil(lambda: not dialog.busy)
        dialog.reject()
        assert window.dashboard.cards["kcl"].status_label.text() == "ready"
        assert not window.services.editing
        assert window.open_project_action.isEnabled()
    finally:
        window.close()
