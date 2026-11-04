"""The live, read-only project overview (P5-T03b); disk work belongs to StatusService."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.project.project import Project
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusResult
from ctstudio.gui.views.component_card import ComponentCard


def _label(name: str, parent: QWidget) -> QLabel:
    label = QLabel(parent)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class Dashboard(QWidget):
    edit_requested = Signal()
    mode_requested = Signal(str, str)

    def __init__(self, services: AppServices, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self._project: Project | None = None
        self._checking = False
        self.setObjectName("dashboard")
        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.name_label = _label("dashboardName", self)
        font = self.name_label.font()
        font.setPointSize(18)
        font.setBold(True)
        self.name_label.setFont(font)
        self._layout.addWidget(self.name_label)
        form = QFormLayout()
        self.folder_label = _label("dashboardFolder", self)
        self.slot_label = _label("dashboardSlot", self)
        self.source_label = _label("dashboardSource", self)
        form.addRow("Project folder", self.folder_label)
        form.addRow("Replaces", self.slot_label)
        form.addRow("Blender source", self.source_label)
        self._layout.addLayout(form)
        self._make_cards()
        self.services.status.updated.connect(self._updated)
        self.services.status.failed.connect(self._failed)
        self.services.build.running_changed.connect(self._sync)
        self.services.build.finished.connect(self._after_build)
        self.services.build.failed.connect(self._after_build)

    def set_project(self, project: Project, *, changed: bool = False) -> None:
        if project is self._project and not changed:
            self.refresh()  # retain last good results, including during an existing check/build
            return
        self._project = project
        self._checking = False
        info = project.manifest.project
        self.name_label.setText(info.name)
        self.folder_label.setText(str(project.root))
        self.slot_label.setText(f"{info.slot}.szs")
        source = project.root / info.blend if info.blend else None
        self.source_label.setText(str(source) if source else "No Blender file chosen")
        access = (
            f"Read-only — {project.read_only_reason}. You can inspect and copy paths."
            if project.read_only
            else "Writable project"
        )
        self.access_label.setText(access)
        self._sync()
        for card in self.cards.values():
            card.bind(project)
        self.refresh()

    def _make_cards(self) -> None:
        self.access_label = _label("dashboardAccess", self)
        self._layout.addWidget(self.access_label)
        self.work_label = _label("dashboardWork", self)
        self._layout.addWidget(self.work_label)
        self.notice = _label("dashboardNotice", self)
        self._layout.addWidget(self.notice)
        self.checking = QProgressBar(self)
        self.checking.setObjectName("dashboardChecking")
        self.checking.setRange(0, 0)
        self.checking.hide()
        self._layout.addWidget(self.checking)
        self.refresh_button = QPushButton("Refresh statuses", self)
        self.refresh_button.setObjectName("refreshStatuses")
        self.refresh_button.setEnabled(False)
        self.refresh_button.clicked.connect(self.refresh)
        controls = QHBoxLayout()
        controls.addWidget(self.refresh_button)
        self.copy_project = QPushButton("Copy project folder", self)
        self.copy_project.setObjectName("copyProjectFolder")
        self.copy_project.setEnabled(False)
        self.copy_project.clicked.connect(self._copy_project)
        controls.addWidget(self.copy_project)
        self.edit_button = QPushButton("Project details…", self)
        self.edit_button.setObjectName("editProjectDetails")
        self.edit_button.setToolTip("Change the track to replace and the Blender source file.")
        self.edit_button.clicked.connect(self.edit_requested)
        controls.addWidget(self.edit_button)
        controls.addStretch()
        self._layout.addLayout(controls)
        grid = QGridLayout()
        self.cards: dict[str, ComponentCard] = {}
        for index, spec in enumerate(COMPONENTS):
            card = ComponentCard(spec, self)
            card.mode_requested.connect(self.mode_requested)
            self.cards[spec.id] = card
            grid.addWidget(card, index // 2, index % 2)
        self._layout.addLayout(grid)

    @property
    def busy(self) -> bool:
        return self._checking

    def refresh(self) -> None:
        project = self._project
        if (
            project is None
            or not self._current()
            or self._checking
            or self.services.build.running
            or self.services.editing
        ):
            return
        self._begin_check()
        self.services.status.request(project)

    def _begin_check(self) -> None:
        self._checking = True
        self.notice.setText("Checking component statuses…")
        self.checking.show()
        self._sync()

    def _checked(self) -> None:
        self._checking = False
        self.checking.hide()
        self._sync()

    def _updated(self, payload: object) -> None:
        if (
            not isinstance(payload, StatusResult)
            or not self._current()
            or self._project is None
            or payload.root != self._project.root
        ):
            return
        self._checked()
        for name, card in self.cards.items():
            card.show_status(payload.statuses.get(name))
        incomplete = any(name not in payload.statuses for name in self.cards)
        message = "Some parts were not checked; try Refresh." if incomplete else "Statuses checked."
        self.notice.setText(payload.settings_problem or message)

    def _failed(self, error: object) -> None:
        if not self._current():
            return
        self._checked()
        self.notice.setText(f"Could not check component statuses. {error} Try Refresh.")

    def _current(self) -> bool:
        return self._project is not None and self.services.project is self._project

    def _sync(self, _running: bool = False) -> None:
        building = self.services.build.running
        self.work_label.setText(
            "Build running — showing last checked statuses." if building else ""
        )
        self.work_label.setVisible(building)
        idle = self._current() and not self._checking and not building and not self.services.editing
        self.refresh_button.setEnabled(idle)
        self.copy_project.setEnabled(self._current())
        mutable = idle and self._project is not None and not self._project.read_only
        self.edit_button.setEnabled(mutable)
        for card in self.cards.values():
            card.set_actions_enabled(mutable)

    def _after_build(self, _result: object) -> None:
        if self._current():
            self._begin_check()  # AppServices has already requested the post-build refresh

    def _copy_project(self) -> None:
        if self._current() and self._project is not None:
            QApplication.clipboard().setText(str(self._project.root))
