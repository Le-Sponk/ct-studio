"""P5-T10a: the dashboard says things in plain words.

"Replaces" names the track (the file is in its tooltip); "Open in Blender" says why it is
off; the Open in… dialog names the part as well as the file; every dashboard button
explains itself in a tooltip.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from editor_menu_helpers import menu_board, offered
from editor_owner_helpers import EditorWork
from editor_request_helpers import dashboard_for, settled
from editor_tools_helpers import project_for
from PySide6.QtWidgets import QLabel, QPushButton
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.project import slots
from ctstudio.core.project.project import Project
from ctstudio.gui.editor_launch import PreparedEditors
from ctstudio.gui.services import AppServices
from ctstudio.gui.views import dashboard as dashboard_module
from ctstudio.gui.views.dashboard import Dashboard
from ctstudio.gui.views.issues_panel import NO_HELP_PAGE

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]

BLENDER_ON = "Start Blender with this project's source file."
NO_BLEND = "No Blender file chosen yet: choose one in Project details…"


@contextmanager
def board(qtbot: QtBot, project: Project) -> Generator[tuple[Dashboard, AppServices]]:
    services = quiet_services()
    services.adopt(project)
    try:
        yield dashboard_for(qtbot, services, project), services
    finally:
        assert services.shutdown(10)


def blender(page: Dashboard) -> tuple[bool, str, str]:
    button = page.open_blender
    return button.isEnabled(), button.toolTip(), button.accessibleDescription()


def test_replaces_names_the_track_and_keeps_the_file_in_its_tooltip(
    qtbot: QtBot, tmp_path: Path
) -> None:
    project = Project.create(tmp_path / "Piste é", "Piste é", slot="castle_course")
    with board(qtbot, project) as (page, _services):
        assert page.slot_label.text() == "Mario Circuit (Flower Cup, track 1)"
        assert page.slot_label.toolTip() == "castle_course.szs"
        assert page.slot_label.accessibleDescription() == "castle_course.szs"


class Unknown(slots.UnknownSlot):
    def __str__(self) -> str:
        return "not a slot"


def unknown_slot(_text: str) -> slots.Slot:
    raise Unknown("not a slot")


def test_an_unknown_slot_shows_its_file(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Project.create(tmp_path / "Piste é", "Piste é")
    with board(qtbot, project) as (page, _services):
        assert page.slot_label.toolTip(), "a known slot shows its file first"
        monkeypatch.setattr(dashboard_module, "find_slot", unknown_slot)
        page.set_project(project, changed=True)  # shown again: nothing of the old slot stays
        slot = project.manifest.project.slot
        shown = (page.slot_label.text(), page.slot_label.toolTip())
        assert shown == (f"{slot}.szs", "")
        assert page.slot_label.accessibleDescription() == ""


def test_the_help_button_says_why_it_is_off_before_any_check(qtbot: QtBot) -> None:
    services = quiet_services()
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.show()
        help_tip = page.issues.help_button
        assert help_tip.toolTip() == help_tip.accessibleDescription() == NO_HELP_PAGE
    finally:
        assert services.shutdown(10)


def test_open_in_blender_says_why_it_is_off_without_a_blender_file(
    qtbot: QtBot, tmp_path: Path
) -> None:
    project = Project.create(tmp_path / "Piste é", "Piste é")
    with board(qtbot, project) as (page, _services):
        assert blender(page) == (False, NO_BLEND, NO_BLEND)


def test_open_in_blender_explains_itself_when_available(qtbot: QtBot, tmp_path: Path) -> None:
    project = Project.create(tmp_path / "Piste é", "Piste é", blend=tmp_path / "source é.blend")
    with board(qtbot, project) as (page, _services):
        assert blender(page) == (True, BLENDER_ON, BLENDER_ON)


def test_open_in_blender_names_the_read_only_reason(qtbot: QtBot, tmp_path: Path) -> None:
    with project_for(tmp_path / "board", read_only=True) as project:
        with board(qtbot, project) as (page, _services):
            why = f"Not available: this project is read-only ({project.read_only_reason})."
            assert blender(page) == (False, why, why)


def test_the_open_in_dialog_names_the_part_and_the_file(qtbot: QtBot, tmp_path: Path) -> None:
    with menu_board(qtbot, tmp_path / "board") as (page, _services, _project, work, model):
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        dialog = offered(qtbot, page)
        assert dialog.windowTitle() == f"Open Course model ({model.name}) in…"
        described = dialog.choices.accessibleDescription()
        assert described == f"Editors for Course model ({model.name})", described
        labels = [w for w in dialog.findChildren(QLabel) if w.buddy() is dialog.choices]
        assert [w.text() for w in labels] == [f"&Choose an editor for Course model ({model.name}):"]
        dialog.reject()
        assert settled(qtbot, lambda: page.editors.dialog is None)


class ResolvedWork(EditorWork):
    """Choices for the file as the real preparation reports it: resolved, so its path can
    differ from the card's (a short 8.3 name, a junction, a mapped drive)."""

    def prepare(self, project: Project, document: Path) -> PreparedEditors:
        prepared = super().prepare(project, document)
        return replace(prepared, document=Path("Z:/resolved é") / document.name)


def test_the_dialog_names_the_part_even_when_the_path_was_resolved(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = ResolvedWork()
    with menu_board(qtbot, tmp_path / "board", work) as (page, _services, _project, _w, model):
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        dialog = offered(qtbot, page)
        assert dialog.windowTitle() == f"Open Course model ({model.name}) in…"
        dialog.reject()
        assert settled(qtbot, lambda: page.editors.dialog is None)


def test_every_dashboard_button_explains_itself(qtbot: QtBot, tmp_path: Path) -> None:
    project = Project.create(tmp_path / "Piste é", "Piste é")
    with board(qtbot, project) as (page, _services):
        silent = [
            b.text() for b in page.findChildren(QPushButton) if b.isVisible() and not b.toolTip()
        ]
        assert silent == []
        controls = page.builds.controls
        assert controls.test_button.toolTip() == (
            "Build a track to try in the game, with the test compression (Ctrl+B)"
        )
        assert controls.release_button.toolTip() == (
            "Build the track to share, with the release compression; an error in the final"
            " check stops it (Ctrl+Shift+B)"
        )
        assert controls.cancel_button.toolTip() == "Stop the running build (Esc)"
        for button in (controls.test_button, controls.release_button, page.refresh_button):
            assert button.accessibleDescription() == button.toolTip(), button.text()
