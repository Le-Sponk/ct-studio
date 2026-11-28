"""The wizard's problem lines show their text as typed (found in Deep Clean #1 step d).

They repeat paths and names the user typed or chose; a folder called ``<b>draft`` must not
turn the message bold or hide part of it, so every problem label is plain text.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWizard
from pytestqt.qtbot import QtBot
from wizard_fakes import Choices, Creator, choices, creator, edit, label, make_wizard, wizard_button

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["choices", "creator"]  # fixtures used by name

PROBLEMS = ("locationProblem", "blendProblem", "slotProblem", "createProblem")


def test_every_problem_line_is_plain_text(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    for name in PROBLEMS:
        assert label(wizard, name).textFormat() == Qt.TextFormat.PlainText, name


def test_a_missing_blend_with_markup_in_its_name_is_named_as_typed(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    blend = tmp_path / "<b>draft.blend"  # never created: the name is only shown
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    edit(wizard, "trackName").setText("Ma piste")
    wizard_button(wizard, QWizard.WizardButton.NextButton).click()
    edit(wizard, "blendEdit").setText(str(blend))
    problem = label(wizard, "blendProblem")
    assert "<b>draft.blend" in problem.text() and "was not found" in problem.text()
    assert problem.textFormat() == Qt.TextFormat.PlainText


def test_the_summary_shows_the_typed_name_as_typed(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    blend = tmp_path / "piste.blend"
    blend.write_bytes(b"BLENDER")
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    edit(wizard, "trackName").setText("<b>Ma piste")
    wizard_button(wizard, QWizard.WizardButton.NextButton).click()
    edit(wizard, "blendEdit").setText(str(blend))
    for _ in range(2):
        wizard_button(wizard, QWizard.WizardButton.NextButton).click()
    select = Qt.TextInteractionFlag.TextSelectableByMouse
    for name in ("summaryTrack", "summarySlot"):
        assert label(wizard, name).textFormat() == Qt.TextFormat.PlainText, name
        assert label(wizard, name).textInteractionFlags() & select, name
    assert label(wizard, "summaryTrack").text() == "<b>Ma piste"
