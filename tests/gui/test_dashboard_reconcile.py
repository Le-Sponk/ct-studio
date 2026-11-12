"""Joined outside-edit results publish saved state, not a successful-looking receipt."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# Tests inspect the existing build eligibility predicate, never production private-thread APIs.
import threading
from collections.abc import Collection
from dataclasses import replace
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from reconcile_bootstrap_helpers import BootstrapPause
from reconcile_helpers import outcome, owned, settled

from ctstudio.core.components.edited import discard_edit, lock_as_manual
from ctstudio.core.components.status import ComponentStatus, ProjectLike, State
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.project_details import DetailsSnapshot, ProjectDetailsService
from ctstudio.gui.status_service import StatusResult
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize("relative", [False, True])
def test_real_joined_result_rebinds_cards_and_checks_saved_state(
    qtbot: QtBot,
    tmp_path: Path,
    action: str,
    relative: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    folder = Path("relative é") if relative else tmp_path
    with owned(folder) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        original = project.manifest
        if action == "lock":
            previous = project.root / "files/course.kcl"
            previous.write_bytes(b"previous synthetic copy")
        assert services.start_reconcile("kcl", action)
        assert project.manifest is original, "unjoined work was published"
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert project.manifest is not original, "saved state was never published"
        assert project.manifest == manifest_io.load(project.manifest_path)
        card = page.cards["kcl"]
        mode = "manual" if action == "lock" else "auto"
        assert card.mode_label.text() == f"Mode: {mode}"
        assert not project.read_only and page.refresh_button.isEnabled()
        assert "folder" not in page.launch_notice.text(), "reconcile was mistaken for reveal"
        assert ("manual" if action == "lock" else "backed up") in page.launch_notice.text()
        assert "Could not" not in page.launch_notice.text()
        location = "files/course.kcl" if action == "lock" else ".ctstudio"
        assert location in page.launch_notice.text()
        if action == "lock":
            assert "previous copy was backed up" in page.launch_notice.text()
            backups = project.root.glob(".ctstudio/backups/*/files/course.kcl")
            assert any(p.read_bytes() == b"previous synthetic copy" for p in backups)


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize(
    "error",
    [
        ProjectError("Action refused.", hint="Check the file."),
        RuntimeError("after writing"),
        KeyboardInterrupt(),
        RuntimeError(),
        PermissionError(13, "Permission denied", "C:/elsewhere"),
        OSError(13, ""),
        OSError("disk full"),
    ],
)
def test_action_faults_recover_disk_without_claiming_success(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    error: BaseException,
) -> None:
    with owned(tmp_path) as (services, project, _work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        before = project.manifest

        def fail(given: object, part: str) -> None:
            if not isinstance(error, ProjectError):
                (lock_as_manual if action == "lock" else discard_edit)(project, part)
            raise error

        monkeypatch.setattr(services.launch, "_lock" if action == "lock" else "_discard", fail)
        assert services.start_reconcile("kcl", action)
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert project.manifest is not before
        assert project.manifest == manifest_io.load(project.manifest_path)
        assert not project.read_only
        text = page.launch_notice.text()
        assert "Saved project reloaded" in text
        assert "Check this card" in text
        assert "Locked as manual" not in text and "was backed up" not in text
        if isinstance(error, ProjectError):
            assert str(error) in text
        if isinstance(error, OSError) and error.errno is None:
            assert str(error) in text


@pytest.mark.parametrize("problem", ["read", "stale", "both"])
def test_unsafe_publication_retains_lock_but_refuses_writes(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        if problem in ("read", "both"):

            def unreadable(_self: object, _project: object) -> None:
                raise KeyboardInterrupt("saved read failed")

            monkeypatch.setattr(ProjectDetailsService, "load", unreadable)
        if problem == "both":
            work.error = ProjectError("Action failed.", hint="Check the file.")
        held = project.lock
        assert services.start_reconcile("kcl", "lock")
        if problem == "stale":
            project.manifest = replace(
                project.manifest, project=replace(project.manifest.project, name="New live edit")
            )
        live = project.manifest
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert project.manifest is live, "unsafe recovery overwrote live memory"
        assert project.lock is held and held is not None, "write ownership was dropped"
        assert project.read_only, "unsafe saved state still permits writes"
        assert "reopen" in page.launch_notice.text()
        if problem == "both":
            assert "Action failed" in page.launch_notice.text()
            assert "KeyboardInterrupt" in page.launch_notice.text()

        assert not page.edit_button.isEnabled() and not page.builds._eligible()
        error = outcome(lambda: project.save(live))
        assert isinstance(error, ProjectError), "unsafe-state save was not refused"
        assert "read-only" in str(error)
        with pytest.raises(ProjectError, match="read-only"):
            services.start_reconcile("kcl", "lock")
        with Project.open(project.root) as contender:
            assert contender.read_only, "recovery failure released the real write lock"
        project.close()
        with Project.open(project.root) as reopened:
            assert not reopened.read_only
            assert reopened.manifest == manifest_io.load(project.manifest_path)


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_false_after_native_dispatch_still_publishes_joined_recovery(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        before = project.manifest
        pause = BootstrapPause(services.launch, KeyboardInterrupt(), "_set_ident")
        try:
            with monkeypatch.context() as patch:
                pause.install(patch)
                assert outcome(lambda: services.start_reconcile("kcl", action)) is False
            assert services.launch.busy and project.manifest is before
        finally:
            pause.finish(work.gate)
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert project.manifest is not before
        assert project.manifest == manifest_io.load(project.manifest_path)
        assert "Saved project reloaded" in page.launch_notice.text()
        assert not project.read_only


@pytest.mark.parametrize(
    "guard", ["project", "root", "current", "snapshot_root", "closed", "captured_copy"]
)
def test_completion_origin_and_ownership_guards(
    qtbot: QtBot,
    tmp_path: Path,
    guard: str,
) -> None:
    with owned(tmp_path) as (services, project, _work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        before = project.manifest
        changed = replace(before, project=replace(before.project, name="Should not publish"))
        saved = DetailsSnapshot(project.root, changed, b"stand-in; never read on UI")
        result = LaunchResult(
            project,
            project.root,
            before,
            "kcl",
            edit_action="lock",
            saved=saved,
            recovery_root=project.root.resolve(),
        )
        if guard == "project":
            result = replace(result, project=replace(project))
        elif guard == "root":
            result = replace(result, root=tmp_path / "elsewhere")
        elif guard == "current":
            services.project = replace(project)
        elif guard == "snapshot_root":
            result = replace(result, saved=replace(saved, root=tmp_path / "elsewhere"))
        elif guard == "captured_copy":
            result = replace(result, manifest=replace(before))
        else:
            project.close()
        services.launch.completed.emit(result)
        assert result.project.manifest is before, "the foreign result owner was modified"
        assert project.manifest is before, "unowned or foreign state was published"
        if guard in ("project", "root", "current"):
            assert not page.launch_notice.text(), "foreign completion changed this dashboard"
        if guard == "snapshot_root":
            assert project.read_only and project.lock is not None


def test_failure_before_dispatch_does_not_quarantine_a_safe_project(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with owned(tmp_path) as (services, project, _work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        original_start = threading.Thread.start

        def refuse(thread: threading.Thread) -> None:
            if thread.name == "ctstudio-launch":
                raise RuntimeError("could not create thread")
            original_start(thread)

        monkeypatch.setattr(threading.Thread, "start", refuse)
        assert services.start_reconcile("kcl", "lock") is False
        assert not services.launch.busy
        assert not project.read_only, "a request that never ran needs no disk recovery"
        assert "Could not start" in page.launch_notice.text()


def test_publication_uses_real_saved_state_not_receipt_and_has_no_ui_read(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        original_load, original_read = ProjectDetailsService.load, Path.read_bytes
        original_resolve = Path.resolve
        observed: list[bool] = []
        reads: list[threading.Thread] = []
        resolutions: list[threading.Thread] = []

        def changed_load(loader: ProjectDetailsService, given: Project) -> DetailsSnapshot:
            assert threading.current_thread() is not threading.main_thread()
            disk = manifest_io.load(given.manifest_path)
            changed = replace(disk, project=replace(disk.project, name="Saved <&> état"))
            manifest_io.save(changed, given.manifest_path)
            return original_load(loader, given)

        def read(path: Path) -> bytes:
            reads.append(threading.current_thread())
            return original_read(path)

        def resolve(path: Path, strict: bool = False) -> Path:
            if path == project.root:
                resolutions.append(threading.current_thread())
            return original_resolve(path, strict=strict)

        def joined(_result: object) -> None:
            observed.append(
                threading.current_thread() is threading.main_thread() and not services.launch.busy
            )

        services.launch.completed.connect(joined)
        with monkeypatch.context() as patch:
            patch.setattr(ProjectDetailsService, "load", changed_load)
            patch.setattr(Path, "read_bytes", read)
            patch.setattr(Path, "resolve", resolve)
            assert services.start_reconcile("kcl", "lock")
            work.gate.set()
            assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert observed == [True]
        assert reads and all(t is not threading.main_thread() for t in reads), "UI read disk"
        assert resolutions and all(t is not threading.main_thread() for t in resolutions)
        assert project.manifest == manifest_io.load(project.manifest_path)
        assert page.name_label.text() == "Saved <&> état", "receipt replaced the saved snapshot"
        text = page.launch_notice.text()
        page.recheck()
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        assert page.launch_notice.text() == text, "status delivery erased the action outcome"


def test_a_pre_save_status_result_cannot_publish_after_recovery(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        entered, release = threading.Event(), threading.Event()
        updates: list[object] = []
        services.status.updated.connect(updates.append)

        def evaluate(given: ProjectLike, _tools: Collection[str]) -> dict[str, ComponentStatus]:
            if given.manifest.components.kcl.mode == "auto":
                entered.set()
                assert release.wait(10), "old status worker was not released"
                return {"kcl": ComponentStatus(State.ERROR, ("OLD PRE-SAVE STATUS",))}
            return {"kcl": ComponentStatus(State.MANUAL, ("Fresh saved state",))}

        monkeypatch.setattr(services.status, "_evaluate", evaluate)
        try:
            assert services.start_reconcile("kcl", "lock")
            services.status.request(project)
            assert settled(qtbot, entered.is_set), "the old snapshot was never evaluated"
            work.gate.set()
            assert settled(qtbot, lambda: not services.launch.busy)
            assert page.cards["kcl"].mode_label.text() == "Mode: manual"
            release.set()
            assert settled(qtbot, lambda: not page.busy and not services.status.busy)
            reasons = [
                reason
                for update in updates
                if isinstance(update, StatusResult)
                for status in update.statuses.values()
                for reason in status.reasons
            ]
            assert "OLD PRE-SAVE STATUS" not in reasons, "old check published after recovery"
            assert "Fresh saved state" in reasons, "saved state was never checked"
        finally:
            release.set()


def test_foreign_loader_root_cannot_authorize_itself(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        before = project.manifest
        original = ProjectDetailsService.load

        def foreign(loader: ProjectDetailsService, given: Project) -> DetailsSnapshot:
            loaded = original(loader, given)
            return replace(loaded, root=tmp_path / "foreign snapshot")

        monkeypatch.setattr(ProjectDetailsService, "load", foreign)
        assert services.start_reconcile("kcl", "lock")
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert project.manifest is before, "snapshot authorized its own foreign provenance"
        assert project.read_only and project.lock is not None
        assert "different folder" in page.launch_notice.text()
