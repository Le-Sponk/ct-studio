"""P5-T02a: the new-project wizard's track list, and its search."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QWizard
from pytestqt.qtbot import QtBot
from wizard_fakes import (
    Choices,
    Creator,
    choices,
    creator,
    edit,
    fill_first_page,
    label,
    make_wizard,
    slot_item,
    tree,
    visible_slots,
    wizard_button,
)

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["choices", "creator"]  # fixtures used by name

NEXT = QWizard.WizardButton.NextButton


# --- page 3: the track to replace ---------------------------------------------------------------


def test_every_original_track_and_arena_is_listed_by_cup(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    wizard.next()
    wizard.next()
    shown = visible_slots(wizard)
    assert len(shown) == 42
    assert shown[0] == "beginner_course"
    assert tree(wizard).topLevelItemCount() == 10  # 8 cups, 2 arena groups
    current = tree(wizard).currentItem()
    assert current is slot_item(wizard, "beginner_course")


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ("Luigi", ["beginner_course"]),
        ("mmm", ["farm_course"]),
        ("GCN", None),  # every GCN retro track: checked by count below
        ("flower cup", ["castle_course", "shopping_course", "boardcross_course", "truck_course"]),
        ("  KOOPA cape ", ["water_course"]),
    ],
)
def test_search_finds_by_name_abbreviation_or_cup(
    qtbot: QtBot,
    creator: Creator,
    choices: Choices,
    tmp_path: Path,
    search: str,
    expected: list[str] | None,
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    wizard.next()
    wizard.next()
    edit(wizard, "slotSearch").setText(search)
    if expected is None:
        assert len(visible_slots(wizard)) >= 4
    else:
        assert visible_slots(wizard) == expected
    assert wizard_button(wizard, NEXT).isEnabled()


def test_a_search_that_hides_the_choice_picks_the_first_shown(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    wizard.next()
    wizard.next()
    edit(wizard, "slotSearch").setText("flower")
    assert tree(wizard).currentItem() is slot_item(wizard, "castle_course")


def test_a_cup_with_no_match_is_hidden_too(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    wizard.next()
    wizard.next()
    edit(wizard, "slotSearch").setText("flower")
    picker = tree(wizard)
    cups = [picker.topLevelItem(n) for n in range(picker.topLevelItemCount())]
    assert [c.text(0) for c in cups if c is not None and not c.isHidden()] == ["Flower Cup"]
    edit(wizard, "slotSearch").setText("")
    assert all(c is not None and not c.isHidden() for c in cups)


def test_a_search_with_no_match_cannot_go_on_until_cleared(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    wizard.next()
    wizard.next()
    edit(wizard, "slotSearch").setText("zzz")
    assert visible_slots(wizard) == []
    assert not wizard_button(wizard, NEXT).isEnabled()
    assert "no original track" in label(wizard, "slotProblem").text().lower()
    edit(wizard, "slotSearch").setText("")
    assert len(visible_slots(wizard)) == 42
    assert wizard_button(wizard, NEXT).isEnabled()
    assert label(wizard, "slotProblem").text() == ""


def test_choosing_a_cup_row_is_not_a_track(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    wizard.next()
    wizard.next()
    cup = tree(wizard).topLevelItem(1)
    assert cup is not None
    tree(wizard).setCurrentItem(cup)
    assert not wizard_button(wizard, NEXT).isEnabled()
