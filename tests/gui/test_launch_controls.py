"""P5-T03i: dashboard and card launch controls, notices and stale-result handling."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from launch_controller_helpers import LaunchWork, owned_launch
from PySide6.QtTest import QSignalSpy
from pytestqt.qtbot import QtBot

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.errors import ToolNotFound
from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import LaunchResult, Receipt
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusResult
from ctstudio.gui.views.component_card import ComponentCard
from ctstudio.gui.views.dashboard import Dashboard, describe_launch

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def page_for(qtbot: QtBot, services: AppServices, project: Project) -> Dashboard:
    page = Dashboard(services)
    qtbot.addWidget(page)
    page.set_project(project)
    page.resize(900, 800)
    page.show()
    qtbot.waitUntil(lambda: not page.busy)
    return page


def finished(
    project: Project,
    component: str | None,
    *,
    receipt: Receipt | None = None,
    error: BaseException | None = None,
) -> LaunchResult:
    return LaunchResult(project, project.root, project.manifest, component, receipt, error)


def test_card_reveal_is_a_request_with_its_own_gate(qtbot: QtBot, tmp_path: Path) -> None:
    with Project.create(tmp_path / "Pistë 日本", "Synthetic") as project:
        card = ComponentCard(COMPONENT_BY_ID["kcl"])
        qtbot.addWidget(card)
        card.bind(project)
        spy = QSignalSpy(card.reveal_requested)
        card.set_actions_enabled(False)
        card.set_inspection_enabled(True)
        menu = card.more_button.menu()
        assert card.reveal_action.text() == "Open folder"
        assert card.reveal_action in menu.actions()
        assert card.reveal_action.isEnabled() and not card.mode_button.isEnabled()
        card.reveal_action.trigger()
        assert [spy.at(i) for i in range(spy.count())] == [["kcl"]]
        card.set_inspection_enabled(False)
        card.reveal_action.triggered.emit()  # a direct trigger is also refused
        assert spy.count() == 1
        assert card.copy_button.isEnabled() and card.copy_action.isEnabled()


def test_cards_without_a_single_path_cannot_reveal(qtbot: QtBot, tmp_path: Path) -> None:
    with Project.create(tmp_path / "Pistë", "Synthetic") as project:
        card = ComponentCard(COMPONENT_BY_ID["objects"])
        qtbot.addWidget(card)
        card.bind(project)
        card.set_inspection_enabled(True)
        spy = QSignalSpy(card.reveal_requested)
        assert card.path is None and not card.reveal_action.isEnabled()
        card.reveal_action.triggered.emit()
        assert spy.count() == 0


def test_controls_follow_explicit_state(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path) as (services, project, work):
        page = page_for(qtbot, services, project)
        assert page.open_blender.isEnabled() and page.open_blender.objectName() == "openInBlender"
        assert page.cards["kcl"].reveal_action.isEnabled()
        assert services.start_launch("kcl")
        assert work.entered.wait(5)
        qtbot.waitUntil(page.launch_progress.isVisible)
        for control in (page.open_blender, page.refresh_button, page.edit_button):
            assert not control.isEnabled()
        assert not page.cards["kcl"].reveal_action.isEnabled()
        assert page.cards["kcl"].copy_button.isEnabled()  # copying never waits
        assert page.copy_project.isEnabled()
        work.gate.set()
        qtbot.waitUntil(lambda: not services.launch.busy)
        assert not page.launch_progress.isVisible()
        assert page.open_blender.isEnabled() and page.cards["kcl"].reveal_action.isEnabled()


def test_no_source_disables_blender_but_not_folders(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path, source=False) as (services, project, _work):
        page = page_for(qtbot, services, project)
        assert not page.open_blender.isEnabled()
        assert page.cards["kcl"].reveal_action.isEnabled()


def test_read_only_allows_folders_only(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path) as (services, project, _work):
        viewer = Project.open(project.root)
        services.project = viewer
        try:
            page = page_for(qtbot, services, viewer)
            assert not page.open_blender.isEnabled() and not page.edit_button.isEnabled()
            assert page.cards["kcl"].reveal_action.isEnabled()
        finally:
            services.project = project


def test_signals_request_only(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path) as (services, project, work):
        page = page_for(qtbot, services, project)
        blender, reveal = QSignalSpy(page.blender_requested), QSignalSpy(page.reveal_requested)
        page.open_blender.click()
        page.cards["kcl"].reveal_action.trigger()
        assert blender.count() == 1 and reveal.count() == 1 and reveal.at(0) == ["kcl"]
        assert not work.calls and not services.launch.busy  # the window decides, not the view


def test_results_have_their_own_notice(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path) as (services, project, work):
        page = page_for(qtbot, services, project)
        page.show_launching(None)
        assert page.launch_notice.text() == "Opening Blender…"
        services.launch.completed.emit(finished(project, None, receipt=work.blender_receipt))
        text = page.launch_notice.text()
        assert "process 123" in text and "cannot tell whether Blender finished" in text
        assert "Old Blender." in text  # adapter warnings are kept
        services.status.updated.emit(StatusResult(project.root, {}))
        assert page.launch_notice.text() == text  # a status check does not hide it
        assert page.launch_notice.isVisible()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ToolNotFound("Blender", "Set Blender's path on the Tools page."), "Tools page"),
        (OSError("disk vanished"), "Try again; if it keeps failing, restart"),
        (RuntimeError(), "Could not open"),
        (KeyboardInterrupt(), "interrupted. Try again"),
    ],
    ids=["typed", "ordinary", "empty", "interrupt"],
)
def test_failures_are_explained(tmp_path: Path, error: BaseException, expected: str) -> None:
    with Project.create(tmp_path / "P", "P") as project:
        assert expected in describe_launch(finished(project, None, error=error))
        folder = describe_launch(finished(project, "kcl", error=error))
        assert expected in folder
        assert ": ." not in folder  # an empty message still names the failure


def test_folder_receipt_claims_only_a_request(tmp_path: Path) -> None:
    with Project.create(tmp_path / "P", "P") as project:
        work = LaunchWork()
        text = describe_launch(finished(project, "kcl", receipt=work.folder_receipt))
        assert "Asked the system to open" in text and "If no window appears" in text


def test_stale_results_are_ignored(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path) as (services, project, work):
        page = page_for(qtbot, services, project)
        page.show_launching("kcl")
        other = LaunchResult(project, project.root / "x", project.manifest, "kcl")
        changed = replace(project.manifest)
        for stale in (
            other,
            LaunchResult(project, project.root, changed, "kcl", receipt=work.folder_receipt),
            "not a result",
        ):
            services.launch.completed.emit(stale)
            assert page.launch_notice.text() == "Opening the Collision folder…"


def test_a_result_for_a_project_no_longer_current_is_ignored(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path) as (services, project, work):
        page = page_for(qtbot, services, project)
        page.show_launching("kcl")
        services.project = None  # the displayed project is no longer the app's
        try:
            services.launch.completed.emit(finished(project, "kcl", receipt=work.folder_receipt))
            assert page.launch_notice.text() == "Opening the Collision folder…"
        finally:
            services.project = project
