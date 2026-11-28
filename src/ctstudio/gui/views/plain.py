"""Plain-text labels and activity bars, set up one way across the views (Deep Clean #1 step d).

A label shows its text as typed, never as HTML, and wraps it. ``fill`` lets the label take
the layout's width instead of widening the window for one long line; ``selectable`` lets the
reader select and copy the text. A busy bar shows activity with no known length.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QSizePolicy, QWidget


def plain_label(
    parent: QWidget, name: str = "", text: str = "", *, fill: bool = False, selectable: bool = False
) -> QLabel:
    label = QLabel(text, parent)
    if name:
        label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if fill:
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    if selectable:
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def busy_bar(parent: QWidget, name: str, *, slim: bool = False) -> QProgressBar:
    """``slim``: a thin bar without its percentage text, for a page's background checks."""
    bar = QProgressBar(parent)
    bar.setObjectName(name)
    bar.setRange(0, 0)
    if slim:
        bar.setTextVisible(False)
        bar.setMaximumHeight(6)
    return bar
