"""The live project overview (P5-T03b) with launch requests (P5-T03i) and issues (P5-T05b).

Disk work belongs to StatusService and LaunchController; this view only emits requests and
shows their results. Launch results have their own notice, so a status check never hides them.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGridLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.project import Project
from ctstudio.core.project.slots import UnknownSlot
from ctstudio.core.project.slots import find as find_slot
from ctstudio.gui.dashboard_assign import DashboardAssign
from ctstudio.gui.dashboard_builds import DashboardBuilds
from ctstudio.gui.dashboard_editors import DashboardEditors
from ctstudio.gui.dashboard_outside import DashboardOutside
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.launch_text import component_name
from ctstudio.gui.launch_text import describe_launch as describe_launch
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusResult
from ctstudio.gui.views.component_card import ComponentCard
from ctstudio.gui.views.dashboard_watch import DashboardWatch
from ctstudio.gui.views.header_buttons import HeaderButtons
from ctstudio.gui.views.issues_panel import IssuesPanel
from ctstudio.gui.views.path_label import PathLabel


def _explain(widget: QWidget, text: str) -> None:
    """The tooltip and the screen reader's description say the same thing."""
    widget.setToolTip(text)
    widget.setAccessibleDescription(text)


def _label(name: str, parent: QWidget) -> QLabel:
    label = QLabel(parent)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _path(name: str, parent: QWidget) -> PathLabel:
    label = PathLabel(parent)  # one line, shortened in the middle (P5-T10c)
    label.setObjectName(name)
    return label


