"""P5-T07f2 local evidence: the add/edit dialog light/dark, normal/enlarged, with a refusal
reason shown. Pictures stay in tests/artifacts/screens (git-ignored, never uploaded)."""

from __future__ import annotations

import pytest
from custom_editor_helpers import fill, tool_dialog
from editor_settings_helpers import editors_window, write_settings
from outside_visual_helpers import visual_style
from PySide6.QtCore import QRect
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
    assert dialog.width() <= dialog.screen().availableGeometry().width()
    lines = dialog.arguments.fontMetrics().lineSpacing()
    assert dialog.arguments.height() >= lines * 4, "the arguments box is too short"


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
        fill(dialog, "My paint program", "C:/Program Files/Paint/paint.exe", "{file}\n{folder}")
        dialog.accept()
        assert dialog.problem.isVisible(), "the bad argument was not refused"
        QApplication.processEvents()
        assert_entry_readable(dialog)
        shot(dialog, f"{name}.png")
        dialog.reject()
    assert (SCREENS / f"{name}.png").stat().st_size > 0
