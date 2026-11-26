"""A path on one line that is never cut off at the edge (P5-T10c, owner decision D2).

The path is shortened in the middle to fit ("C:\\Users\\…\\course.kcl"); the whole path is
its tooltip, its accessible name, and what "Copy path" (right-click) puts on the clipboard
(off for a placeholder such as "No Blender file chosen"). Shortening follows the label's
width and font, so it never makes the window wider than the screen.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QResizeEvent
from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy, QWidget


class PathLabel(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.copy_action = QAction("Copy path", self)
        self.copy_action.triggered.connect(self._copy)
        self.copy_action.setEnabled(False)
        self.addAction(self.copy_action)

    @property
    def full_text(self) -> str:
        return self._full

    def set_path(self, text: str, *, is_path: bool = True) -> None:
        """Show ``text``; ``is_path=False`` for a placeholder that is not a path to copy."""
        self._full = text
        self.setToolTip(text)
        self.setAccessibleName(text)  # the whole path, read once (no separate description)
        self.copy_action.setEnabled(bool(text) and is_path)
        self._fit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._fit()

    def _fit(self) -> None:
        room = self.contentsRect().width()
        metrics = self.fontMetrics()
        shown = self._full
        if room > 0 and metrics.horizontalAdvance(shown) > room:
            shown = metrics.elidedText(shown, Qt.TextElideMode.ElideMiddle, room)
        if self.text() != shown:
            self.setText(shown)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._full)
