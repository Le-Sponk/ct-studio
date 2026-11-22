"""Small parts of Settings → Editors… shared by its tabs (P5-T07f1-f3): a list where Enter
stops at the list, the notes shown after a save, and text helpers for the banner."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QListWidget

from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.spec import CustomTool


class EnterList(QListWidget):
    """Enter on a row acts on it and stops there: a plain list passes Enter on to the window,
    which then also presses its default button (it would close the window, or accept the
    dialog the row just opened)."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()


def choice_note(kind: str, tool: str | None) -> str:
    if tool is None:
        return f"Saved. Open in… now uses the default order for {kind} files."
    return f"Saved. Open in… now lists {TOOL_BY_ID[tool].name} first for {kind} files."


def custom_note(old: CustomTool | None, new: CustomTool) -> str:
    if old is None:
        return f"Added {new.name}. Open in… offers it next time."
    return f"Saved {new.name}. Open in… uses the change next time."


def error_text(error: Exception) -> str:
    return str(error) or type(error).__name__


def breakable(text: str) -> str:
    """Let a Windows path wrap after each backslash (a zero-width space): a word-wrapped label
    cannot break after a backslash, so the path would widen the window past the screen.
    Qt already breaks after "/" when a letter or digit follows (not before "." or "-"),
    which real Linux paths give often enough (tested with a long Linux-style path); one
    folder name over about 65 characters can still widen the window (TD-019)."""
    return text.replace("\\", "\\\u200b")
