"""Wide fonts for Settings width tests (TD-022, P5-T10i): Verdana where Windows has it, else
the test font (DejaVu Sans on Ubuntu, about as wide), enlarged and stretched."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from outside_visual_helpers import visual_style
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# % stretch: TD-022 measured the Tools page past 800 px from 132 % on (965 px at 162 %),
# set by its single row of buttons, before P5-T10i put them in two rows.
WIDE = [132, 162]


@contextmanager
def wide_family() -> Generator[str]:
    """Verdana where Windows has it (the wide font TD-022 measured), else the test font
    (DejaVu Sans on Ubuntu, about as wide); a loaded Verdana is removed afterwards."""
    fonts = Path(os.environ.get("WINDIR", "")) / "Fonts" / "verdana.ttf"
    if os.name != "nt" or not fonts.is_file():
        yield QApplication.font().family()
        return
    added = QFontDatabase.addApplicationFont(str(fonts))
    assert added >= 0, "Verdana could not be loaded"
    try:
        yield QFontDatabase.applicationFontFamilies(added)[0]
    finally:
        QFontDatabase.removeApplicationFont(added)


@contextmanager
def wide_font(stretch: int) -> Generator[QApplication]:
    """The enlarged test font in the widest family, stretched to `stretch` %."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with visual_style(app, False, True), wide_family() as family:
        font = QFont(app.font())
        font.setFamilies([family, *font.families()])
        font.setStretch(stretch)
        app.setFont(font)
        yield app
