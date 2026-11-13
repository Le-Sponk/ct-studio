"""P5-T06c2b2c2a: real watcher → native choices, refusal, recovery and stale joins."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

import pytest
from outside_failure_helpers import (
    PostWrite,
    actual_files,
    click_native,
    failure_flow,
    honest_note,
    protected,
)
from pytestqt.qtbot import QtBot
from reconcile_bootstrap_helpers import BootstrapPause
from reconcile_helpers import settled

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.gui.project_details import ProjectDetailsService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(45)]


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize("fault", ["creation", "refusal", "postwrite"])
def test_native_failure_keeps_original_error_and_actual_saved_state(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str, fault: str
) -> None:
    with failure_flow(qtbot, tmp_path) as (page, project, work, changed, capture):
        before, raw = project.manifest, project.manifest_path.read_bytes()
        error = RuntimeError("actual write finished")
        post = PostWrite(work, action, error)
        original_start = threading.Thread.start

        def no_creation(thread: threading.Thread) -> None:
            if thread.name == "ctstudio-launch":
                raise error
            original_start(thread)

        with post.installed(monkeypatch, page):
            if fault == "creation":
                monkeypatch.setattr(threading.Thread, "start", no_creation)
            post.refuse = fault == "refusal"
            click_native(qtbot, page, action)
            result = capture.one(qtbot)
        assert (
            result.project is project and result.manifest is before and result.edit_action == action
        )
        assert result.root == project.root and result.component_id == "kcl"
        assert result.recovery_error is None and result.receipt is None
        assert not project.read_only
        note = honest_note(page)
        if fault == "creation":
            assert isinstance(result.error, ProjectError) and result.error.__cause__ is error
            assert not work.calls and result.saved is None and result.recovery_root is None
            assert project.manifest is before and "Could not start" in note
        else:
            assert result.error is post.error and result.saved is not None
            assert result.saved.raw == project.manifest_path.read_bytes()
            assert result.recovery_root == project.root.resolve() == result.saved.root
            assert (
                project.manifest == result.saved.manifest == manifest_io.load(project.manifest_path)
            )
            assert "Saved project reloaded" in note and str(result.error) in note
            assert len(work.calls) == 1 and work.calls[0][2] == action
            assert work.calls[0][3] is not threading.main_thread()
        if fault == "refusal":
            assert isinstance(result.error, ProjectError) and "changed since" in str(result.error)
        if fault == "postwrite":
            assert result.error is error and post.memory_unchanged and result.saved is not None
            assert (
                result.saved.raw == post.raw and project.manifest.project.name == "Saved état 日本"
            )
            actual_files(project, action, changed)
        else:
            assert project.manifest_path.read_bytes() == (post.raw if fault == "refusal" else raw)
            assert (project.root / ".ctstudio/stage/course.kcl").read_bytes() == changed
            assert not list(project.root.glob(".ctstudio/backups/*"))
            assert not (project.root / "files/course.kcl").exists()


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize("primary_fault", [False, True])
def test_actual_write_then_unreadable_recovery_quarantines_without_losing_lock(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str, primary_fault: bool
) -> None:
    with failure_flow(qtbot, tmp_path) as (page, project, work, changed, capture):
        before, held = project.manifest, project.lock
        primary, recovery = RuntimeError("after actual write"), PermissionError("saved read denied")
        post = PostWrite(work, action, primary if primary_fault else None)
        reads: list[threading.Thread] = []

        def no_read(_self: ProjectDetailsService, _project: object) -> None:
            reads.append(threading.current_thread())
            assert post.written.is_set(), "read fault was injected before an actual write"
            raise recovery

        monkeypatch.setattr(ProjectDetailsService, "load", no_read)
        with post.installed(monkeypatch, page):
            click_native(qtbot, page, action)
            result = capture.one(qtbot)
        assert result.error is (primary if primary_fault else None)
        assert result.recovery_error is recovery and result.saved is None
        assert reads and all(thread is not threading.main_thread() for thread in reads)
        assert project.manifest is before and post.memory_unchanged and project.lock is held
        assert project.manifest_path.read_bytes() == post.raw
        actual_files(project, action, changed)
        note = honest_note(page)
        assert "reopen" in note and "saved read denied" in note
        if primary_fault:
            assert "after actual write" in note
        protected(qtbot, page, project)


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize("replace_memory", [False, True])
def test_postwrite_rebind_requires_publication_or_retained_lock_quarantine(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str, replace_memory: bool
) -> None:
    with failure_flow(qtbot, tmp_path) as (page, project, work, changed, capture):
        before, held = project.manifest, project.lock
        post = PostWrite(work, action)
        post.release.clear()
        with post.installed(monkeypatch, page):
            click_native(qtbot, page, action)
            assert settled(qtbot, post.written.is_set), "worker never reached its AFTER-write gate"
            assert page.services.launch.busy and not capture.results
            assert project.manifest is before and project.manifest_path.read_bytes() == post.raw
            actual_files(project, action, changed)
            if replace_memory:
                project.manifest = replace(
                    before, project=replace(before.project, name="New live edit")
                )
            live = project.manifest
            page.set_project(project, changed=True)
            assert page.services.launch.busy and project.lock is held
            assert not page.cards["kcl"].outside.activity.text()
            post.release.set()
            result = capture.one(qtbot)
        assert result.error is None and result.recovery_error is None and result.saved is not None
        assert result.manifest is before and result.saved.raw == post.raw
        assert result.saved.manifest == manifest_io.load(project.manifest_path)
        assert result.recovery_root == result.saved.root == project.root.resolve()
        assert project.lock is held and held is not None
        if replace_memory:
            assert project.manifest is live and project.read_only
            assert "reopen" in honest_note(page)
            protected(qtbot, page, project)
        else:
            assert project.manifest == result.saved.manifest and not project.read_only
            assert project.manifest.project.name == "Saved état 日本"
            assert page.cards["kcl"].outside.note.text() == page.launch_notice.text() != ""


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_native_acknowledgement_fault_still_joins_real_write_and_recovery(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    with failure_flow(qtbot, tmp_path) as (page, project, work, changed, capture):
        before, held = project.manifest, project.lock
        error = KeyboardInterrupt("native acknowledgement interrupted")
        pause = BootstrapPause(page.services.launch, error, "_set_ident")
        post = PostWrite(work, action)
        with post.installed(monkeypatch, page):
            try:
                with monkeypatch.context() as patch:
                    pause.install(patch)
                    click_native(qtbot, page, action)
                assert page.services.launch.busy and page.outside_edits.pending
                assert project.manifest is before and project.lock is held
                assert not capture.results and not page.cards["kcl"].outside.progress.isHidden()
            finally:
                pause.finish(work.gate)
            result = capture.one(qtbot)
        assert result.error is error and result.recovery_error is None and result.receipt is None
        assert result.manifest is before and result.saved is not None
        assert result.saved.raw == post.raw == project.manifest_path.read_bytes()
        assert project.manifest == result.saved.manifest == manifest_io.load(project.manifest_path)
        assert post.memory_unchanged and not project.read_only and project.lock is held
        actual_files(project, action, changed)
        assert "Saved project reloaded" in honest_note(page)
