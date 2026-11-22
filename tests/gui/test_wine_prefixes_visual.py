"""P5-T07f3 local evidence: Settings → Editors… → Wine (Linux) light/dark, normal/enlarged,
with long prefix paths, plus a much wider font. Pictures stay in tests/artifacts/screens
(git-ignored, never uploaded); fonts and palettes are installed-font proxies (see
outside_visual_helpers). The small-screen test runs this file on an 800x600 screen too."""

from __future__ import annotations

from pathlib import Path

import pytest
from editor_request_helpers import settled
from editor_settings_helpers import editors_window, write_settings
from outside_visual_helpers import visual_style
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QWidget
from pytestqt.qtbot import QtBot
from wine_prefix_helpers import select_wine, show_wine
from wizard_fakes import SCREENS, shot

from ctstudio.gui.views.editors_page import EditorsPage

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
CASES = [(dark, enlarged) for dark in (False, True) for enlarged in (False, True)]
LONG_PREFIX = "/home/someone/.local/share/wineprefixes/brawlcrate-dotnet48-win32-prefix"
PAINT = {"name": "My paint program", "exe": "C:/Paint/paint.exe", "args_template": ["{file}"]}
SETTINGS = {
    "format": 1,
    "custom_tools": {"custom-paint": PAINT},
    "wine_prefixes": {"brawlcrate": {"prefix": LONG_PREFIX}},
}


def _inside(child: QWidget, parent: QWidget) -> bool:
    corner = child.mapTo(parent, child.rect().topLeft())
    return parent.rect().contains(QRect(corner, child.size()))


def _shown_text(dialog: QDialog) -> list[QLabel]:
    return [label for label in dialog.findChildren(QLabel) if label.isVisible() and label.text()]


def _wrapped_fit(dialog: QDialog) -> bool:
    wrapped = [label for label in _shown_text(dialog) if label.wordWrap()]
    return all(label.height() >= label.heightForWidth(label.width()) for label in wrapped)


def _assert_controls_fit(page: EditorsPage, dialog: QDialog) -> None:
    bar = page.tabs.tabBar()
    for index in range(page.tabs.count()):
        name = page.tabs.tabText(index)
        assert bar.rect().contains(bar.tabRect(index)), f"the {name!r} tab is cut off"
    wine = page.wine
    for control in (wine.rows, wine.choose_button, wine.clear_button):
        assert _inside(control, dialog), f"{control.objectName() or control} is cut off"
    for button in (wine.choose_button, wine.clear_button):
        assert button.width() >= button.sizeHint().width(), f"{button.text()!r} is clipped"
    assert wine.rows.textElideMode() == Qt.TextElideMode.ElideMiddle
    assert not wine.rows.horizontalScrollBar().isVisible(), "rows scroll sideways"


def assert_wine_readable(page: EditorsPage, dialog: QDialog) -> None:
    """Every shown label fits (wrapped ones not cut short), the tabs, rows and buttons are
    inside the window, long rows are shortened in the middle, and the window fits the screen."""
    _assert_controls_fit(page, dialog)
    for label in _shown_text(dialog):
        assert _inside(label, dialog), f"{label.text()!r} is cut off"
        if label.wordWrap():
            needed = label.heightForWidth(label.width())
            assert needed > 0 and label.height() >= needed, f"{label.text()!r} cut short"
    assert dialog.width() <= dialog.screen().availableGeometry().width()
    assert dialog.height() <= dialog.screen().availableGeometry().height()


def _show_longest(qtbot: QtBot, page: EditorsPage, dialog: QDialog) -> None:
    show_wine(page)
    select_wine(page, "BrawlCrate")  # shows the longest how-to text
    # The window refits on the next event turns (a real event loop runs them at once);
    # if it never does, the readable check names the label that is cut short.
    settled(qtbot, lambda: _wrapped_fit(dialog))
    assert page.wine.clear_button.isEnabled() and page.wine.how.text()


@pytest.mark.parametrize(
    ("dark", "enlarged"),
    CASES,
    ids=[f"{'dark' if d else 'light'}{'-big' if e else ''}" for d, e in CASES],
)
def test_wine_tab_pictures(qtbot: QtBot, dark: bool, enlarged: bool) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    write_settings(SETTINGS)
    name = f"p5-t07f3-wine-{'dark' if dark else 'light'}{'-big' if enlarged else ''}"
    with visual_style(app, dark, enlarged), editors_window(qtbot) as (window, page):
        window.resize(window.minimumSize())
        dialog = window.editors_window.dialog
        assert dialog is not None
        _show_longest(qtbot, page, dialog)
        assert page.wine.rows.item(0).toolTip().endswith(str(Path(LONG_PREFIX)))
        assert_wine_readable(page, dialog)
        shot(dialog, f"{name}.png")
    assert (SCREENS / f"{name}.png").stat().st_size > 0


def test_wine_tab_stays_readable_at_a_very_wide_font(qtbot: QtBot) -> None:
    """An enlarged font stretched much wider (wider than Ubuntu's): the window still fits
    the screen and no wrapped text is cut short (on 800x600 the lists give up their room)."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    write_settings(SETTINGS)
    with visual_style(app, False, True), editors_window(qtbot) as (window, page):
        wide = QFont(app.font())
        wide.setStretch(150)
        app.setFont(wide)
        dialog = window.editors_window.dialog
        assert dialog is not None
        _show_longest(qtbot, page, dialog)
        assert_wine_readable(page, dialog)
