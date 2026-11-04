"""Explicit component-mode drafts on the shared joined-worker editor lifecycle."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.component_modes import ComponentModeService
from ctstudio.gui.project_details import DetailsSnapshot
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.project_details import ProjectDetailsDialog

WORKER_NAME = "ctstudio-component-mode"
_EXPLANATIONS = {
    "auto": "Build this part from the project's source and settings.",
    "manual": "Use a file or folder you supply instead of generating this part.",
    "template": "Use this part from a selected original track template.",
}


class ComponentModeDialog(ProjectDetailsDialog):
    SUBJECT = "component mode"
    worker_name = WORKER_NAME

    def __init__(
        self,
        services: AppServices,
        component_id: str,
        *,
        initial_mode: str | None = None,
        service: ComponentModeService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        spec = COMPONENT_BY_ID.get(component_id)
        if spec is None or spec.manifest_table in (None, "project") or len(spec.modes) < 2:
            raise ProjectError(
                "This component has no alternative modes to edit.",
                hint="Choose a component with more than one supported mode.",
            )
        if initial_mode is not None and initial_mode not in spec.modes:
            raise ProjectError(
                f"The mode {initial_mode!r} is not supported for {spec.name}.",
                hint=f"Choose one of: {', '.join(spec.modes)}.",
            )
        self.component_id = component_id
        self.spec = spec
        self._initial_mode = initial_mode
        self._mode_service = service if service is not None else ComponentModeService()
        super().__init__(services, parent=parent)
        self.setObjectName("componentModeDialog")
        self.setWindowTitle(f"{self.spec.name} mode")

    def _make_fields(self) -> None:
        layout = QVBoxLayout(self)
        note = QLabel(self.spec.description, self)
        note.setObjectName("componentModeDescription")
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.mode = QComboBox(self)
        self.mode.setObjectName("componentMode")
        self.mode.setToolTip("Choose how this part is made; changes apply only when you save.")
        for mode in self.spec.modes:
            self.mode.addItem(mode, mode)
        form.addRow("&Mode", self.mode)
        layout.addLayout(form)
        explanation = QLabel(
            "\n".join(f"{mode}: {_EXPLANATIONS[mode]}" for mode in self.spec.modes)
            + "\nSwitching modes keeps existing files and inactive settings. "
            "Switching to manual does not choose a file; assign one separately.",
            self,
        )
        explanation.setObjectName("componentModeExplanation")
        explanation.setTextFormat(Qt.TextFormat.PlainText)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self._make_footer(layout)

    def _load(self, project: Project) -> DetailsSnapshot:
        return self._mode_service.load(project)

    def _fill(self, snapshot: DetailsSnapshot) -> None:
        part = getattr(snapshot.manifest.components, self.spec.manifest_table or "")
        mode = self._initial_mode if self._initial_mode is not None else part.mode
        self.mode.setCurrentIndex(self.mode.findData(mode))

    def _editing_controls(self, editable: bool) -> None:
        self.mode.setEnabled(editable)

    def accept(self) -> None:
        project, snapshot = self.project, self._snapshot
        if self._busy or not self._allowed() or project is None or snapshot is None:
            return
        mode = self.mode.currentData()
        if not isinstance(mode, str) or mode not in self.spec.modes:
            self.problem.setText("Choose a supported mode from the list before saving.")
            return
        self._start(
            lambda: self._mode_service.save(project, snapshot, self.component_id, mode),
            saving=True,
        )
