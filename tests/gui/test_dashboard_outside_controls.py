"""Outside-edit buttons route through the existing joined owner and target presentation."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot
from reconcile_bootstrap_helpers import BootstrapPause
from reconcile_helpers import outcome, owned, settled

from ctstudio.core.components.assign import Assigned
from ctstudio.core.components.status import ComponentStatus, State
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.gui.launch_controller import LaunchController, LaunchResult
from ctstudio.gui.project_details import ProjectDetailsService
from ctstudio.gui.status_service import StatusResult
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_assignment_rebind_allows_later_outside_request(qtbot: QtBot, tmp_path: Path) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        before = project.manifest
        saved = replace(before, project=replace(before.project, name="Assigned another part"))
        services.launch.completed.emit(
            LaunchResult(
                project,
                project.root,
                before,
                "course_model",
                receipt=Assigned(saved, "files/course_model.brres", None, None),
                source=project.root / "supplied.brres",
            )
        )
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        assert project.manifest is saved and page.cards["kcl"].can_reconcile()
        # A service refusal proves the new context reaches dispatch without touching disk.
        work.error = ProjectError("Fixture: saved input differs.", hint="Refresh.")
        page.cards["kcl"].outside.lock_button.click()
        assert services.launch.busy, "assignment left outside-edit eligibility bound to old state"
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)


def busy_owner(_self: object) -> bool:
    return True


def approve(_parent: QWidget) -> bool:
    return True


def cancel(_parent: QWidget) -> bool:
    return False


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_buttons_route_real_action_and_keep_target_outcome(
    qtbot: QtBot, tmp_path: Path, action: str
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        banner = page.cards["kcl"].outside
        banner.confirm = approve
        assert banner.lock_button.isEnabled(), "fixture did not deliver edited status"
        button = banner.lock_button if action == "lock" else banner.discard_button
        button.click()
        assert services.launch.busy, "button emitted without starting the existing owner"
        assert not banner.progress.isHidden(), "target has no working presentation"
        assert banner.activity.text() and not banner.note.text()
        assert not banner.lock_button.isEnabled() and not banner.discard_button.isEnabled()
        for part, card in page.cards.items():
            if part != "kcl":
                assert not card.outside.activity.text() and not card.outside.note.text()
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert len(work.calls) == 1 and work.calls[0][1:3] == ("kcl", action)
        assert work.calls[0][3] is not threading.main_thread()
        assert banner.progress.isHidden() and not banner.activity.text()
        assert banner.note.text() == page.launch_notice.text() != ""
        assert banner.note.toolTip() == banner.note.accessibleDescription() == banner.note.text()
        assert ("Locked as manual" if action == "lock" else "was backed up") in banner.note.text()
        note = banner.note.text()
        page.refresh()
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        assert banner.note.text() == note, "routine status update erased the outcome"


def test_cancel_changes_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        banner = page.cards["kcl"].outside
        banner.confirm = cancel
        before = project.manifest
        banner.discard_button.click()
        assert not services.launch.busy and not work.calls
        assert project.manifest is before and banner.progress.isHidden()
        assert not banner.note.text()


@pytest.mark.parametrize(
    "gate",
    [
        "none",
        "foreign",
        "readonly",
        "checking",
        "status",
        "build",
        "edit",
        "launch",
        "unchecked",
        "ready",
        "manual",
        "part",
        "action",
    ],
)
def test_request_rechecks_explicit_state_before_service(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gate: str
) -> None:
    with owned(tmp_path) as (services, project, _work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        calls: list[tuple[str, str]] = []

        def record(part: str, action: str) -> bool:
            calls.append((part, action))
            return False

        monkeypatch.setattr(services, "start_reconcile", record)
        if gate == "none":
            services.project = None
        elif gate == "foreign":
            services.project = replace(project)
        elif gate == "readonly":
            project.read_only_reason = "Unsafe recovery"
        elif gate == "checking":
            page.refresh()
        elif gate == "status":
            services.status.request(project)  # independent producer: page.busy is still False
        elif gate == "build":
            monkeypatch.setattr(type(services.build), "running", property(busy_owner))
        elif gate == "edit":
            services.editing = True
        elif gate == "launch":
            monkeypatch.setattr(LaunchController, "busy", property(busy_owner))
        elif gate in ("unchecked", "ready"):
            page.cards["kcl"].show_status(
                None if gate == "unchecked" else ComponentStatus(State.READY)
            )
        elif gate == "manual":
            project.manifest = replace(
                project.manifest,
                components=replace(
                    project.manifest.components,
                    kcl=replace(project.manifest.components.kcl, mode="manual"),
                ),
            )
            page.cards["kcl"].bind(project)
        result = outcome(
            lambda: page.outside_edits.request(
                "unknown" if gate == "part" else "kcl", "invalid" if gate == "action" else "lock"
            )
        )
        pending = page.outside_edits.pending
        services.project = project
        monkeypatch.undo()  # restore ownership before any assertion can interrupt cleanup
        assert result is None, "an ineligible request must be refused without raising"
        assert not calls, f"{gate} reached the service"
        assert not pending


def test_ancestor_disablement_is_not_cached_eligibility(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned(tmp_path) as (services, project, _work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        calls: list[tuple[str, str]] = []

        def refuse(part: str, action: str) -> bool:
            calls.append((part, action))
            return False

        monkeypatch.setattr(services, "start_reconcile", refuse)
        page.setEnabled(False)
        page.outside_edits.request("kcl", "lock")
        assert calls == [("kcl", "lock")], "eligibility read a widget's effective enabled state"
        assert not page.outside_edits.pending
        banner = page.cards["kcl"].outside
        assert banner.progress.isHidden() and "did not start" in banner.note.text()


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize("fault", ["typed", "read", "start", "native"])
def test_target_fault_outcomes_and_uncertain_dispatch(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str, fault: str
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        banner = page.cards["kcl"].outside
        banner.confirm = approve
        error = ProjectError("Refused safely.", hint="Try Refresh.")

        def refuse(_part: str, _action: str) -> bool:
            raise error

        def no_read(_self: object, _project: object) -> None:
            raise PermissionError("saved state unavailable")

        def no_start(_self: threading.Thread) -> None:
            raise RuntimeError("cannot start")

        button = banner.lock_button if action == "lock" else banner.discard_button
        if fault == "typed":
            monkeypatch.setattr(services, "start_reconcile", refuse)
        elif fault == "read":
            monkeypatch.setattr(ProjectDetailsService, "load", no_read)
        pause = BootstrapPause(services.launch, KeyboardInterrupt(), "_set_ident")
        with monkeypatch.context() as patch:
            if fault == "start":
                patch.setattr(threading.Thread, "start", no_start)
            elif fault == "native":
                pause.install(patch)
            assert outcome(button.click) is None
        if fault in ("read", "native"):
            assert services.launch.busy and not banner.progress.isHidden()
            assert page.outside_edits.pending
        if fault == "native":
            pause.finish(work.gate)
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert not page.outside_edits.pending and banner.progress.isHidden()
        assert banner.note.text() and not banner.activity.text()
        if fault == "typed":
            assert banner.note.text() == str(error)
        else:
            assert banner.note.text() == page.launch_notice.text()
        assert project.read_only is (fault == "read")
        for part, card in page.cards.items():
            if part != "kcl":
                assert not card.outside.note.text() and not card.outside.activity.text()


@pytest.mark.parametrize("transition", ["rebind", "edit", "status", "nested", "root", "manifest"])
def test_modal_approval_cannot_outlive_eligibility_or_reenter(
    qtbot: QtBot, tmp_path: Path, transition: str
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        banner = page.cards["kcl"].outside

        def confirm(_parent: QWidget) -> bool:
            if transition == "rebind":
                page.set_project(project, changed=True)
            elif transition == "edit":
                services.editing = True
            elif transition == "status":
                services.status.request(project)
            elif transition == "root":
                project.root = project.root / "different"
            elif transition == "manifest":
                project.manifest = replace(project.manifest)
            else:
                banner.lock_button.click()
                banner.discard_button.click()
            return True

        banner.confirm = confirm
        original_root = project.root
        banner.discard_button.click()
        project.root = original_root
        if transition == "nested":
            assert services.launch.busy
            work.gate.set()
        else:
            assert not services.launch.busy and not work.calls
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert len(work.calls) == int(transition == "nested")


def test_rebind_drops_pending_presentation_without_releasing_worker(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        banner = page.cards["kcl"].outside
        before, held = project.manifest, project.lock
        banner.lock_button.click()
        assert services.launch.busy and page.outside_edits.pending
        page.set_project(project, changed=True)
        assert not page.outside_edits.pending and services.launch.busy
        assert project.lock is held and held is not None
        assert not banner.activity.text() and not banner.note.text()
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert project.manifest is not before
        assert project.manifest == manifest_io.load(project.manifest_path)
        assert project.manifest.components.kcl.mode == "manual" and not project.read_only
        assert project.lock is held
        assert "Locked as manual" in banner.note.text() == page.launch_notice.text()


def test_pending_context_blocks_duplicates_and_ignores_foreign_action(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        banner = page.cards["kcl"].outside
        banner.lock_button.click()
        page.outside_edits.request("kcl", "discard")
        services.launch.completed.emit(
            LaunchResult(project, project.root, project.manifest, "kcl", edit_action="discard")
        )
        assert page.outside_edits.pending and not banner.progress.isHidden()
        services.status.updated.emit(
            StatusResult(project.root, {"kcl": ComponentStatus(State.READY)})
        )
        assert banner.activity.text() and not banner.progress.isHidden()
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert len(work.calls) == 1 and work.calls[0][2] == "lock"
        assert banner.note.text() == page.launch_notice.text() != ""
