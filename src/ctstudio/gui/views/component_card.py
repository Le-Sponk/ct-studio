"""Native-palette component data and signal-only editing entry points.

Cards of parts that can use a file you supply (a manual mode with its own settings) also take
one dropped file or folder and offer "Choose file…" / "Reference file in place…" (P5-T04b).
They only emit ``assign_requested``; the dashboard runs the assignment and reports back here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.components.registry import ComponentSpec
from ctstudio.core.components.state import GENERATED_DIR
from ctstudio.core.components.status import STATE_LABELS, ComponentStatus, State
from ctstudio.core.project.manifest_io import FILE_NAME
from ctstudio.core.project.project import Project

_STATUS_ICONS = {
    State.MISSING: QStyle.StandardPixmap.SP_MessageBoxQuestion,
    State.STALE: QStyle.StandardPixmap.SP_BrowserReload,
    State.READY: QStyle.StandardPixmap.SP_DialogApplyButton,
    State.WARNING: QStyle.StandardPixmap.SP_MessageBoxWarning,
    State.ERROR: QStyle.StandardPixmap.SP_MessageBoxCritical,
    State.MANUAL: QStyle.StandardPixmap.SP_FileIcon,
    State.EDITED_EXTERNALLY: QStyle.StandardPixmap.SP_FileDialogDetailedView,
}
DROP_ONE = "Drop one file or folder from this computer. Nothing was changed."
ChooseSource = Callable[[QWidget, ComponentSpec, Path], Path | None]  # None: cancelled


def choose_source(parent: QWidget, spec: ComponentSpec, start: Path) -> Path | None:
    """The native chooser: a folder for post-effects, otherwise one file."""
    if spec.kind is None:
        chosen = QFileDialog.getExistingDirectory(
            parent, f"Choose the {spec.name} folder", str(start)
        )
    else:
        chosen, _filter = QFileDialog.getOpenFileName(
            parent, f"Choose the {spec.name} file", str(start)
        )
    return Path(chosen) if chosen else None


def takes_a_file(spec: ComponentSpec) -> bool:
    """A part whose modes include manual and that has its own settings table."""
    return "manual" in spec.modes and spec.manifest_table not in (None, "project")


def _copyable(event: QDropEvent) -> bool:
    copy = Qt.DropAction.CopyAction
    return event.mimeData().hasUrls() and event.possibleActions() & copy == copy


def dropped_path(data: QMimeData) -> Path | None:
    """The one local file or folder in a drop, or None for anything else."""
    urls = data.urls() if data.hasUrls() else []
    if len(urls) != 1 or not urls[0].isLocalFile() or not urls[0].toLocalFile():
        return None
    return Path(urls[0].toLocalFile())


class ComponentCard(QWidget):
    """Present component data; rendering never checks or changes project files."""

    mode_requested = Signal(str, str)
    reveal_requested = Signal(str)
    assign_requested = Signal(str, object, bool)  # part, source Path, reference in place

    def __init__(self, spec: ComponentSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
        self._project: Project | None = None
        self._current_mode = spec.default_mode
        self._actions_enabled = False
        self._inspection_enabled = False
        self.path: Path | None = None
        self.choose: ChooseSource = choose_source
        self.setObjectName(f"card_{spec.id}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        header = self._label(spec.name, "Name")
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)
        status_row = QHBoxLayout()
        self._status_icon = self._label("", "Icon")
        status_row.addWidget(self._status_icon)
        self.status_label = self._label("Not checked", "State")
        status_row.addWidget(self.status_label, 1)
        layout.addLayout(status_row)
        self.build_label = self._label("", "Build")
        self.build_label.hide()
        layout.addWidget(self.build_label)
        self.summary = self._label(spec.description, "Summary")
        self.summary.setWordWrap(True)
        self.summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.summary.setMaximumHeight(self.summary.fontMetrics().lineSpacing() * 3)
        layout.addWidget(self.summary)
        self.mode_label = self._label(f"Mode: {spec.default_mode}", "Mode")
        self.assign_note = self._label("", "AssignNote")
        self.assign_note.setWordWrap(True)
        self.assign_note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.assign_note.setMaximumHeight(self.assign_note.fontMetrics().lineSpacing() * 4)
        self.assign_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.assign_note.hide()
        layout.addWidget(self.assign_note)
        self._add_actions(layout)
        self.show_status(None)

    def _add_actions(self, layout: QVBoxLayout) -> None:
        spec = self._spec
        footer = QHBoxLayout()
        self.mode_button = QPushButton("Change mode…", self)
        self.mode_button.setObjectName(f"{spec.id}ChangeMode")
        self.mode_button.setAccessibleName(f"Change {spec.name} mode")
        self.mode_button.setToolTip("Choose how this part is supplied; review before saving.")
        self.mode_button.setAccessibleDescription(self.mode_button.toolTip())
        self.mode_button.setVisible(self._supports_mode())
        self.mode_button.clicked.connect(self._request_current_mode)
        # Separate rows retain complete native labels with wider desktop fonts.
        mode_row = QVBoxLayout()
        mode_row.addWidget(self.mode_label)
        mode_row.addWidget(self.mode_button, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(mode_row)
        footer.addStretch()
        self.copy_button = QPushButton("Copy path", self)
        self.copy_button.setObjectName(f"{spec.id}CopyPath")
        self.copy_button.setAccessibleName(f"Copy {spec.name} path")
        self.copy_button.clicked.connect(self._copy_path)
        footer.addWidget(self.copy_button)
        self.more_button = QToolButton(self)
        self.more_button.setText("…")
        self.more_button.setObjectName(f"{spec.id}MoreActions")
        self.more_button.setAccessibleName(f"More {spec.name} actions")
        self.more_button.setToolTip("More actions for this part, including Copy path.")
        self.more_button.setAccessibleDescription(self.more_button.toolTip())
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        menu = QMenu(self.more_button)
        self.copy_action = menu.addAction("Copy path")
        self.copy_action.triggered.connect(self._copy_path)
        self.reveal_action = menu.addAction("Open folder")
        self.reveal_action.setObjectName(f"{spec.id}OpenFolder")
        self.reveal_action.setToolTip("Request this part's folder, even if the output is missing.")
        self.reveal_action.triggered.connect(self._request_reveal)
        self._add_file_actions(menu)
        self._mode_menu = QMenu("Mode", menu)
        self._mode_menu.setObjectName(f"{spec.id}ModeMenu")
        self.mode_actions: dict[str, QAction] = {}
        if self._supports_mode():
            menu.addMenu(self._mode_menu)
            for mode in spec.modes:
                action = self._mode_menu.addAction(mode)
                action.setData(mode)
                action.setCheckable(True)
                self.mode_actions[mode] = action
        self._mode_menu.triggered.connect(self._mode_action_triggered)
        self.more_button.setMenu(menu)
        footer.addWidget(self.more_button)
        layout.addLayout(footer)
        self._sync_actions()

    def _add_file_actions(self, menu: QMenu) -> None:
        spec = self._spec
        noun = "folder" if spec.kind is None else "file"
        self.choose_action = QAction(f"Choose {noun}…", self)
        self.choose_action.setObjectName(f"{spec.id}ChooseFile")
        self.choose_action.setToolTip(
            f"Copy a {noun} into the project's files folder and use it for this part. "
            "A different copy already there is backed up first."
        )
        self.choose_action.triggered.connect(lambda: self._choose(reference=False))
        self.reference_action = QAction(f"Reference {noun} in place…", self)
        self.reference_action.setObjectName(f"{spec.id}ReferenceFile")
        self.reference_action.setToolTip(
            f"Use a {noun} where it is; nothing is copied, so keep it there."
        )
        self.reference_action.triggered.connect(lambda: self._choose(reference=True))
        if takes_a_file(spec):
            menu.addAction(self.choose_action)
            menu.addAction(self.reference_action)

    def _can_assign(self) -> bool:
        return (
            takes_a_file(self._spec)
            and self._actions_enabled
            and self._project is not None
            and not self._project.read_only
        )

    def _choose(self, *, reference: bool) -> None:
        project = self._project
        if not self._can_assign() or project is None:
            return
        chosen = self.choose(self, self._spec, project.root)
        # The chooser is modal: the card may have been disabled or rebound meanwhile.
        if chosen is not None and self._can_assign() and self._project is project:
            self.assign_requested.emit(self._spec.id, chosen, reference)

    # acceptDrops() follows _can_assign(), so Qt only offers drags while it holds; a drag can
    # outlive a gate change, so the drop checks again.
    # Always a copy: a move (Shift in Explorer) would let the file manager delete the original.
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _copyable(event):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if not self._can_assign() or not _copyable(event):
            event.ignore()
            return
        source = dropped_path(event.mimeData())
        if source is None:
            event.ignore()
            self.show_assign_note(DROP_ONE)
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.assign_requested.emit(self._spec.id, source, False)

    def show_assign_note(self, text: str, detail: str = "") -> None:
        """The latest file assignment news for this card (``detail`` adds to the tooltip)."""
        self.assign_note.setText(text)
        full = f"{text}\n{detail}" if detail else text
        self.assign_note.setToolTip(full)
        self.assign_note.setAccessibleDescription(full)  # screen readers get the full path too
        self.assign_note.setVisible(bool(text))

    def _supports_mode(self) -> bool:
        return self._spec.manifest_table not in (None, "project") and len(self._spec.modes) > 1

    def _can_change_mode(self) -> bool:
        return (
            self._supports_mode()
            and self._actions_enabled
            and self._project is not None
            and not self._project.read_only
        )

    def set_actions_enabled(self, enabled: bool) -> None:
        """Gate mutable actions only; planned-path copying remains available."""
        self._actions_enabled = enabled
        self._sync_actions()

    def _sync_actions(self) -> None:
        mutable = self._can_change_mode()
        self.mode_button.setEnabled(mutable)
        self._mode_menu.setEnabled(mutable)
        for mode, action in self.mode_actions.items():
            action.setEnabled(mutable)
            action.setChecked(mode == self._current_mode)
        copyable = self.path is not None
        self.copy_button.setEnabled(copyable)
        self.copy_action.setEnabled(copyable)
        self.copy_action.setToolTip(self.copy_button.toolTip())
        self.reveal_action.setEnabled(self._inspection_enabled and copyable)
        assignable = self._can_assign()
        self.choose_action.setEnabled(assignable)
        self.reference_action.setEnabled(assignable)
        self.setAcceptDrops(assignable)
        self.more_button.setEnabled(copyable or mutable or assignable)

    def set_inspection_enabled(self, enabled: bool) -> None:
        """Gate folder dispatch separately from mutable modes and always-available copy."""
        self._inspection_enabled = enabled
        self._sync_actions()

    def _request_reveal(self) -> None:
        if self._inspection_enabled and self._project is not None and self.path is not None:
            self.reveal_requested.emit(self._spec.id)

    def _request_current_mode(self) -> None:
        self._request_mode("")

    def _mode_action_triggered(self, action: QAction) -> None:
        self._request_mode(str(action.data()))

    def _request_mode(self, mode: str) -> None:
        # QAction toggles before triggered; only a later bind may publish a new mode.
        self._sync_actions()
        if self._can_change_mode() and (mode == "" or mode in self.mode_actions):
            self.mode_requested.emit(self._spec.id, mode)

    def bind(self, project: Project) -> None:
        """Use only the in-memory manifest and lexical paths, including missing outputs."""
        self._project = project
        self.path = None
        if self._spec.manifest_table == "project":
            mode = self._spec.default_mode
            self.path = project.root / FILE_NAME
        elif self._spec.manifest_table is None:
            mode = self._spec.default_mode
        else:
            table = getattr(project.manifest.components, self._spec.manifest_table)
            mode = table.mode
            if mode == "manual":
                if table.file:
                    self.path = project.root / Path(table.file)
            elif self._spec.outputs:
                self.path = project.root / GENERATED_DIR / self._spec.outputs[0]
        self._current_mode = mode
        self.mode_label.setText(f"Mode: {mode}")
        tip = (
            "No single path is chosen for this part."
            if self.path is None
            else f"Copy planned path (it may not yet exist):\n{self.path}"
        )
        self.copy_button.setToolTip(tip)
        self.copy_button.setAccessibleDescription(tip)
        self._sync_actions()
        self.show_status(None)
        self.show_assign_note("")

    def show_status(self, status: ComponentStatus | None) -> None:
        """Render an already evaluated status; None is explicitly not checked."""
        text = "Not checked" if status is None else STATE_LABELS[status.state]
        reasons = () if status is None else status.reasons
        summary = reasons[0] if reasons else self._spec.description
        details = "\n".join(reasons) if reasons else self._spec.description
        self.status_label.setText(text)
        self.summary.setText(summary)
        self._status_icon.setAccessibleName(text)
        if status is None:
            self._status_icon.clear()
        else:
            icon = self.style().standardIcon(_STATUS_ICONS[status.state])
            self._status_icon.setPixmap(icon.pixmap(16, 16))
        for widget in (self, self.summary, self.status_label):
            widget.setToolTip(details)
            widget.setAccessibleDescription(details)

    def _copy_path(self) -> None:
        if self.path is not None:
            QApplication.clipboard().setText(str(self.path))

    def show_build_state(self, text: str) -> None:
        """A run overlay, never a replacement for last-good checked status/reasons."""
        self.build_label.setText(text)
        self.build_label.setToolTip(text)
        self.build_label.setAccessibleDescription(text)
        self.build_label.setVisible(bool(text))

    def _label(self, text: str, suffix: str) -> QLabel:
        label = QLabel(text, self)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setObjectName(f"{self._spec.id}{suffix}")
        return label
