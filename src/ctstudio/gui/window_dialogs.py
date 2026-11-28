"""The main window's Settings → Tools… and Settings → Editors… entries, and Help → About.

Both entries open the one Settings window (``settings_window``, P5-T08a) at their page.
``ToolsWindow`` also selects a tool there for a choice dialog's "Set up … in Tools…"
(P5-T07e2); the Tools page selects it once its row is shown.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from ctstudio import version
from ctstudio.gui.settings_window import EDITORS, TOOLS, SettingsWindow
from ctstudio.gui.views.editors_page import EditorsPage
from ctstudio.gui.views.tools_page import ToolsPage


class ToolsWindow:
    """Settings → Tools…: the Settings window at its Tools page."""

    def __init__(self, settings: SettingsWindow) -> None:
        self._settings = settings

    @property
    def dialog(self) -> QDialog | None:
        return self._settings.dialog

    @property
    def page(self) -> ToolsPage | None:
        return self._settings.tools_page

    def open(self, tool_id: str | None = None) -> None:
        """Show the page; with ``tool_id``, select that tool (once its row is shown)."""
        self._settings.open(TOOLS)
        page = self._settings.tools_page
        if tool_id is not None and page is not None:
            page.select(tool_id)


class EditorsWindow:
    """Settings → Editors… (P5-T07f1): the Settings window at its Editors page."""

    def __init__(self, settings: SettingsWindow) -> None:
        self._settings = settings

    @property
    def dialog(self) -> QDialog | None:
        return self._settings.dialog

    @property
    def page(self) -> EditorsPage | None:
        return self._settings.editors_page

    def open(self) -> None:
        self._settings.open(EDITORS)


def about_dialog(parent: QWidget) -> QDialog:
    dialog = QDialog(parent)
    dialog.setObjectName("aboutDialog")
    dialog.setWindowTitle("About CT Studio")
    dialog.setMinimumWidth(420)
    layout = QVBoxLayout(dialog)
    for text in (
        f"CT Studio {version()}",
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
