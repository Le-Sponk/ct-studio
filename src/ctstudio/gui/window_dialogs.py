"""The main window's Settings → Tools and Help → About windows (moved out of main_window.py).

``ToolsWindow`` makes the Tools window on first use (its check starts then) and checks again
on later opens; a choice dialog's "Set up … in Tools…" opens the same window with that tool
selected (P5-T07e2).
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from ctstudio import __version__
from ctstudio.gui.services import ToolsService
from ctstudio.gui.views.tools_page import ToolsPage


class ToolsWindow:
    """Settings → Tools: one window, made on first use and reused."""

    def __init__(self, tools: ToolsService, parent: QWidget) -> None:
        self._tools = tools
        self._parent = parent
        self.dialog: QDialog | None = None
        self.page: ToolsPage | None = None

    def open(self, tool_id: str | None = None) -> None:
        """Show the window; with ``tool_id``, select that tool (once its row is shown)."""
        if self.dialog is None or self.page is None:
            dialog = QDialog(self._parent)
            dialog.setObjectName("toolsDialog")
            dialog.setWindowTitle("Tools")
            dialog.resize(900, 560)
            layout = QVBoxLayout(dialog)
            self.page = ToolsPage(self._tools, parent=dialog)
            layout.addWidget(self.page)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            self.dialog = dialog
        elif not self.page.busy:
            self.page.recheck(force=False)
        self.dialog.open()
        if tool_id is not None:
            self.page.select(tool_id)


def about_dialog(parent: QWidget) -> QDialog:
    dialog = QDialog(parent)
    dialog.setObjectName("aboutDialog")
    dialog.setWindowTitle("About CT Studio")
    dialog.setMinimumWidth(420)
    layout = QVBoxLayout(dialog)
    for text in (
        f"CT Studio {__version__}",
        "Turn a Blender project into a Mario Kart Wii custom track.",
        "Licence: GPL-3.0-or-later",
        "Third-party notices will be listed here before release.",
    ):
        label = QLabel(text, dialog)
        label.setWordWrap(True)
        layout.addWidget(label)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return dialog
