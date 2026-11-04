"""Native-palette component data and signal-only editing entry points."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
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


class ComponentCard(QWidget):
    """Present component data; rendering never checks or changes project files."""

    mode_requested = Signal(str, str)

    def __init__(self, spec: ComponentSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
        self._project: Project | None = None
        self._current_mode = spec.default_mode
        self._actions_enabled = False
        self.path: Path | None = None
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
        self.summary = self._label(spec.description, "Summary")
        self.summary.setWordWrap(True)
        self.summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.summary.setMaximumHeight(self.summary.fontMetrics().lineSpacing() * 3)
        layout.addWidget(self.summary)
        self.mode_label = self._label(f"Mode: {spec.default_mode}", "Mode")
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
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_label)
        mode_row.addStretch()
        mode_row.addWidget(self.mode_button)
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
        self.more_button.setEnabled(copyable or mutable)

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

    def _label(self, text: str, suffix: str) -> QLabel:
        label = QLabel(text, self)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setObjectName(f"{self._spec.id}{suffix}")
        return label
