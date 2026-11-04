"""A native-palette, read-only view of one registry component."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
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

    def __init__(self, spec: ComponentSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
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
        footer = QHBoxLayout()
        self.mode_label = self._label(f"Mode: {spec.default_mode}", "Mode")
        footer.addWidget(self.mode_label)
        footer.addStretch()
        self.copy_button = QPushButton("Copy path", self)
        self.copy_button.setObjectName(f"{spec.id}CopyPath")
        self.copy_button.setAccessibleName(f"Copy {spec.name} path")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy_path)
        footer.addWidget(self.copy_button)
        layout.addLayout(footer)
        self.show_status(None)

    def bind(self, project: Project) -> None:
        """Use only the in-memory manifest and lexical paths, including missing outputs."""
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
        self.mode_label.setText(f"Mode: {mode}")
        self.copy_button.setEnabled(self.path is not None)
        tip = (
            "No single path is chosen for this part."
            if self.path is None
            else f"Copy planned path (it may not yet exist):\n{self.path}"
        )
        self.copy_button.setToolTip(tip)
        self.copy_button.setAccessibleDescription(tip)
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
