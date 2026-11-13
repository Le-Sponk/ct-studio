"""P5-T06c2b2c2a: real watcher/native choices and actual post-write faults."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# Observe watcher registration and inject at the existing joined action boundary only.
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from outside_flow_helpers import answer_discard, change_stage, live_dashboard
from PySide6.QtCore import QTimer
from pytestqt.qtbot import QtBot
from reconcile_helpers import EditWork, outcome, settled

from ctstudio.core.components.assign import Assigned
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.core.project.watch import ProjectWatcher
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.views.dashboard import Dashboard


class Completion:
    def __init__(self, page: Dashboard) -> None:
        self.page = page
        self.results: list[LaunchResult] = []
        self.joined: list[bool] = []
        page.services.launch.completed.connect(self.record)

    def record(self, payload: object) -> None:
        assert isinstance(payload, LaunchResult), "completion lost its typed result"
        self.results.append(payload)
        self.joined.append(
            threading.current_thread() is threading.main_thread()
            and not self.page.services.launch.busy
            and not any(t.name == "ctstudio-launch" for t in threading.enumerate())
        )

    def one(self, qtbot: QtBot) -> LaunchResult:
        assert settled(qtbot, lambda: len(self.results) == 1), "missing joined completion"
        assert self.joined == [True], "result arrived before join or outside the UI thread"
        assert settled(qtbot, lambda: idle(self.page)), "dashboard did not return idle"
        return self.results[0]


def idle(page: Dashboard) -> bool:
    return not page.busy and not page.services.status.busy and not page.services.launch.busy


@contextmanager
def failure_flow(
    qtbot: QtBot, folder: Path
) -> Generator[tuple[Dashboard, Project, EditWork, bytes, Completion], None, None]:
    with live_dashboard(qtbot, folder) as (page, project, work, _area):
        banner = page.cards["kcl"].outside
        assert page.cards["kcl"].status_label.text() == "ready" and banner.isHidden()
        watcher = page.services.watcher._watcher
        assert isinstance(watcher, ProjectWatcher) and watcher.wait_ready(10)
        begun = time.monotonic()
        changed = change_stage(project)
        assert settled(qtbot, lambda: idle(page) and banner.lock_button.isEnabled())
        assert time.monotonic() - begun < 2.0, "watcher-to-banner exceeded two seconds"
        assert not banner.isHidden() and "outside CT Studio" in banner.title.text()
        yield page, project, work, changed, Completion(page)


def click_native(qtbot: QtBot, page: Dashboard, action: str) -> None:
    banner = page.cards["kcl"].outside
    # A real watcher can queue a second status request; wait for the actual idle guards.
    assert settled(qtbot, lambda: idle(page) and banner.lock_button.isEnabled())
    seen: list[bool] = []
    if action == "discard":
        QTimer.singleShot(0, lambda: answer_discard(action, seen))
        banner.discard_button.click()
        assert seen == [True], "native destructive confirmation was bypassed"
    else:
        banner.lock_button.click()


class PostWrite:
    def __init__(self, work: EditWork, action: str, error: BaseException | None = None) -> None:
        self.work, self.action, self.error = work, action, error
        self.written, self.release = threading.Event(), threading.Event()
        self.release.set()
        self.raw = b""
        self.memory_unchanged = False
        self.refuse = False

    def call(self, project: Project, part: str) -> Assigned | Path:
        before = project.manifest
        if self.refuse:
            manifest_io.save(
                replace(before, project=replace(before.project, name="Outside edit")),
                project.manifest_path,
            )
            self.raw = project.manifest_path.read_bytes()
        try:
            receipt = (self.work.lock if self.action == "lock" else self.work.discard)(
                project, part
            )
        except ProjectError as exc:
            self.error = exc  # retain the actual core refusal, not a synthetic exception
            raise
        # A genuinely different saved manifest defeats recovery from captured memory/receipt.
        saved = manifest_io.load(project.manifest_path)
        manifest_io.save(
            replace(saved, project=replace(saved.project, name="Saved état 日本")),
            project.manifest_path,
        )
        self.raw = project.manifest_path.read_bytes() + "\n# exact saved café 日本\n".encode()
        project.manifest_path.write_bytes(self.raw)
        self.memory_unchanged = project.manifest is before
        self.written.set()
        assert self.release.wait(10), "post-write worker was not released"
        if self.error is not None:
            raise self.error
        return receipt

    @contextmanager
    def installed(self, patch: pytest.MonkeyPatch, page: Dashboard) -> Generator[None, None, None]:
        patch.setattr(
            page.services.launch, "_lock" if self.action == "lock" else "_discard", self.call
        )
        try:
            yield
        finally:
            self.release.set()


def actual_files(project: Project, action: str, changed: bytes) -> None:
    stage = project.root / ".ctstudio/stage/course.kcl"
    if action == "lock":
        manual = project.root / "files/course.kcl"
        assert manual.is_file(), "Lock did not make the real manual file"
        assert manual.read_bytes() == changed, "Lock changed the user's bytes"
        assert manifest_io.load(project.manifest_path).components.kcl.mode == "manual"
    else:
        backups = list(project.root.glob(".ctstudio/backups/*/.ctstudio/stage/course.kcl"))
        assert len(backups) == 1 and not stage.exists(), "Discard did not move into one real backup"
        assert backups[0].read_bytes() == changed, "Discard backup lost the user's bytes"


def honest_note(page: Dashboard) -> str:
    banner = page.cards["kcl"].outside
    note = page.launch_notice.text()
    assert banner.note.text() == note != "", "requested card lost its joined outcome"
    assert banner.note.toolTip() == banner.note.accessibleDescription() == note
    assert banner.progress.isHidden() and not banner.activity.text()
    assert not page.outside_edits.pending, "joined ownership remained pending"
    assert "Locked as manual" not in note and "was backed up" not in note, "false success claim"
    return note


def protected(qtbot: QtBot, page: Dashboard, project: Project) -> None:
    held = project.lock
    assert project.read_only and held is not None, "unsafe recovery dropped protection"
    assert not page.edit_button.isEnabled() and not page.builds._eligible()
    error = outcome(lambda: project.save(project.manifest))
    assert isinstance(error, ProjectError) and "read-only" in str(error), "save was not refused"
    error = outcome(lambda: page.services.start_reconcile("kcl", "lock"))
    assert isinstance(error, ProjectError) and "read-only" in str(error), "action was not refused"
    with Project.open(project.root) as contender:
        assert contender.read_only, "unsafe recovery released the actual writer lock"
    assert settled(qtbot, lambda: idle(page))
    project.close()
    with Project.open(project.root) as reopened:
        assert not reopened.read_only, "close/reopen did not restore editable ownership"
        assert reopened.manifest == manifest_io.load(project.manifest_path)
