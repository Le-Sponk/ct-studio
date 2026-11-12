"""P5-T06c1: outside-edit operations use the existing joined launch owner, not the UI."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from assign_helpers import kcl_bytes
from PySide6.QtTest import QSignalSpy
from pytestqt.qtbot import QtBot
from reconcile_helpers import edited_project, settled

from ctstudio.core.components.assign import Assigned
from ctstudio.gui.launch_controller import THREAD_NAME, LaunchController, LaunchResult

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_real_core_action_runs_off_ui_and_returns_an_explicit_joined_receipt(
    qtbot: QtBot, tmp_path: Path, action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = edited_project(tmp_path)
    manifest = project.manifest
    owner = LaunchController()
    done = QSignalSpy(owner.completed)
    events: list[str] = []
    threads: list[threading.Thread] = []
    real_join = threading.Thread.join

    def joined(thread: threading.Thread, timeout: float | None = None) -> None:
        if thread.name == THREAD_NAME:
            threads.append(thread)
            events.append("joined")
        real_join(thread, timeout)

    def busy_changed(busy: bool) -> None:
        events.append(f"busy={busy}")

    def completed(_payload: object) -> None:
        events.append("completed")

    owner.busy_changed.connect(busy_changed)
    owner.completed.connect(completed)
    monkeypatch.setattr(threading.Thread, "join", joined)
    try:
        assert owner.reconcile(project, "kcl", action)
        assert settled(qtbot, lambda: not owner.busy)
        assert done.count() == 1
        result = done.at(0)[0]
        assert isinstance(result, LaunchResult)
        assert result.edit_action == action and result.source is None
        assert result.project is project and result.manifest is manifest
        assert result.root == project.root and result.component_id == "kcl"
        assert result.error is None
        assert events == ["busy=True", "joined", "busy=False", "completed"]
        assert len(threads) == 1 and threads[0] is not threading.main_thread()
        assert not threads[0].is_alive()
        assert project.manifest is manifest, "publishing belongs to the later UI receiver"
        if action == "lock":
            assert isinstance(result.receipt, Assigned)
            assert result.receipt.manifest.components.kcl.mode == "manual"
            assert (project.root / "files/course.kcl").read_bytes() == kcl_bytes(0x480)
        else:
            assert isinstance(result.receipt, Path)
            assert (result.receipt / ".ctstudio/stage/course.kcl").read_bytes() == kcl_bytes(0x480)
            assert not (project.root / ".ctstudio/stage/course.kcl").exists()
    finally:
        assert owner.shutdown(10)
        project.close()
