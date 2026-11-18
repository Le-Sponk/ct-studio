"""P5-T07e2 local evidence: the choice dialog and the Tools route, light/dark, normal/enlarged.

Pictures stay in tests/artifacts/screens (git-ignored, never uploaded). Fonts and palettes
are installed-font proxies (see outside_visual_helpers); native Linux pixels are not shown.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from editor_menu_helpers import offered
from editor_request_helpers import settled
from editor_tools_helpers import ToolsCheck, selected_tool, tools_window
from outside_visual_helpers import visual_style
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QTableWidget, QWidget
from pytestqt.qtbot import QtBot
from wizard_fakes import SCREENS, shot

from ctstudio.gui.views.editor_choices import EditorChoices

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
CASES = [(dark, enlarged) for dark in (False, True) for enlarged in (False, True)]


def inside(child: QWidget, parent: QWidget) -> bool:
    top_left = child.mapTo(parent, child.rect().topLeft())
    return parent.rect().contains(QRect(top_left, child.size()))


def assert_readable(dialog: EditorChoices) -> None:
    """Every shown control fits the dialog, keeps its full label and wrapped notes fit."""
    for button in dialog.findChildren(QAbstractButton):
        if button.isVisible():
            assert inside(button, dialog), f"{button.text()!r} is cut off"
            assert button.width() >= button.sizeHint().width(), f"{button.text()!r} is clipped"
    notes = dialog.notes
    assert notes.wordWrap() and notes.heightForWidth(notes.width()) > 0
    assert notes.height() >= notes.heightForWidth(notes.width()), "the notes are cut short"
    assert inside(notes, dialog) and inside(dialog.choices, dialog)
    assert dialog.width() <= dialog.window().screen().availableGeometry().width()


@pytest.mark.parametrize(
    ("dark", "enlarged"), CASES, ids=["light", "light-big", "dark", "dark-big"]
)
def test_choice_dialog_and_tools_route_pictures(
    qtbot: QtBot, tmp_path: Path, dark: bool, enlarged: bool
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    name = f"p5-t07e2-{'dark' if dark else 'light'}{'-big' if enlarged else ''}"
    with (
        visual_style(app, dark, enlarged),
        tools_window(qtbot, tmp_path, ToolsCheck()) as (
            window,
            work,
        ),
    ):
        window.resize(window.minimumSize())  # the smallest window the app allows
        work.gate.set()
        window.dashboard.cards["course_model"].open_action.trigger()
        dialog = offered(qtbot, window.dashboard)
        dialog.adjustSize()
        QApplication.processEvents()
        assert dialog.setup_button.isVisible()
        assert_readable(dialog)
        shot(dialog, f"{name}-choices.png")
        dialog.setup_button.click()
        page = window.tools_window.page
        tools = window.tools_window.dialog
        assert page is not None and tools is not None
        assert settled(qtbot, lambda: not page.busy)
        assert selected_tool(page) == "riistudio"
        table = page.findChild(QTableWidget, "toolsTable")
        assert table is not None
        row = table.selectionModel().selectedRows()[0].row()
        cell = table.visualRect(table.model().index(row, 0))
        assert table.viewport().rect().contains(cell), "the selected tool is scrolled out of view"
        details = page.findChild(QLabel, "toolDetails")
        assert details is not None and "RiiStudio" in details.text(), "details not shown"
        shot(tools, f"{name}-tools.png")
        tools.reject()
    for part in ("choices", "tools"):
        assert (SCREENS / f"{name}-{part}.png").stat().st_size > 0
