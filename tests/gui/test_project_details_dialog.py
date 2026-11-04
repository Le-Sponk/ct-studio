"""P5-T03c: explicit Save/Cancel and background project details operations."""

from pathlib import Path

import pytest
from details_helpers import details
from PySide6.QtWidgets import QDialogButtonBox
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.views.project_details import ProjectDetailsDialog


@pytest.mark.parametrize("source", [False, True])
def test_save_updates_disk_and_publishes_snapshot_on_ui_thread(
    qtbot: QtBot, tmp_path: Path, source: bool
) -> None:
    with details(qtbot, tmp_path) as (dialog, services, project, work):
        before = project.manifest_path.read_bytes()
        blend = project.root / "Source é.blend"
        blend.write_bytes(b"synthetic source")
        dialog.slot.setCurrentIndex(1)
        chosen = dialog.slot.currentData()
        dialog.source.setText(str(blend) if source else "")
        dialog.save_button.click()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert dialog.saved and not dialog.isVisible()
        assert not services.editing
        assert project.manifest.project.slot == chosen
        assert project.manifest.project.blend == ("Source é.blend" if source else None)
        assert manifest_io.load(project.manifest_path) == project.manifest
        assert next(project.root.glob("*.bak")).read_bytes() == before
        assert [name for name, _thread in work.calls] == ["load", "save"]


def test_failed_save_keeps_dialog_and_current_project_unchanged(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with details(qtbot, tmp_path) as (dialog, services, project, work):
        work.save_error = OSError("Synthetic disk failure")
        before = project.manifest_path.read_bytes()
        current = project.manifest
        dialog.slot.setCurrentIndex(1)
        dialog.accept()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert "Synthetic disk failure" in dialog.problem.text()
        assert dialog.isVisible() and not dialog.saved
        assert services.editing and dialog.save_button.isEnabled()
        assert project.manifest is current and project.manifest_path.read_bytes() == before
        work.save_error = None
        dialog.accept()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert dialog.saved


pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_details_load_current_values_and_cancel_changes_nothing(
    qtbot: QtBot, tmp_path: Path
) -> None:
    services = quiet_services()
    project = Project.create(tmp_path / "Détails 日本", "Détails 日本")
    services.adopt(project)
    before = project.manifest_path.read_bytes()
    try:
        dialog = ProjectDetailsDialog(services)
        qtbot.addWidget(dialog)
        dialog.open()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert dialog.slot.currentData() == project.manifest.project.slot
        assert dialog.source.text() == ""
        assert dialog.save_button.isEnabled()
        dialog.slot.setCurrentIndex(1)
        dialog.source.setText(str(tmp_path / "not saved.blend"))
        dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        assert not dialog.isVisible()
        assert not dialog.saved and not services.editing
        assert project.manifest_path.read_bytes() == before
        assert not tuple(project.root.glob("*.bak"))
    finally:
        assert services.shutdown(10)
