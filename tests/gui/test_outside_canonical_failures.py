"""P5-T06c2b2c2b: real watcher/native writes before canonical recovery faults."""

from __future__ import annotations

import threading
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
from reconcile_helpers import EditWork

from ctstudio.core.components.assign import Assigned
from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.project_details import DetailsSnapshot, ProjectDetailsService
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(45)]
PREVIOUS = b"previous manual synthetic bytes"


class CanonicalFault:
    def __init__(self, root: Path, post: PostWrite, error: BaseException) -> None:
        self.root, self.post, self.error = root, post, error
        self.original_resolve = Path.resolve
        self.original_load = ProjectDetailsService.load
        self.resolutions: list[tuple[threading.Thread, bool]] = []
        self.reads: list[threading.Thread] = []
        self.action_errors: list[BaseException] = []

    def resolve(self, path: Path, strict: bool = False) -> Path:
        # Only this raw project root, only AFTER actual action + saved-byte writes.
        if path == self.root and self.post.written.is_set():
            self.resolutions.append((threading.current_thread(), self.post.written.is_set()))
            raise self.error
        return self.original_resolve(path, strict=strict)

    def load(self, loader: ProjectDetailsService, project: Project) -> DetailsSnapshot:
        self.reads.append(threading.current_thread())
        return self.original_load(loader, project)

    def action(self, project: Project, part: str) -> Assigned | Path:
        try:
            return self.post.call(project, part)
        except BaseException as exc:
            self.action_errors.append(exc)
            raise

    def install(self, patch: pytest.MonkeyPatch, page: Dashboard) -> None:
        def resolve(path: Path, strict: bool = False) -> Path:
            return self.resolve(path, strict)

        def load(loader: ProjectDetailsService, project: Project) -> DetailsSnapshot:
            return self.load(loader, project)

        patch.setattr(Path, "resolve", resolve)
        patch.setattr(ProjectDetailsService, "load", load)
        patch.setattr(page.services.launch, "_" + self.post.action, self.action)


def native_attempt(
    qtbot: QtBot,
    page: Dashboard,
    work: EditWork,
    action: str,
    startup: BaseException | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if startup is None:
        click_native(qtbot, page, action)
        return
    pause = BootstrapPause(page.services.launch, startup, "_set_ident")
    try:
        with monkeypatch.context() as patch:
            pause.install(patch)
            click_native(qtbot, page, action)
        assert page.services.launch.busy and page.outside_edits.pending
    finally:
        pause.finish(work.gate)


def check_errors(
    result: LaunchResult,
    fault: CanonicalFault,
    startup: BaseException | None,
    primary: BaseException | None,
) -> None:
    assert result.error is (startup if startup is not None else primary)
    assert result.recovery_error is fault.error
    assert fault.error is not primary and fault.error is not startup
    assert fault.action_errors == ([] if primary is None else [primary])
    if primary is not None:
        assert fault.action_errors[0] is primary  # native-start error must not cancel the action
    assert result.saved is None and result.recovery_root is None
    assert (result.receipt is not None) == (primary is None and startup is None)


def disk_bytes(project: Project) -> dict[Path, bytes]:
    return {
        path.relative_to(project.root): path.read_bytes()
        for path in project.root.rglob("*")
        if path.is_file() and path != project.root / ".ctstudio/lock"
    }


def check_files(project: Project, post: PostWrite, changed: bytes) -> None:
    assert post.written.is_set() and post.memory_unchanged
    assert project.manifest_path.read_bytes() == post.raw
    actual_files(project, post.action, changed)
    manual = project.root / "files/course.kcl"
    if post.action == "lock":
        assert (project.root / ".ctstudio/stage/course.kcl").read_bytes() == changed
        backups = list(project.root.glob(".ctstudio/backups/*/files/course.kcl"))
        assert len(backups) == 1 and backups[0].read_bytes() == PREVIOUS
    else:
        assert manual.read_bytes() == PREVIOUS


@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize("error_type", [PermissionError, RuntimeError, KeyboardInterrupt])
@pytest.mark.parametrize("primary_fault", ["none", "action", "bootstrap", "both"])
def test_postwrite_canonical_failure_keeps_errors_bytes_and_real_ownership(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: bool,
    action: str,
    error_type: type[BaseException],
    primary_fault: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    folder = Path("relative é") if relative else tmp_path / "absolute é"
    with failure_flow(qtbot, folder) as (page, project, work, changed, capture):
        before, held, root = project.manifest, project.lock, project.root
        assert root.is_absolute() is not relative
        (root / "files/course.kcl").write_bytes(PREVIOUS)
        primary = (
            RuntimeError("postwrite action failed") if primary_fault in ("action", "both") else None
        )
        startup = (
            KeyboardInterrupt("native acknowledgement interrupted")
            if primary_fault in ("bootstrap", "both")
            else None
        )
        recovery = error_type("canonical resolution failed")
        post = PostWrite(work, action, primary)
        fault = CanonicalFault(root, post, recovery)
        with post.installed(monkeypatch, page):
            with monkeypatch.context() as patch:
                fault.install(patch, page)
                native_attempt(qtbot, page, work, action, startup, monkeypatch)
                result = capture.one(qtbot)
        assert len(work.calls) == 1 and work.calls[0][:3] == (project, "kcl", action)
        check_errors(result, fault, startup, primary)
        assert fault.resolutions == [(work.calls[0][3], True)]
        assert fault.resolutions[0][0] is not threading.main_thread()
        assert fault.reads == [], "saved reader ran after canonicalization failed"
        assert result.project is project and result.manifest is before
        assert result.root == root and result.component_id == "kcl" and result.edit_action == action
        assert project.manifest is before and project.root == root and project.lock is held
        check_files(project, post, changed)
        note = honest_note(page)
        assert "reopen" in note
        assert (
            "KeyboardInterrupt" if isinstance(recovery, KeyboardInterrupt) else str(recovery)
        ) in note
        if startup is not None:
            assert note.count("KeyboardInterrupt") == 1 + isinstance(recovery, KeyboardInterrupt)
        elif primary is not None:
            assert str(primary) in note
        saved_bytes = disk_bytes(project)
        protected(qtbot, page, project)
        assert disk_bytes(project) == saved_bytes, "refusal/reopen changed saved data or backups"
        check_files(project, post, changed)
