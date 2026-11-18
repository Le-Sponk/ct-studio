"""P5-T07e2: a missing built-in editor in the choice dialog leads to the Tools window.

Unavailable rows are disabled (neither mouse nor keys select them), so the dialog offers one
"Set up … in Tools…" button for its missing built-in editors rather than per selected row.
"""

from __future__ import annotations

import pytest
from editor_tools_helpers import (
    CRATE_FOUND,
    LORENZI_NO_KCL,
    MINE_MISSING,
    RII_MISSING,
    prepared,
)
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot

from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.gui.editor_launch import EditorOption, PreparedEditors
from ctstudio.gui.views.editor_choices import EditorChoices

pytestmark = pytest.mark.gui
CRATE_MISSING = EditorOption(
    EditorChoice("builtin", "brawlcrate"), "BrawlCrate", "missing", "Not found.", "Install it."
)


def shown(qtbot: QtBot, choices: PreparedEditors, *, can_open: bool = True) -> EditorChoices:
    dialog = EditorChoices(choices, can_open=can_open)
    qtbot.addWidget(dialog)
    dialog.open()
    qtbot.waitUntil(dialog.isVisible)
    return dialog


def test_a_missing_builtin_editor_is_offered_in_tools(qtbot: QtBot) -> None:
    dialog = shown(qtbot, prepared(RII_MISSING, CRATE_FOUND, LORENZI_NO_KCL, MINE_MISSING))
    button = dialog.setup_button
    assert button.isVisible() and button.isEnabled()
    assert button.text() == "Set up RiiStudio in Tools…"
    assert "Settings → Tools" in button.toolTip()
    assert dialog.open_button.isDefault(), "Return must still open the selected editor"
    button.click()
    assert dialog.result() == QDialog.DialogCode.Rejected and not dialog.isVisible()
    assert dialog.setup == "riistudio" and dialog.chosen is None


def test_several_missing_editors_go_to_tools_at_the_first(qtbot: QtBot) -> None:
    dialog = shown(qtbot, prepared(MINE_MISSING, CRATE_MISSING, RII_MISSING))
    assert dialog.setup_button.text() == "Set up editors in Tools…"
    dialog.setup_button.click()
    assert dialog.setup == "brawlcrate", "not the first missing built-in editor in the list"


@pytest.mark.parametrize(
    "options",
    [(CRATE_FOUND, LORENZI_NO_KCL), (CRATE_FOUND, MINE_MISSING), (CRATE_FOUND,)],
    ids=["ineligible lorenzi", "missing custom tool", "all found"],
)
def test_only_missing_builtin_editors_lead_to_tools(
    qtbot: QtBot, options: tuple[EditorOption, ...]
) -> None:
    """Lorenzi needs a file, not a tool; custom tools are not on the Tools page."""
    dialog = shown(qtbot, prepared(*options))
    assert not dialog.setup_button.isVisible() and not dialog.setup_button.isEnabled()
    dialog.setup_button.clicked.emit()  # straight into the slot, past Qt's disablement
    assert dialog.setup is None and dialog.isVisible()


def test_read_only_projects_may_still_set_up_tools(qtbot: QtBot) -> None:
    """Setting up a tool changes CT Studio's own settings, never the project."""
    dialog = shown(qtbot, prepared(RII_MISSING, CRATE_FOUND), can_open=False)
    assert dialog.setup_button.isEnabled() and not dialog.open_button.isEnabled()
    dialog.setup_button.click()
    assert dialog.setup == "riistudio" and dialog.chosen is None


def test_the_keyboard_reaches_set_up_right_after_the_list(qtbot: QtBot) -> None:
    dialog = shown(qtbot, prepared(RII_MISSING, CRATE_FOUND))
    dialog.activateWindow()
    qtbot.waitUntil(dialog.isActiveWindow)
    dialog.choices.setFocus()
    assert dialog.choices.hasFocus(), "the choice list did not take the keyboard focus"
    layout = dialog.layout()
    assert layout is not None
    assert layout.indexOf(dialog.setup_button) == layout.indexOf(dialog.choices) + 1, (
        "Set up is not shown right below the list, where Tab reaches it"
    )
    QTest.keyClick(dialog.choices, Qt.Key.Key_Tab)
    assert QApplication.focusWidget() is dialog.setup_button, "Tab skipped Set up in Tools…"
    QTest.keyClick(dialog.setup_button, Qt.Key.Key_Space)
    assert dialog.setup == "riistudio" and dialog.result() == QDialog.DialogCode.Rejected


def test_open_still_clears_setup(qtbot: QtBot) -> None:
    dialog = shown(qtbot, prepared(RII_MISSING, CRATE_FOUND))
    dialog.open_button.click()
    assert dialog.chosen == CRATE_FOUND.choice and dialog.setup is None