class Dashboard(QWidget):
    edit_requested = Signal()
    mode_requested = Signal(str, str)
    blender_requested = Signal()
    reveal_requested = Signal(str)
    tools_requested = Signal(str)  # a tool id to set up in Settings → Tools (P5-T07e2)

    def __init__(self, services: AppServices, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self._project: Project | None = None
        self._checking = False
        self.outside_edits = DashboardOutside(self)
        self.editors = DashboardEditors(self)
        self.assigns = DashboardAssign(self)
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
        self.folder_label = _path("dashboardFolder", self)
        self.slot_label = _label("dashboardSlot", self)
        self.source_label = _path("dashboardSource", self)
        form.addRow("Project folder", self.folder_label)
        form.addRow("Replaces", self.slot_label)
        form.addRow("Blender source", self.source_label)
        self._layout.addLayout(form)
        self._make_cards()
        self.watch = DashboardWatch(services, self._shown, self._begin_check, self)
        self._layout.insertWidget(self._layout.indexOf(self.notice) + 1, self.watch.notice)
        self.issues = IssuesPanel(self)
        self.issues.part_requested.connect(self.focus_card)
        self._layout.addWidget(self.issues)
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
        self.outside_edits.bind(project)
        self.editors.clear()
        self._project = project
        self.builds.clear()
        self.issues.clear()
        self.watch.clear()
        self._checking = False
        self._show_launch_text("")  # clears the text and its tooltip, and hides it
        info = project.manifest.project
        self.name_label.setText(info.name)
        self.folder_label.set_path(str(project.root))
        try:
            track = find_slot(info.slot)
            self.slot_label.setText(track.label)
            _explain(self.slot_label, f"{info.slot}.szs")
        except UnknownSlot:  # a hand-edited manifest: the file name is all there is
            self.slot_label.setText(f"{info.slot}.szs")
            _explain(self.slot_label, "")
        source = project.root / info.blend if info.blend else None
        self.source_label.set_path(str(source or "No Blender file chosen"), is_path=bool(source))
        self.access_label.setText(  # only a read-only project needs an access line (P5-T10d)
            f"Read-only — {project.read_only_reason}. You can inspect and copy paths."
            if project.read_only
            else ""
        )
        self.access_label.setVisible(project.read_only)
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
        self.notice.hide()  # shown only with something to say (_say)
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
        self._layout.addWidget(self._controls())
        self._make_grid()

    def _controls(self) -> HeaderButtons:
        self.refresh_button = QPushButton("Refresh statuses", self)
        self.refresh_button.setObjectName("refreshStatuses")
        self.refresh_button.setEnabled(False)
        _explain(self.refresh_button, "Check every part's files and the tools again.")
        self.refresh_button.clicked.connect(self.refresh)
        self.copy_project = QPushButton("Copy project folder", self)
        self.copy_project.setObjectName("copyProjectFolder")
        self.copy_project.setEnabled(False)
        _explain(self.copy_project, "Copy this project's folder path to the clipboard.")
        self.copy_project.clicked.connect(self._copy_project)
        self.edit_button = QPushButton("Project details…", self)
        self.edit_button.setObjectName("editProjectDetails")
        self.edit_button.setToolTip("Change the track to replace and the Blender source file.")
        self.edit_button.clicked.connect(self.edit_requested)
        self.open_blender = QPushButton("Open in Blender", self)
        self.open_blender.setObjectName("openInBlender")
        self.open_blender.clicked.connect(self.blender_requested)
        # One row when it fits, else two; labels are never squeezed (P5-T10d).
        buttons = [self.refresh_button, self.copy_project, self.edit_button, self.open_blender]
        self.header_buttons = HeaderButtons(buttons, self)
        return self.header_buttons

    def _make_grid(self) -> None:
        grid = QGridLayout()
        self.cards: dict[str, ComponentCard] = {}
        for index, spec in enumerate(COMPONENTS):
            card = ComponentCard(spec, self)
            card.mode_requested.connect(self.mode_requested)
            card.reveal_requested.connect(self.reveal_requested)
            card.assign_requested.connect(self.assigns.request)
            card.open_requested.connect(self.editors.request)
            card.reconcile_requested.connect(self.outside_edits.request)
            card.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # the Issues panel can go to it
            card.setAccessibleName(spec.name)
            self.cards[spec.id] = card
            grid.addWidget(card, index // 2, index % 2)
        self._layout.addLayout(grid)

    @property
    def busy(self) -> bool:
        return self._checking

    def refresh(self) -> None:
        project = self._project
        self.watch.follow()  # the manifest may name other outside files now; retries too
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

    def recheck(self) -> None:
        """Drop any status check on its way (it may predate a change) and check again."""
        self.services.status.clear()
        if self._checking:
            self._checked()  # no answer is coming for the dropped check
        self.refresh()

    def _begin_check(self) -> None:
        self._checking = True
        self._say("Checking component statuses…")
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
        title = self._project.manifest.project.name
        self.issues.show_report(payload.issues, payload.issues_problem, title)
        incomplete = any(name not in payload.statuses for name in self.cards)
        message = "Some parts were not checked; try Refresh." if incomplete else ""
        self._say(payload.settings_problem or message)  # all checked: the cards say it

    def _failed(self, error: object) -> None:
        if not self._current():
            return
        self._checked()
        self._say(f"Could not check component statuses. {error} Try Refresh.")

    def _say(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setVisible(bool(text))

    def focus_card(self, part: str) -> None:
        """Scroll to a part's card and put the focus on its first usable control (or on it)."""
        card = self.cards.get(part)
        if card is None:
            return
        area = self.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if area is not None:
            area.ensureWidgetVisible(card)
        buttons = (card.mode_button, card.more_button)
        usable = [button for button in buttons if button.isVisible() and button.isEnabled()]
        (usable[0] if usable else card).setFocus(Qt.FocusReason.OtherFocusReason)

    def _current(self) -> bool:
        return self._project is not None and self.services.project is self._project

    def _shown(self) -> Project | None:
        return self._project if self._current() else None

    @property
    def shown_project(self) -> Project | None:
        return self._shown()

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
        mutable = self.mutable
        self.edit_button.setEnabled(mutable)
        has_source = self._project is not None and bool(self._project.manifest.project.blend)
        self.open_blender.setEnabled(mutable and has_source)
        _explain(self.open_blender, self._blender_tip(has_source))
        for card in self.cards.values():
            card.set_actions_enabled(mutable)
            card.set_inspection_enabled(idle)

    def _blender_tip(self, has_source: bool) -> str:
        """What Open in Blender does, or why it is off."""
        project = self._project
        if project is not None and project.read_only:
            return f"Not available: this project is read-only ({project.read_only_reason})."
        if not has_source:
            return "No Blender file chosen yet: choose one in Project details…"
        return "Start Blender with this project's source file."

    @property
    def mutable(self) -> bool:
        """Current explicit editable ownership, independent of ancestor enablement."""
        return (
            self._idle()
            and not self.services.status.busy
            and self._project is not None
            and not self._project.read_only
        )

    @property
    def inspectable(self) -> bool:
        """Read-only work (editor choices) may start: idle, statuses known."""
        return self._idle() and not self.services.status.busy

    def _idle(self) -> bool:
        """Explicit app state only: current project and no check, build, edit or launch."""
        services = self.services
        busy = services.build.running or services.launch.busy or services.editing
        busy = busy or self.outside_edits.pending
        return self._current() and not self._checking and not busy

    def show_launching(self, component_id: str | None) -> None:
        """The request was accepted; nothing has opened yet."""
        text = (
            "Opening Blender…"
            if component_id is None
            else f"Opening the {component_name(component_id)} folder…"
        )
        self._show_launch_text(text)

    def show_launch_problem(self, error: CTStudioError) -> None:
        """A request refused before it started (nothing was opened)."""
        self._show_launch_text(str(error))

    def show_launch_note(self, text: str) -> None:
        """Window-level news about the launch owner, e.g. that closing must wait for it."""
        self._show_launch_text(text)

    def _launched(self, payload: object) -> None:
        project = self._project
        if (
            isinstance(payload, LaunchResult)
            and project is not None
            and self._current()
            and payload.project is project
            and payload.root == project.root
        ):
            if payload.editor_action is not None:  # before Blender: no component
                self.editors.completed(payload)
            elif payload.edit_action is not None:
                self.outside_edits.completed(payload)
            elif payload.source is not None:
                self.assigns.completed(project, payload)
            elif payload.manifest is project.manifest:
                self._show_launch_text(describe_launch(payload))
        self._sync()

    def _show_launch_text(self, text: str) -> None:
        self.launch_notice.setText(text)
        self.launch_notice.setToolTip(text)  # a long path cut at the edge is whole on hover
        self.launch_notice.setVisible(bool(text))

    def _after_build(self, _result: object) -> None:
        if self._current():
            self._begin_check()  # AppServices has already requested the post-build refresh

    def _copy_project(self) -> None:
        if self._current() and self._project is not None:
            QApplication.clipboard().setText(str(self._project.root))
