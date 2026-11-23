"""P5-T08a local evidence: the Settings window at its Tools and Editors pages, light/dark,
normal/enlarged. Also run on a real 800x600 screen (test_editors_small_screen).

Pictures stay in tests/artifacts/screens (git-ignored, never uploaded). Fonts and palettes
are installed-font proxies (see outside_visual_helpers); native Linux pixels are not shown.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from editor_request_helpers import settled
from editor_settings_helpers import write_settings
from outside_visual_helpers import visual_style
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QListWidget, QPushButton, QWidget
from pytestqt.qtbot import QtBot
from settings_window_helpers import (
    action,
    main_window,
    page_list,
    settings_dialog,
    shown_page,
)
from tools_fakes import FakeDoctor, doctor, settings_file
from wizard_fakes import SCREENS, shot

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
__all__ = ["doctor", "settings_file"]  # fixtures used by name
CASES = [
    (page, dark, enlarged)
    for page in ("Tools", "Editors")
    for dark in (False, True)
    for enlarged in (False, True)
]


def inside(child: QWidget, parent: QWidget) -> bool:
    top_left = child.mapTo(parent, child.rect().topLeft())
    return parent.rect().contains(QRect(top_left, child.size()))


def wrapped_fit(dialog: QDialog) -> bool:
    labels = [label for label in dialog.findChildren(QLabel) if label.isVisible()]
    wrapped = [label for label in labels if label.wordWrap() and label.text()]
    return all(label.height() >= label.heightForWidth(label.width()) for label in wrapped)


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
            assert label.height() >= needed, f"{label.text()[:40]!r} is cut short"


@pytest.mark.parametrize(
    ("page", "dark", "enlarged"),
    CASES,
    ids=[f"{p.lower()}-{'dark' if d else 'light'}{'-big' if e else ''}" for p, d, e in CASES],
)
def test_settings_window_pictures(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    page: str,
    dark: bool,
    enlarged: bool,
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    write_settings({"format": 1, "editor_preferences": {".kmp": "kmp_cloud"}})
    name = f"p5-t08a-{page.lower()}-{'dark' if dark else 'light'}{'-big' if enlarged else ''}"
    with (
        visual_style(app, dark, enlarged),
        main_window(qtbot, doctor, settings_file) as (
            window,
            _preferences,
        ),
    ):
        action(window, "toolsAction" if page == "Tools" else "editorsAction").trigger()
        dialog = settings_dialog(window)
        made = window.tools_window.page if page == "Tools" else window.editors_window.page
        assert made is not None
        assert settled(qtbot, lambda: not made.busy), "the page's first read never ended"
        assert settled(qtbot, lambda: wrapped_fit(dialog)), "the window never refitted"
        assert shown_page(dialog) == page
        assert_readable(dialog)
        shot(dialog, f"{name}.png")
        dialog.resize(dialog.width(), 1)  # the user drags it as short as it goes
        QApplication.processEvents()
        assert_readable(dialog)
    assert (SCREENS / f"{name}.png").stat().st_size > 0
