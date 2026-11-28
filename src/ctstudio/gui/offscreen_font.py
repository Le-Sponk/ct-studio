"""A readable font for offscreen frames (CI screenshots and ``--offscreen-smoke``).

Qt's Windows offscreen plugin may expose no system fonts, which draws every letter as a box.
This loads Segoe UI (Windows) or DejaVu Sans (Linux) as the application font, only when the
offscreen platform is in use and Qt found no font itself. The normal window never needs it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication


def font_file() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    return Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def ensure_offscreen_font() -> None:
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen" or QFontDatabase.families():
        return
    path = font_file()
    if not path.is_file():
        return
    font_id = QFontDatabase.addApplicationFont(str(path))
    if font_id < 0:
        return
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    font = app.font()
    font.setFamily(QFontDatabase.applicationFontFamilies(font_id)[0])
    app.setFont(font)
