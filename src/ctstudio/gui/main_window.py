"""Minimal native-palette Qt Widgets shell, with no build logic on the UI thread."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from ctstudio import __version__


def _ensure_offscreen_font() -> None:
    """Qt's Windows offscreen plugin may expose no system fonts; load one for readable CI PNGs."""
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen" or QFontDatabase.families():
        return
    font_path = (
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        if sys.platform == "win32"
        else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    )
    if not font_path.is_file():
        return
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        return
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    font = app.font()
    font.setFamily(QFontDatabase.applicationFontFamilies(font_id)[0])
    app.setFont(font)


class MainWindow(QMainWindow):
    """Show the empty-project dashboard until project workflows are implemented."""

    def __init__(self) -> None:
        _ensure_offscreen_font()
        super().__init__()
        self.setWindowTitle("CT Studio")
        self.resize(960, 600)
        self.setMinimumSize(720, 480)

        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        heading = QLabel("CT Studio", page)
        heading_font = heading.font()
        heading_font.setPointSize(18)
        heading_font.setBold(True)
        heading.setFont(heading_font)
        layout.addWidget(heading)
        layout.addStretch()

        card = QFrame(page)
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        title = QLabel("No project open", card)
        title.setObjectName("emptyTitle")
        title_font = title.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)
        body = QLabel("Project creation and opening are coming in a later phase.", card)
        body.setObjectName("emptyBody")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        card_layout.addWidget(body)
        layout.addWidget(card)
        layout.addStretch()
        self.setCentralWidget(page)

        self.about_dialog = self._make_about_dialog()
        help_menu = self.menuBar().addMenu("&Help")
        self.about_action = QAction("About CT Studio", self)
        self.about_action.setObjectName("aboutAction")
        self.about_action.triggered.connect(self.about_dialog.open)
        help_menu.addAction(self.about_action)

    def _make_about_dialog(self) -> QDialog:
        dialog = QDialog(self)
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
