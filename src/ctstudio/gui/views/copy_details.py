"""A "Copy details" button for an inline error message (P5-T10f, owner decision D4).

An error's details (a tool's output, a parser's reason, a traceback) never appear in the
message itself; the button, shown only when there are details, copies the message and its
details together, ready to paste into a bug report.
"""

from __future__ import annotations

import traceback

from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from ctstudio.core.errors import CTStudioError

TIP = "Copy this message and its technical details, to paste into a bug report."


def details_of(error: BaseException) -> str | None:
    """A CTStudioError's own details; for anything unexpected, its traceback."""
    if isinstance(error, CTStudioError):
        return error.details
    return "".join(traceback.format_exception(error))


class CopyDetails(QPushButton):
    def __init__(self, name: str, about: str, parent: QWidget | None = None) -> None:
        super().__init__("Copy details", parent)
        self.setObjectName(name)
        self.setAccessibleName(f"Copy details of the {about}")
        self.setToolTip(TIP)
        self.setAccessibleDescription(TIP)
        self._text = ""
        self.clicked.connect(self._copy)
        self.hide()

    def offer(self, message: str, details: str | None) -> None:
        """Offer ``message`` with ``details``; hidden when there are no details."""
        self._text = f"{message}\n\n{details}" if details else ""
        self.setVisible(bool(details))

    def _copy(self) -> None:
        if self._text:
            QApplication.clipboard().setText(self._text)
