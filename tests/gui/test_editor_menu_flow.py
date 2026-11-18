"""P5-T07e1: card Open in… → joined preparation → choice dialog → joined launch."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

import pytest
import shiboken6
from editor_menu_helpers import flush_deletes, menu_board, offered, row_texts
from editor_owner_helpers import BUILTIN, CUSTOM, EditorWork
from editor_request_helpers import dashboard_for, no_tools, settled
from launch_controller_helpers import LaunchWork, writable_project
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot

from ctstudio.core.components.status import State, evaluate
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.launch_controller import LaunchController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
STALE_NOTE = "Nothing was opened: the project changed or other work started meanwhile."


def test_card_action_prepares_offers_and_opens_the_chosen_editor(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with menu_board(qtbot, tmp_path) as (page, services, _project, work, model):
        card = page.cards["course_model"]
        card.open_action.trigger()
        assert work.entered.wait(5), "the card action did not reach the joined worker"
        assert page.launch_notice.text() == "Finding editors…"
        assert page.editors.dialog is None, "offered before choices were delivered"
        assert not card.open_action.isEnabled(), "Open in… stayed on while the worker ran"
        work.gate.set()
        dialog = offered(qtbot, page)
        assert work.calls[0][0] == "prepare" and work.calls[0][2] == model
        assert work.calls[0][4] is not threading.main_thread(), "prepared on the UI thread"
        assert row_texts(dialog) == ["builtin", "custom"]
        assert dialog.isVisible() and dialog.isModal()
        dialog.choices.setCurrentRow(1)
        dialog.open_button.click()
        assert settled(qtbot, lambda: not services.launch.busy and len(work.calls) == 2)
        assert [call[3] for call in work.calls] == [None, CUSTOM]
        text = page.launch_notice.text()
        assert text.startswith(f"custom was started (process 321) with {work.launched.document}.")
        assert "cannot tell whether custom finished opening" in text and "Warned." in text
        assert "Blender" not in text
        assert page.editors.dialog is None, "the finished dialog was kept"
        assert card.open_action.isEnabled(), "Open in… did not come back after the launch"


def test_escape_opens_nothing_and_frees_the_dashboard(qtbot: QtBot, tmp_path: Path) -> None:
    with menu_board(qtbot, tmp_path) as (page, services, _project, work, _model):
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        dialog = offered(qtbot, page)
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow)
        dialog.choices.setFocus()
        QTest.keyClick(dialog.choices, Qt.Key.Key_Escape)
        assert dialog.result() == QDialog.DialogCode.Rejected
        flush_deletes()
        assert page.editors.dialog is None
        assert [call[0] for call in work.calls] == ["prepare"]
        assert not services.launch.busy and page.refresh_button.isEnabled()


def test_no_dialog_over_another_modal_window(qtbot: QtBot, tmp_path: Path) -> None:
    with menu_board(qtbot, tmp_path) as (page, services, _project, work, _model):
        other = QDialog(page)  # e.g. the Tools or About window, opened while choices load
        page.cards["course_model"].open_action.trigger()
        other.open()
        qtbot.waitUntil(lambda: QApplication.activeModalWidget() is other)
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy)
        assert page.editors.dialog is None, "a choice dialog was stacked on another window"
        assert page.launch_notice.text().startswith("Editor choices for")
        other.reject()


def test_the_real_status_check_offers_no_unmade_file(qtbot: QtBot, tmp_path: Path) -> None:
    """A new project without tools: every made part is Error (not Missing) and has no file."""
    held = EditorWork()
    held.gate.set()
    other = LaunchWork()
    other.gate.set()
    status = StatusService(find_tools=no_tools)  # the real evaluator
    controller = LaunchController(blender=other, folders=other, editors=held)
    services = AppServices(launch=controller, status=status, build=BuildController())
    project = writable_project(tmp_path)
    services.adopt(project)
    try:
        page = dashboard_for(qtbot, services, project)
        statuses = evaluate(project, ())
        assert statuses["course_model"].state == State.ERROR, "precondition from the review"
        for part in ("course_model", "kcl", "minimap", "skybox", "kmp"):
            card = page.cards[part]
            assert not card.can_open() and not card.open_action.isEnabled(), part
            card.open_action.triggered.emit()  # straight into the slot
        assert held.calls == [] and page.editors.dialog is None
    finally:
        assert services.shutdown(10)


def test_a_project_changed_while_choosing_opens_nothing_and_says_so(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with menu_board(qtbot, tmp_path) as (page, services, project, work, _model):
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        dialog = offered(qtbot, page)
        project.manifest = replace(project.manifest)  # e.g. saved elsewhere meanwhile
        dialog.choices.setCurrentRow(0)
        dialog.open_button.click()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert [call[0] for call in work.calls] == ["prepare"], "a stale choice was opened"
        assert not services.launch.busy
        assert page.launch_notice.text() == STALE_NOTE


def test_work_started_while_choosing_opens_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    with menu_board(qtbot, tmp_path) as (page, services, _project, work, _model):
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        dialog = offered(qtbot, page)
        services.editing = True  # project details opened by another route meanwhile
        dialog.choices.setCurrentRow(0)
        dialog.open_button.click()
        assert [call[0] for call in work.calls] == ["prepare"], "opened while details were open"
        assert page.launch_notice.text() == STALE_NOTE
        services.editing = False


def test_rebinding_closes_an_open_choice_dialog(qtbot: QtBot, tmp_path: Path) -> None:
    with menu_board(qtbot, tmp_path) as (page, services, project, work, _model):
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        dialog = offered(qtbot, page)
        page.set_project(project, changed=True)  # e.g. project details were saved
        assert not dialog.isVisible(), "the old project's dialog stayed open"
        assert dialog.result() == QDialog.DialogCode.Rejected and dialog.chosen is None
        assert page.editors.dialog is None
        assert [call[0] for call in work.calls] == ["prepare"]
        # A late "chosen" finish from the retired dialog (re-delivered, before it is deleted)
        # must stay silent; nothing above ran the event loop, so the object is still alive.
        assert shiboken6.isValid(dialog)
        before = page.launch_notice.text()
        dialog.chosen = CUSTOM
        dialog.finished.emit(QDialog.DialogCode.Accepted.value)
        assert [call[0] for call in work.calls] == ["prepare"], "a retired dialog opened"
        assert page.launch_notice.text() == before, "a retired dialog still reported"
        assert not services.launch.busy
        flush_deletes()
        assert not shiboken6.isValid(dialog), "the retired dialog was never deleted"


def test_read_only_cards_offer_choices_but_open_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    with menu_board(qtbot, tmp_path) as (_page, services, project, work, _model):
        work.gate.set()
        viewer = Project.open(project.root)
        services.project = viewer
        try:
            page = dashboard_for(qtbot, services, viewer)
            card = page.cards["course_model"]
            assert settled(qtbot, card.can_open), "a read-only card could not ask for choices"
            card.open_action.trigger()
            dialog = offered(qtbot, page)
            assert not dialog.open_button.isEnabled(), "a read-only project could open"
            notes = dialog.notes.text()
            assert notes.startswith("This project is open read-only here")
            assert f"Why: {viewer.read_only_reason}." in notes, (
                "the project's own reason is missing"
            )
            dialog.reject()
            assert [call[0] for call in work.calls] == ["prepare"]
            assert not services.launch.busy
        finally:
            services.project = project
            viewer.close()


def test_a_failed_preparation_shows_its_reason_and_offers_nothing(
    qtbot: QtBot, tmp_path: Path
) -> None:
    from ctstudio.core.errors import ProjectError

    with menu_board(qtbot, tmp_path) as (page, services, _project, work, _model):
        work.error = ProjectError("Could not inspect editor choices.", hint="Check paths.")
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        assert settled(qtbot, lambda: len(work.calls) == 1 and not services.launch.busy)
        assert page.launch_notice.text() == "Could not inspect editor choices.\nNext: Check paths."
        assert page.editors.dialog is None, "a failed preparation still offered choices"


def test_the_card_asks_only_through_its_own_part_and_path(qtbot: QtBot, tmp_path: Path) -> None:
    with menu_board(qtbot, tmp_path) as (page, _services, _project, work, _model):
        work.gate.set()
        page.editors.request("posteffect")  # no single file
        page.editors.request("no-such-part")
        assert work.calls == [], "a part without a single file was prepared"
        assert page.editors.dialog is None


def test_one_choice_dialog_at_a_time(qtbot: QtBot, tmp_path: Path) -> None:
    with menu_board(qtbot, tmp_path) as (page, services, _project, work, _model):
        work.gate.set()
        page.cards["course_model"].open_action.trigger()
        first = offered(qtbot, page)
        page.editors.request("course_model")  # e.g. a shortcut while the dialog is up
        assert [call[0] for call in work.calls] == ["prepare"], "a second dialog was prepared"
        assert page.editors.dialog is first and not services.launch.busy
        first.choices.setCurrentRow(0)
        first.open_button.click()
        assert settled(qtbot, lambda: not services.launch.busy and len(work.calls) == 2)
        assert [call[3] for call in work.calls] == [None, BUILTIN]
