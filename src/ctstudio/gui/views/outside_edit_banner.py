"""Signal-only outside-edit choices; project/worker ownership belongs to the dashboard."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def confirm_discard(parent: QWidget) -> bool:
    """Discard is opt-in; Enter and Escape both keep the outside edit by default."""
    dialog = QMessageBox(parent)
    dialog.setObjectName("confirmOutsideDiscard")
    dialog.setWindowTitle("Discard outside edit?")
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setText("Move the changed file or folder to a backup? The next build will remake it.")
    discard = dialog.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
    cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
    dialog.setDefaultButton(cancel)
    dialog.setEscapeButton(cancel)
    try:
        dialog.exec()
        return dialog.clickedButton() is discard
    finally:
        dialog.deleteLater()


class OutsideEditBanner(QWidget):
    """Render caller-supplied eligibility without inspecting or changing any files."""

    requested = Signal(str)  # explicit action: lock or discard

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("outsideEditBanner")
        self._edited = self._eligible = self._working = self._confirming = False
        self._generation = 0
        self.confirm: Callable[[QWidget], bool] = confirm_discard
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.title = self._label("Title")
        self._text(self.title, "Edited outside CT Studio")
        layout.addWidget(self.title)
        self.lock_button = QPushButton("Lock as manual", self)
        self.discard_button = QPushButton("Discard…", self)
        for button, name, tip in (
            (
                self.lock_button,
                "Lock",
                "Keep this change: copy it into files/ and use manual mode.",
            ),
            (self.discard_button, "Discard", "Back up this change; the next build will remake it."),
        ):
            button.setObjectName(f"outsideEdit{name}")
            button.setAccessibleName(button.text())
            button.setToolTip(tip)
            button.setAccessibleDescription(tip)
            layout.addWidget(button)
        self.lock_button.clicked.connect(lambda: self._request("lock"))
        self.discard_button.clicked.connect(lambda: self._request("discard"))
        self.activity, self.note = self._label("Activity"), self._label("Note")
        self.progress = QProgressBar(self)
        self.progress.setObjectName("outsideEditProgress")
        self.progress.setAccessibleName("Outside-edit request progress")
        self.progress.setRange(0, 0)
        for widget in (self.activity, self.progress, self.note):
            layout.addWidget(widget)
        self.clear()

    def set_state(self, *, edited: bool, eligible: bool) -> None:
        """Eligibility is explicit app state, never read back from a disabled ancestor."""
        self._generation += 1
        self._edited, self._eligible = edited, eligible
        self._sync()

    def show_work(self, action: str | None) -> None:
        """The owner accepted a request, or joined it; only the owner calls this."""
        text = (
            ""
            if action is None
            else {
                "lock": "Locking as manual…",
                "discard": "Backing up outside edit…",
            }[action]
        )
        self._generation += 1
        self._working = action is not None
        if self._working:
            self.show_note("")
        self._text(self.activity, text)
        self.progress.setVisible(self._working)
        self.progress.setToolTip(text)
        self.progress.setAccessibleDescription(text)
        self._sync()

    def show_note(self, text: str, detail: str = "") -> None:
        """Keep the latest outcome visible, even after the edited status goes away."""
        self._text(self.note, text, detail)
        self._sync()

    def clear(self) -> None:
        """Invalidate modal approval and clear all per-project activity/results on rebind."""
        self.set_state(edited=False, eligible=False)
        self.show_work(None)
        self.show_note("")

    def _can_request(self) -> bool:
        return self._edited and self._eligible and not self._working and not self._confirming

    def _sync(self) -> None:
        self.title.setVisible(self._edited)
        for button in (self.lock_button, self.discard_button):
            button.setVisible(self._edited)
            button.setEnabled(self._can_request())
        self.setVisible(self._edited or self._working or bool(self.note.text()))

    def _label(self, suffix: str) -> QLabel:
        label = QLabel(self)
        label.setObjectName(f"outsideEdit{suffix}")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setMaximumHeight(label.fontMetrics().lineSpacing() * 4)
        label.installEventFilter(self)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FontChange and isinstance(watched, QLabel):
            watched.setMaximumHeight(watched.fontMetrics().lineSpacing() * 4)
        return super().eventFilter(watched, event)

    @staticmethod
    def _text(label: QLabel, text: str, detail: str = "") -> None:
        label.setText(text)
        full = f"{text}\n{detail}" if detail else text
        label.setToolTip(full)
        label.setAccessibleDescription(full)
        label.setVisible(bool(text))

    def _request(self, action: str) -> None:
        if not self._can_request():
            return
        generation = self._generation
        if action == "discard":
            self._confirming = True
            self._sync()
            try:
                approved = self.confirm(self)
            finally:
                self._confirming = False
                self._sync()
            if not approved:
                return
        if generation == self._generation:
            self.requested.emit(action)
