"""P5-T10e: a card's note says only what is new, stays until that card changes; one copy."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel, QPushButton
from pytestqt.qtbot import QtBot

from ctstudio.core.components.assign import Assigned
from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS
from ctstudio.core.components.status import ComponentStatus, State
from ctstudio.core.project.project import Project
from ctstudio.gui.assign_text import STALE_ASSIGNMENT, describe_assignment
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.views.component_card import ComponentCard
from ctstudio.gui.views.wrap_text import ZWSP

pytestmark = [pytest.mark.gui]


def _card(qtbot: QtBot, part: str, project: Project) -> ComponentCard:
    card = ComponentCard(COMPONENT_BY_ID[part])
    qtbot.addWidget(card)
    card.bind(project)
    return card


def test_every_card_has_one_way_to_copy_its_path(qtbot: QtBot, tmp_path: Path) -> None:
    with Project.create(tmp_path / "P", "P") as project:
        for spec in COMPONENTS:
            card = _card(qtbot, spec.id, project)
            buttons = [b for b in card.findChildren(QPushButton) if "copy" in b.text().lower()]
            assert buttons == [], f"{spec.id}: a Copy button as well as the More menu"
            menu = card.more_button.menu()
            assert menu is not None
            copies = [action for action in menu.actions() if "copy" in action.text().lower()]
            assert copies == [card.copy_action], f"{spec.id}: not exactly one copy action"
            assert menu.toolTipsVisible(), "the planned path is only in the action's tooltip"


def test_a_note_stays_through_other_changes_and_goes_with_its_own(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with (
        Project.create(tmp_path / "P", "P") as project,
        Project.create(tmp_path / "Q", "P") as other_project,
    ):
        card = _card(qtbot, "kcl", project)
        card.show_assign_note("Copied from mine.kcl.")
        manifest = project.manifest
        project.manifest = replace(manifest, project=replace(manifest.project, name="Renamed"))
        card.bind(project)  # another part or the name changed: this card did not
        assert card.assign_note.text() == "Copied from mine.kcl."
        assert not card.assign_note.isHidden()
        kcl = replace(project.manifest.components.kcl, mode="manual", file="files/course.kcl")
        project.manifest = replace(
            project.manifest, components=replace(project.manifest.components, kcl=kcl)
        )
        card.bind(project)  # this card's own part changed
        assert not card.assign_note.text() and card.assign_note.isHidden()
        card.show_assign_note("Copied from mine.kcl.")
        kcl = replace(kcl, file="files/other.kcl")
        project.manifest = replace(
            project.manifest, components=replace(project.manifest.components, kcl=kcl)
        )
        card.bind(project)  # the same mode, another file
        assert not card.assign_note.text(), "the note outlived a change of file"
        card.show_assign_note("Copied from mine.kcl.")
        card.bind(other_project)  # another project altogether
        assert not card.assign_note.text(), "a note from another project"
        course = _card(qtbot, "kmp", project)  # no path in either project: only the root differs
        assert course.path is None
        course.show_assign_note("Kept where it is (not copied).")
        course.bind(other_project)
        assert not course.assign_note.text(), "a pathless part's note followed another project"


CASES = [
    (False, "files/course.kcl"),  # copied into the project
    (True, "sources/mine.kcl"),  # kept where it is, inside the project
    (True, "OUTSIDE"),  # kept where it is, outside the project
]


@pytest.mark.parametrize(("reference", "file"), CASES, ids=["copy", "inside", "outside"])
def test_a_card_never_shows_the_file_it_uses_twice(
    qtbot: QtBot, tmp_path: Path, reference: bool, file: str
) -> None:
    file = str(tmp_path / "Ailleurs" / "kept.kcl") if file == "OUTSIDE" else file
    with Project.create(tmp_path / "P", "P") as project:
        card = _card(qtbot, "kcl", project)
        source = tmp_path / "Sources" / "mine.kcl"
        assigned = Assigned(project.manifest, file, None, None)
        result = LaunchResult(
            project, project.root, project.manifest, "kcl", assigned, None, source, reference
        )
        card.show_status(ComponentStatus(State.MANUAL, (f"using {file}",)))
        card.show_assign_note(describe_assignment(result))
        card.show()
        qtbot.waitExposed(card)
        shown = [label.text() for label in card.findChildren(QLabel) if label.isVisible()]
        name = Path(file).name
        assert sum(text.count(name) for text in shown) == 1, f"{name} shown twice: {shown}"
        assert card.assign_note.text(), "nothing said about what was just done"


def test_reopening_the_project_clears_a_note(qtbot: QtBot, tmp_path: Path) -> None:
    with Project.create(tmp_path / "P", "P") as first:
        card = _card(qtbot, "kcl", first)
        card.show_assign_note(STALE_ASSIGNMENT)  # it asks to close and reopen the project
    again = Project.open(tmp_path / "P")
    try:
        card.bind(again)  # the same folder, opened again
        assert not card.assign_note.text(), "the note outlived closing the project"
    finally:
        again.close()


def test_a_long_outside_path_still_shows_the_file_name(qtbot: QtBot, tmp_path: Path) -> None:
    file = tmp_path / ("Dossier très long " * 4) / ("Sous-dossier " * 4) / "kept.kcl"
    with Project.create(tmp_path / "P", "P") as project:
        card = _card(qtbot, "kcl", project)
        card.resize(360, 320)
        card.show_status(ComponentStatus(State.MANUAL, (f"using {file}",)))
        card.show()
        qtbot.waitExposed(card)
        shown = card.summary.text().replace(ZWSP, "")
        assert shown == f"using kept.kcl in {file.parent}", "the name is not first"
        first_line = card.summary.fontMetrics().horizontalAdvance("using kept.kcl")
        assert first_line <= card.summary.width(), "the name does not fit on the first line"
        assert str(file) in card.summary.toolTip()  # the whole reason on hover
        relative = "using files/course.kcl"
        card.show_status(ComponentStatus(State.MANUAL, (relative,)))
        assert card.summary.text() == relative  # inside the project: as it is
