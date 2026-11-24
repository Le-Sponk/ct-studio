"""Fit checks for Settings window pictures (P5-T08a; shared since P5-T08d): the window
within the screen, every page name and button whole, wrapped text at its full height."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QListWidget, QPushButton, QWidget
from settings_window_helpers import page_list


def inside(child: QWidget, parent: QWidget) -> bool:
    top_left = child.mapTo(parent, child.rect().topLeft())
    return parent.rect().contains(QRect(top_left, child.size()))


def wrapped_fit(dialog: QDialog) -> bool:
    """Wrapped text has its height, and the window has fitted itself to its current content:
    its minimum height covers the layout at this width (the fit runs some event turns after
    a tab or text change, and until then a window that happens to be tall enough hides a
    stale minimum, which the user's next drag would cut)."""
    labels = [label for label in dialog.findChildren(QLabel) if label.isVisible()]
    wrapped = [label for label in labels if label.wordWrap() and label.text()]
    for _turn in range(20):  # a layout request climbs one widget per event turn
        QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest.value)
    layout = dialog.layout()
    assert layout is not None, "the window has no layout"
    width = max(dialog.width(), layout.minimumSize().width())
    needed = min(layout.totalHeightForWidth(width), dialog.screen().availableGeometry().height())
    fitted = dialog.minimumHeight() >= needed
    return fitted and all(
        label.height() >= label.heightForWidth(label.width()) for label in wrapped
    )


def assert_list_readable(pages: QListWidget) -> None:
    """Every page name shows whole inside the list, which shows whole in the window."""
    view = pages.viewport().rect()
    for row in range(pages.count()):
        item = pages.item(row)
        rect = pages.visualItemRect(item)
        needed = pages.fontMetrics().horizontalAdvance(item.text())
        assert view.contains(rect), f"{item.text()!r} is outside the page list"
        assert rect.width() >= needed, f"{item.text()!r} is cut short ({rect.width()} < {needed})"
    assert not pages.horizontalScrollBar().isVisible(), "the page list scrolls sideways"


def assert_readable(dialog: QDialog) -> None:
    screen = dialog.screen().availableGeometry()
    assert dialog.width() <= screen.width(), f"{dialog.width()} > {screen.width()}"
    assert dialog.height() <= screen.height(), f"{dialog.height()} > {screen.height()}"
    assert_list_readable(page_list(dialog))
    assert_controls_fit(dialog)


def assert_controls_fit(dialog: QDialog) -> None:
    """Every shown button is whole inside the window; wrapped text has its height."""
    for button in dialog.findChildren(QPushButton):
        if button.isVisible():
            assert inside(button, dialog), f"{button.text()!r} is cut off"
            assert button.width() >= button.minimumSizeHint().width(), f"{button.text()!r}"
    for label in dialog.findChildren(QLabel):
        if label.isVisible() and label.text() and label.wordWrap():
            needed = label.heightForWidth(label.width())
            height = label.height()
            cut = f"{label.text()[:40]!r} is cut short ({height} < {needed} px"
            assert height >= needed, f"{cut}, window {dialog.width()}x{dialog.height()})"
