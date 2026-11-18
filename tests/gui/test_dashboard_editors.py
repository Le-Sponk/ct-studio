"""P5-T07d3: dashboard editor requests, kept choices and window ownership (no menus: T07e)."""

# pyright: reportPrivateUsage=false
# (the window test opens a project and navigates the way its existing launch tests do)

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from editor_owner_helpers import BUILTIN, CUSTOM, DOCUMENT_NAME, EditorWork, outcome
from editor_request_helpers import dashboard_for, editor_services, owned_editors, settled
from launch_controller_helpers import LaunchWork, writable_project
from pytestqt.qtbot import QtBot

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def test_prepare_then_open_shows_launch_only_text_never_blender(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        page = dashboard_for(qtbot, services, project)
        page.editors.prepare(document)
        assert work.entered.wait(5)
        assert page.launch_notice.text() == "Finding editors…"
        assert not page.refresh_button.isEnabled(), "an editor request holds the dashboard"
        work.gate.set()
        assert settled(qtbot, lambda: page.editors.choices is not None)
        assert page.editors.choices is work.snapshots[-1]
        ready_text = "Editor choices for course 日本.brres are ready (2 of 2 found)."
        assert page.launch_notice.text() == ready_text
        page.editors.open(CUSTOM)
        assert settled(qtbot, lambda: not services.launch.busy and len(work.calls) == 2)
        text = page.launch_notice.text()
        assert text.startswith("custom was started (process 321) with course 日本.brres.")
        assert "cannot tell whether custom finished opening" in text and "Warned." in text
        assert "Blender" not in text
        assert [call[3] for call in work.calls] == [None, CUSTOM]
        assert page.refresh_button.isEnabled()


def test_choices_retire_when_the_project_changes_and_stale_opens_start_nothing(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        work.gate.set()
        page = dashboard_for(qtbot, services, project)
        page.editors.prepare(document)
        assert settled(qtbot, lambda: page.editors.choices is not None)
        project.manifest = replace(project.manifest)  # e.g. saved project details
        assert page.editors.choices is None, "choices outlived the project they describe"
        page.editors.open(BUILTIN)
        page.editors.open(EditorChoice("custom", "never-offered"))
        assert [call[0] for call in work.calls] == ["prepare"]
        assert not services.launch.busy
        page.editors.prepare(document)
        assert settled(qtbot, lambda: page.editors.choices is not None)
        page.set_project(project, changed=True)  # the dashboard rebinds: old choices retire
        assert page.editors.choices is None


def test_an_unrelated_or_stale_editor_result_changes_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        work.gate.set()
        page = dashboard_for(qtbot, services, project)
        page.editors.prepare(document)
        assert settled(qtbot, lambda: page.editors.choices is not None)
        before = page.launch_notice.text()
        snapshot = work.snapshots[-1]
        for stale in (
            LaunchResult(project, project.root, replace(project.manifest), None, snapshot),
            LaunchResult(project, project.root / "x", project.manifest, None, snapshot),
        ):
            services.launch.completed.emit(replace(stale, editor_action="prepare"))
        assert page.launch_notice.text() == before
        assert page.editors.choices is snapshot


def test_a_new_preparation_retires_old_choices_and_ignores_foreign_results(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        work.gate.set()
        page = dashboard_for(qtbot, services, project)
        page.editors.prepare(document)
        assert settled(qtbot, lambda: page.editors.choices is not None)
        ready = page.launch_notice.text()
        unoffered = EditorChoice("custom", "never-offered")  # current choices, but not offered
        raised = outcome(lambda: page.editors.open(unoffered))
        assert raised is None, f"an unoffered choice raised {raised!r}"
        assert page.launch_notice.text() == ready, "an unoffered choice was requested"
        assert [call[0] for call in work.calls] == ["prepare"]
        work.gate.clear()
        work.entered.clear()
        page.editors.prepare(document)
        assert work.entered.wait(5)
        assert page.editors.choices is None, "old choices stayed usable during a new preparation"
        old = work.snapshots[-1]
        foreign = LaunchResult(project, project.root, replace(project.manifest), None, old)
        services.launch.completed.emit(replace(foreign, editor_action="prepare"))
        assert page.launch_notice.text() == "Finding editors…", "a foreign result was shown"
        assert page.editors.pending and page.editors.choices is None
        work.gate.set()
        assert settled(qtbot, lambda: page.editors.choices is not None)
        assert page.editors.choices is work.snapshots[-1] and work.snapshots[-1] is not old


def test_read_only_dashboards_may_prepare_but_never_open(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        work.gate.set()
        viewer = Project.open(project.root)
        services.project = viewer
        try:
            page = dashboard_for(qtbot, services, viewer)
            page.editors.prepare(document)
            assert settled(qtbot, lambda: page.editors.choices is not None)
            page.editors.open(BUILTIN)  # a direct call bypasses any disabled control
            assert [call[0] for call in work.calls] == ["prepare"]
            assert not services.launch.busy
            assert page.launch_notice.text().startswith("Editor choices for"), "asked anyway"
        finally:
            services.project = project
            viewer.close()


def test_a_service_refusal_is_shown_and_frees_the_dashboard(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        page = dashboard_for(qtbot, services, project)

        def refuse(_document: Path) -> bool:
            raise ProjectError("Refused for the test.", hint="Do something else.")

        monkeypatch.setattr(services, "start_prepare_editors", refuse)
        page.editors.prepare(document)
        assert page.launch_notice.text() == "Refused for the test.\nNext: Do something else."
        assert not page.editors.pending and page.refresh_button.isEnabled()
        assert not work.calls


def test_window_navigation_and_close_wait_for_an_editor_request(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ctstudio.gui.main_window as main_window

    monkeypatch.setattr(main_window, "_SHUTDOWN_WAIT", 0.0)
    other = LaunchWork()
    other.gate.set()
    work = EditorWork()
    view = MainWindow(editor_services(other, work))
    qtbot.addWidget(view)
    view.show()
    assert settled(qtbot, lambda: not view.welcome.busy)
    project = writable_project(tmp_path)
    document = project.root / DOCUMENT_NAME
    document.write_bytes(b"synthetic only")
    view._opened(project)
    assert settled(qtbot, lambda: not view.dashboard.busy)
    view.dashboard.editors.prepare(document)
    assert work.entered.wait(5)
    assert not view.home_action.isEnabled() and not view.open_project_action.isEnabled()
    view._go_home()
    assert view.pages.currentIndex() == 1
    assert view.close() is False, "closed while the editor worker owned the project"
    assert services_project(view) is project and not project.read_only
    assert "still stopping" in view.dashboard.launch_notice.text()
    work.gate.set()
    assert settled(qtbot, lambda: not view.services.launch.busy)
    assert "Editor choices for" in view.dashboard.launch_notice.text()
    view.close()
    assert project.read_only, "closing after the editor request did not release the lock"


def services_project(view: MainWindow) -> Project | None:
    return view.services.project
