"""The live project overview (P5-T03b) with launch requests (P5-T03i).

Disk work belongs to StatusService and LaunchController; this view only emits requests and
shows their results. Launch results have their own notice, so a status check never hides them.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGridLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.components.assign import Assigned
from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors
from ctstudio.core.tools import folders as corefolders
from ctstudio.gui.assign_text import STALE_ASSIGNMENT, assignment_detail, describe_assignment
from ctstudio.gui.dashboard_builds import DashboardBuilds
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusResult
from ctstudio.gui.views.component_card import ComponentCard


def _label(name: str, parent: QWidget) -> QLabel:
    label = QLabel(parent)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _component_name(component_id: str | None) -> str:
    spec = COMPONENT_BY_ID.get(component_id or "")
    return spec.name if spec is not None else "this part"


def describe_launch(result: LaunchResult) -> str:
    """Plain words for a finished launch: dispatch only, never a claim that a file loaded."""
    receipt, error = result.receipt, result.error
    if isinstance(receipt, editors.Launched):
        lines = [
            f"Blender was started (process {receipt.pid}) with {receipt.document}.",
            "CT Studio cannot tell whether Blender finished opening the file.",
            *receipt.warnings,
        ]
        return "\n".join(lines)
    if isinstance(receipt, corefolders.OpenedFolder):
        return (
            f"Asked the system to open {receipt.folder}. "
            "If no window appears, open that folder in your file manager."
        )
    if isinstance(error, CTStudioError):
        return str(error)  # already an explanation and a next step
    subject = "open Blender" if result.component_id is None else "open the folder"
    if error is not None and not isinstance(error, Exception):
        return f"The request to {subject} was interrupted. Try again."
    reason = str(error) or type(error).__name__
    return f"Could not {subject}: {reason}. Try again; if it keeps failing, restart CT Studio."


class Dashboard(QWidget):
    edit_requested = Signal()
    mode_requested = Signal(str, str)
    blender_requested = Signal()
    reveal_requested = Signal(str)

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
        self.builds = DashboardBuilds(self)
        self._layout.addWidget(self.builds.log)
        self._layout.addWidget(self.builds.controls)
        self.services.status.updated.connect(self._updated)
        self.services.status.failed.connect(self._failed)
        self.services.build.running_changed.connect(self._sync)
        self.services.build.finished.connect(self._after_build)
        self.services.build.failed.connect(self._after_build)
        self.services.launch.busy_changed.connect(self._sync)
        self.services.launch.completed.connect(self._launched)

    def set_project(self, project: Project, *, changed: bool = False) -> None:
        if project is self._project and not changed:
            self.refresh()  # retain last good results, including during an existing check/build
            return
        self._project = project
        self.builds.clear()
        self._checking = False
        self.launch_notice.clear()
        self.launch_notice.hide()
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
        self.launch_notice = _label("dashboardLaunchNotice", self)
        self.launch_notice.hide()
        self._layout.addWidget(self.launch_notice)
        self.launch_progress = QProgressBar(self)
        self.launch_progress.setObjectName("dashboardLaunching")
        self.launch_progress.setRange(0, 0)
        self.launch_progress.hide()
        self._layout.addWidget(self.launch_progress)
        self._layout.addLayout(self._controls())
        self._make_grid()

    def _controls(self) -> QGridLayout:
        self.refresh_button = QPushButton("Refresh statuses", self)
        self.refresh_button.setObjectName("refreshStatuses")
        self.refresh_button.setEnabled(False)
        self.refresh_button.clicked.connect(self.refresh)
        # Two columns retain full native labels with wider desktop fonts at minimum width.
        controls = QGridLayout()
        controls.addWidget(self.refresh_button, 0, 0)
        self.copy_project = QPushButton("Copy project folder", self)
        self.copy_project.setObjectName("copyProjectFolder")
        self.copy_project.setEnabled(False)
        self.copy_project.clicked.connect(self._copy_project)
        controls.addWidget(self.copy_project, 0, 1)
        self.edit_button = QPushButton("Project details…", self)
        self.edit_button.setObjectName("editProjectDetails")
        self.edit_button.setToolTip("Change the track to replace and the Blender source file.")
        self.edit_button.clicked.connect(self.edit_requested)
        controls.addWidget(self.edit_button, 1, 0)
        self.open_blender = QPushButton("Open in Blender", self)
        self.open_blender.setObjectName("openInBlender")
        self.open_blender.setToolTip("Start Blender with this project's source file.")
        self.open_blender.setAccessibleDescription(self.open_blender.toolTip())
        self.open_blender.clicked.connect(self.blender_requested)
        controls.addWidget(self.open_blender, 1, 1)
        controls.setColumnStretch(0, 1)
        controls.setColumnStretch(1, 1)
        return controls

    def _make_grid(self) -> None:
        grid = QGridLayout()
        self.cards: dict[str, ComponentCard] = {}
        for index, spec in enumerate(COMPONENTS):
            card = ComponentCard(spec, self)
            card.mode_requested.connect(self.mode_requested)
            card.reveal_requested.connect(self.reveal_requested)
            card.assign_requested.connect(self._assign)
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
        self.builds.sync()
        building = self.services.build.running
        self.work_label.setText(
            "Build running — showing last checked statuses." if building else ""
        )
        self.work_label.setVisible(building)
        self.launch_progress.setVisible(self.services.launch.busy and self._current())
        idle = self._idle()
        self.refresh_button.setEnabled(idle)
        self.copy_project.setEnabled(self._current())
        mutable = idle and self._project is not None and not self._project.read_only
        self.edit_button.setEnabled(mutable)
        has_source = self._project is not None and bool(self._project.manifest.project.blend)
        self.open_blender.setEnabled(mutable and has_source)
        for card in self.cards.values():
            card.set_actions_enabled(mutable)
            card.set_inspection_enabled(idle)

    def _idle(self) -> bool:
        """Explicit app state only: current project and no check, build, edit or launch."""
        services = self.services
        busy = services.build.running or services.launch.busy or services.editing
        return self._current() and not self._checking and not busy

    def show_launching(self, component_id: str | None) -> None:
        """The request was accepted; nothing has opened yet."""
        text = (
            "Opening Blender…"
            if component_id is None
            else f"Opening the {_component_name(component_id)} folder…"
        )
        self._show_launch_text(text)

    def show_launch_problem(self, error: CTStudioError) -> None:
        """A request refused before it started (nothing was opened)."""
        self._show_launch_text(str(error))

    def show_launch_note(self, text: str) -> None:
        """Window-level news about the launch owner, e.g. that closing must wait for it."""
        self._show_launch_text(text)

    def _assign(self, part: str, source: Path, reference: bool) -> None:
        """A card asked to use ``source``; the launch owner runs it, ``_assigned`` reports."""
        card = self.cards.get(part)
        if card is None or not self._current():
            return
        try:
            started = self.services.start_assign(part, source, reference=reference)
        except CTStudioError as exc:
            card.show_assign_note(str(exc))
            return
        if started:
            doing = "Recording" if reference else "Copying"
            where = "" if reference else " into the project"
            card.show_assign_note(f"{doing} {source.name or source}{where}…")

    def _launched(self, payload: object) -> None:
        project = self._project
        if (
            isinstance(payload, LaunchResult)
            and project is not None
            and self._current()
            and payload.project is project
            and payload.root == project.root
        ):
            if payload.source is not None:
                self._assigned(project, payload)
            elif payload.manifest is project.manifest:
                self._show_launch_text(describe_launch(payload))
        self._sync()

    def _assigned(self, project: Project, result: LaunchResult) -> None:
        """Publish a saved assignment (UI thread, worker joined), then check statuses again."""
        card = self.cards.get(result.component_id or "")
        saved = isinstance(result.receipt, Assigned)
        if saved and result.manifest is not project.manifest:  # changed meanwhile: keep it
            if card is not None:
                card.show_assign_note(STALE_ASSIGNMENT)
            return
        if isinstance(result.receipt, Assigned):  # (saved; pyright needs the narrowing)
            project.manifest = result.receipt.manifest
            for each in self.cards.values():
                each.bind(project)
            self.services.status.clear()
            self.refresh()
        self._show_launch_text("")
        if card is not None:
            card.show_assign_note(describe_assignment(result), assignment_detail(result))

    def _show_launch_text(self, text: str) -> None:
        self.launch_notice.setText(text)
        self.launch_notice.setVisible(bool(text))

    def _after_build(self, _result: object) -> None:
        if self._current():
            self._begin_check()  # AppServices has already requested the post-build refresh

    def _copy_project(self) -> None:
        if self._current() and self._project is not None:
            QApplication.clipboard().setText(str(self._project.root))
