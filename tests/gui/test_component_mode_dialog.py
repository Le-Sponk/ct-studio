"""Explicit mode drafts and joined, registry-driven component edits."""

from pathlib import Path

import pytest
from mode_helpers import assert_unchanged, modes
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox, QLabel
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.components.registry import COMPONENTS, ComponentSpec
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.views.component_mode import ComponentModeDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_manual_mode_is_only_persisted_by_explicit_save(qtbot: QtBot, tmp_path: Path) -> None:
    services = quiet_services()
    project = Project.create(tmp_path / "Mode café 日本", "Mode draft")
    services.adopt(project)
    dialog = ComponentModeDialog(services, "course_model")
    qtbot.addWidget(dialog)
    dialog.open()
    try:
        qtbot.waitUntil(lambda: not dialog.busy)
        before = project.manifest_path.read_bytes()
        assert dialog.objectName() == "componentModeDialog"
        assert (dialog.mode.currentData(), dialog.mode.currentText()) == ("auto", "auto")
        dialog.mode.setCurrentIndex(dialog.mode.findData("manual"))
        assert project.manifest_path.read_bytes() == before
        assert project.manifest.components.course_model.mode == "auto"
        dialog.save_button.click()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert (dialog.saved, dialog.isVisible(), services.editing) == (True, False, False)
        assert project.manifest.components.course_model.mode == "manual"
        assert manifest_io.load(project.manifest_path) == project.manifest
        assert next(project.root.glob("*.bak")).read_bytes() == before
    finally:
        qtbot.waitUntil(lambda: not dialog.busy)
        dialog.reject()
        assert services.shutdown(10)


@pytest.mark.parametrize("component_id", ["missing", "objects", "track_info", "kmp"])
@pytest.mark.parametrize("already_editing", [False, True])
def test_ineligible_component_is_rejected_before_taking_edit_ownership(
    qtbot: QtBot, tmp_path: Path, component_id: str, already_editing: bool
) -> None:
    services = quiet_services()
    services.editing = already_editing
    project = Project.create(tmp_path / "Invalid entry", "Invalid entry")
    services.project = project
    try:
        with pytest.raises(ProjectError) as caught:
            ComponentModeDialog(services, component_id)
        assert caught.value.hint
        assert services.editing is already_editing
        assert not project.read_only
    finally:
        services.editing = False
        assert services.shutdown(10)


@pytest.mark.parametrize(
    "spec",
    [s for s in COMPONENTS if s.manifest_table not in (None, "project") and len(s.modes) > 1],
)
@pytest.mark.parametrize("initial_mode", ["", "AUTO", "missing", "manual/../"])
def test_invalid_initial_mode_is_rejected_before_edit_ownership(
    qtbot: QtBot, spec: ComponentSpec, initial_mode: str
) -> None:
    services = quiet_services()
    try:
        with pytest.raises(ProjectError) as caught:
            ComponentModeDialog(services, spec.id, initial_mode=initial_mode)
        assert caught.value.hint
        assert not services.editing
    finally:
        assert services.shutdown(10)


@pytest.mark.parametrize(
    ("spec", "initial"),
    [
        (s, m)
        for s in COMPONENTS
        if s.manifest_table not in (None, "project") and len(s.modes) > 1
        for m in s.modes
    ],
)
def test_supported_modes_have_plain_explanations_and_cancel_only_drafts(
    qtbot: QtBot, tmp_path: Path, spec: ComponentSpec, initial: str
) -> None:
    with modes(qtbot, tmp_path, component_id=spec.id, initial_mode=initial) as (
        dialog,
        services,
        project,
        work,
    ):
        before = project.manifest_path.read_bytes()
        current = project.manifest
        assert [
            (dialog.mode.itemText(i), dialog.mode.itemData(i)) for i in range(dialog.mode.count())
        ] == [(m, m) for m in spec.modes]
        assert dialog.mode.currentData() == initial
        explanation = dialog.findChild(QLabel, "componentModeExplanation")
        assert explanation is not None
        assert explanation.textFormat() == Qt.TextFormat.PlainText
        assert all(f"{m}:" in explanation.text() for m in spec.modes)
        assert "does not choose a file" in explanation.text()
        assert "keeps" in explanation.text()
        dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        assert (services.editing, dialog.saved, dialog.isVisible()) == (False, False, False)
        assert_unchanged(project, current, before)
        assert [name for name, _thread in work.calls] == ["load"]


@pytest.mark.parametrize("value", [None, "unsupported", "AUTO"])
def test_invalid_selected_mode_does_not_start_a_save(
    qtbot: QtBot, tmp_path: Path, value: str | None
) -> None:
    with modes(qtbot, tmp_path) as (dialog, services, project, work):
        before = project.manifest_path.read_bytes()
        dialog.mode.addItem("Invalid injected entry", value)
        dialog.mode.setCurrentIndex(dialog.mode.count() - 1)
        dialog.accept()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert [name for name, _thread in work.calls] == ["load"]
        assert "Choose a supported mode" in dialog.problem.text()
        assert services.editing and not dialog.saved
        assert project.manifest_path.read_bytes() == before
