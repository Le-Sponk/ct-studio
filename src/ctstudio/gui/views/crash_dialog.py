"""The dialog for an error nothing handled (P5-T10f, owner decision D4)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ctstudio.gui.views.plain import plain_label


class CrashDialog(QDialog):
    """The message, the details (read-only) and Copy details, which leaves it open."""

    def __init__(self, message: str, details: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("crashDialog")
        self.setWindowTitle("Unexpected error")
        layout = QVBoxLayout(self)
        layout.addWidget(plain_label(self, text=message))
        self.details = QPlainTextEdit(details, self)
        self.details.setObjectName("crashDetails")
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.details, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.copy_button = QPushButton("Copy details", self)
        self.copy_button.setObjectName("crashCopy")
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(details))
        buttons.addButton(self.copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(640, 360)
