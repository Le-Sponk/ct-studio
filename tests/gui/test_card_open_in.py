"""P5-T07e1: a card's "Open in…" action is signal-only and follows explicit eligibility."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtTest import QSignalSpy
from pytestqt.qtbot import QtBot

from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS, ComponentSpec
from ctstudio.core.components.status import ComponentStatus, State
from ctstudio.core.project.project import Project
from ctstudio.gui.views.component_card import ComponentCard

pytestmark = pytest.mark.gui
FILE_PARTS = {"course_model", "kcl", "minimap", "skybox", "kmp"}
READY = ComponentStatus(State.READY, present=True)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "Circuit café 空", "Synthetic track") as opened:
        yield opened


def card_for(qtbot: QtBot, part: str, project: Project) -> ComponentCard:
    card = ComponentCard(COMPONENT_BY_ID[part])
    qtbot.addWidget(card)
    card.bind(project)
    return card


@pytest.mark.parametrize("spec", COMPONENTS, ids=lambda spec: spec.id)
def test_only_single_file_parts_offer_open_in(qtbot: QtBot, spec: ComponentSpec) -> None:
    card = ComponentCard(spec)
    qtbot.addWidget(card)
    menu = card.more_button.menu()
    assert menu is not None
    offered = card.open_action in menu.actions()
    assert offered == (spec.id in FILE_PARTS), f"{spec.id}: Open in… offered={offered}"
    assert card.open_action.text() == "Open in…"
    assert card.open_action.objectName() == f"{spec.id}OpenIn"
    assert card.open_action.toolTip()
    assert not card.open_action.isEnabled(), "Open in… must start disabled"


def test_open_in_needs_inspection_and_a_checked_present_file(
    qtbot: QtBot, project: Project
) -> None:
    card = card_for(qtbot, "course_model", project)
    spy = QSignalSpy(card.open_requested)
    card.set_inspection_enabled(True)
    assert not card.open_action.isEnabled(), "offered before the file was checked"
    card.show_status(ComponentStatus(State.MISSING, ("not made yet",)))
    assert not card.can_open() and not card.open_action.isEnabled(), "offered a missing file"
    card.show_status(ComponentStatus(State.ERROR, ("has not been made yet", "needs X")))
    assert not card.can_open(), "offered an unmade output because its label was Error"
    card.open_action.triggered.emit()  # straight into the slot, past Qt's disablement
    assert spy.count() == 0
    card.show_status(READY)
    assert card.can_open() and card.open_action.isEnabled()
    card.open_action.trigger()
    assert spy.count() == 1
    assert spy.at(0) == ["course_model"]
    card.set_inspection_enabled(False)
    assert not card.can_open() and not card.open_action.isEnabled()
    card.open_action.triggered.emit()
    assert spy.count() == 1, "a disabled card still asked to open"


@pytest.mark.parametrize("state", list(State))
def test_only_the_checked_presence_decides_never_the_label(
    qtbot: QtBot, project: Project, state: State
) -> None:
    card = card_for(qtbot, "kcl", project)
    card.set_inspection_enabled(True)
    card.show_status(ComponentStatus(state, ("reason",), present=True))
    assert card.can_open(), f"{state} with its file present should allow Open in…"
    card.show_status(ComponentStatus(state, ("reason",)))
    assert not card.can_open(), f"{state} without its file offered Open in…"


def test_rebinding_forgets_the_checked_status(qtbot: QtBot, project: Project) -> None:
    card = card_for(qtbot, "skybox", project)
    card.set_inspection_enabled(True)
    card.show_status(READY)
    assert card.can_open()
    card.bind(project)
    assert not card.can_open(), "a rebound card kept the old project's status"


def test_read_only_projects_may_still_open_in(qtbot: QtBot, project: Project) -> None:
    viewer = Project.open(project.root)
    try:
        assert viewer.read_only
        card = card_for(qtbot, "course_model", viewer)
        card.set_actions_enabled(False)  # read-only: nothing mutable
        card.set_inspection_enabled(True)
        card.show_status(READY)
        assert card.can_open(), "reading choices is allowed for read-only projects"
        assert card.more_button.isEnabled()
    finally:
        viewer.close()


def test_parts_without_a_single_file_never_ask(qtbot: QtBot, project: Project) -> None:
    for part in ("posteffect", "objects", "track_info"):
        card = card_for(qtbot, part, project)
        spy = QSignalSpy(card.open_requested)
        card.set_inspection_enabled(True)
        card.show_status(READY)
        card.open_action.triggered.emit()
        assert not card.can_open() and spy.count() == 0, f"{part} asked to open"
