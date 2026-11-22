"""P5-T07f2 local evidence: the add/edit dialog light/dark, normal/enlarged, with a refusal
reason shown. Pictures stay in tests/artifacts/screens (git-ignored, never uploaded)."""

from __future__ import annotations

import pytest
from custom_editor_helpers import fill, tool_dialog
from editor_settings_helpers import editors_window, write_settings
from outside_visual_helpers import visual_style
from PySide6.QtCore import QRect
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from pytestqt.qtbot import QtBot
from wizard_fakes import SCREENS, shot

from ctstudio.gui.views.custom_tool_dialog import CustomToolDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
CASES = [(dark, enlarged) for dark in (False, True) for enlarged in (False, True)]


def _inside(child: QWidget, parent: QWidget) -> bool:
    corner = child.mapTo(parent, child.rect().topLeft())
    return parent.rect().contains(QRect(corner, child.size()))


def _label_fits(label: QLabel, dialog: CustomToolDialog) -> None:
    assert _inside(label, dialog), f"{label.text()!r} is cut off"
    if label.wordWrap():
        assert label.height() >= label.heightForWidth(label.width()), f"{label.text()!r} short"
    else:
        assert label.width() >= label.sizeHint().width(), f"{label.text()!r} clipped"


def assert_entry_readable(dialog: CustomToolDialog) -> None:
    """Every field and shown label fits the dialog; wrapped text is not cut short."""
    for field in (dialog.name, dialog.program, dialog.browse, dialog.arguments):
        assert _inside(field, dialog), f"{field.objectName() or field} is cut off"
    assert dialog.browse.width() >= dialog.browse.sizeHint().width(), "Browse… is clipped"
    for label in dialog.findChildren(QLabel):
        if label.isVisible() and label.text():
            _label_fits(label, dialog)
    screen = dialog.screen().availableGeometry()
    assert dialog.width() <= screen.width() and dialog.height() <= screen.height(), dialog.size()
    lines = dialog.arguments.fontMetrics().lineSpacing()
    assert dialog.arguments.height() >= lines * 4, "the arguments box is too short"


def assert_fits_narrowed(dialog: CustomToolDialog) -> None:
    """Made as narrow as it goes at the same height, then also as short as it goes, all the
    wrapped text still fits. A window's own minimum size ignores how tall wrapped text gets
    (on Ubuntu's wider fonts the help text was cut short by a few pixels)."""
    narrow = dialog.minimumSizeHint().width()
    for width, height in ((narrow, dialog.height()), (narrow, 1)):
        dialog.resize(width, height)
        QApplication.processEvents()
        assert_entry_readable(dialog)


def assert_refits(dialog: CustomToolDialog) -> None:
    """After a reason appears the text fits when narrowed, and a longer reason shown in a wide
    window (more lines than the arguments box can give up) still fits when narrowed again."""
    assert_fits_narrowed(dialog)
    dialog.resize(dialog.screen().availableGeometry().width(), 1)
    QApplication.processEvents()
    assert_entry_readable(dialog)
    longer = "--" + "-and-".join(["keep-this-window-open-after-saving"] * 4) + "={folder}"
    dialog.arguments.setPlainText(longer)
    dialog.accept()
    QApplication.processEvents()
    assert dialog.problem.isVisible() and longer in dialog.problem.text()
    assert_entry_readable(dialog)
    assert_fits_narrowed(dialog)


@pytest.mark.parametrize(
    ("dark", "enlarged"),
    CASES,
    ids=[f"{'dark' if d else 'light'}{'-big' if e else ''}" for d, e in CASES],
)
def test_entry_dialog_pictures(qtbot: QtBot, dark: bool, enlarged: bool) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    write_settings({"format": 1})
    name = f"p5-t07f2-entry-{'dark' if dark else 'light'}{'-big' if enlarged else ''}"
    with visual_style(app, dark, enlarged), editors_window(qtbot) as (_window, page):
        page.add_button.click()
        dialog = tool_dialog(qtbot, page)
        first = dialog.size()
        assert_fits_narrowed(dialog)  # before any reason: the help text alone
        dialog.resize(first)
        bad = "--open-in-a-new-window-and-remember-the-folder={folder}"  # a long reason
        fill(dialog, "My paint program", "C:/Program Files/Paint/paint.exe", f"{{file}}\n{bad}")
        dialog.accept()
        assert dialog.problem.isVisible(), "the bad argument was not refused"
        QApplication.processEvents()
        assert_entry_readable(dialog)
        shot(dialog, f"{name}.png")
        assert_refits(dialog)
        dialog.reject()
    assert (SCREENS / f"{name}.png").stat().st_size > 0


def test_entry_dialog_stays_on_screen_at_a_very_wide_font(qtbot: QtBot) -> None:
    """At an enlarged font stretched much wider (wider than Ubuntu's), the window still fits the
    screen and its text stays readable; on an 800x600 screen with Segoe UI it needs its height
    cap (the small-screen test runs this file there; Ubuntu's DejaVu Sans fits without it)."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    write_settings({"format": 1})
    with visual_style(app, False, True), editors_window(qtbot) as (_window, page):
        wide = QFont(app.font())
        wide.setStretch(162)
        app.setFont(wide)
        page.add_button.click()
        dialog = tool_dialog(qtbot, page)
        bad = "--open-in-a-new-window-and-remember-the-folder={folder}"
        fill(dialog, "My paint program", "C:/Program Files/Paint/paint.exe", f"{{file}}\n{bad}")
        dialog.accept()
        assert dialog.problem.isVisible(), "the bad argument was not refused"
        QApplication.processEvents()
        assert_entry_readable(dialog)
        assert_refits(dialog)  # includes a much longer reason: the case that needs the cap
        dialog.reject()
