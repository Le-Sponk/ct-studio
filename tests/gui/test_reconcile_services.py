"""P5-T06c1: memory-only eligibility and shared ownership for outside-edit requests."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from PySide6.QtTest import QSignalSpy
from pytestqt.qtbot import QtBot
from reconcile_helpers import outcome, owned, settled

from ctstudio.core.errors import ProjectError
from ctstudio.gui.launch_controller import LaunchResult

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_service_dispatches_current_project_without_publishing_it(
    qtbot: QtBot, tmp_path: Path, action: str
) -> None:
    with owned(tmp_path) as (services, project, work):
        manifest = project.manifest
        done = QSignalSpy(services.launch.completed)
        assert services.start_reconcile("kcl", action)
        assert work.entered.wait(5)
        assert services.launch.busy and done.count() == 0
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy)
        assert done.count() == 1
        result = done.at(0)[0]
        assert isinstance(result, LaunchResult)
        assert result.project is project and result.manifest is manifest
        assert result.edit_action == action and result.component_id == "kcl"
        assert result.receipt is not None and result.error is None
        assert work.calls[0][:3] == (project, "kcl", action)
        assert project.manifest is manifest


@pytest.mark.parametrize("action", ["lock", "discard"])
@pytest.mark.parametrize(
    "block",
    ["none", "read_only", "status", "manual", "unknown", "no_output", "manual_only", "action"],
)
def test_eligibility_refuses_without_disk_work_or_a_worker(
    qtbot: QtBot, tmp_path: Path, action: str, block: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned(tmp_path) as (services, project, work):
        part = "kcl"
        if block == "none":
            services.project = None
        elif block == "read_only":
            services.project = dataclasses.replace(project, lock=None)
        elif block == "status":
            services.status.request(project)
        elif block == "manual":
            parts = project.manifest.components
            project.manifest = dataclasses.replace(
                project.manifest,
                components=dataclasses.replace(
                    parts, kcl=dataclasses.replace(parts.kcl, mode="manual")
                ),
            )
        elif block in ("unknown", "no_output", "manual_only"):
            part = {"unknown": "wheels", "no_output": "objects", "manual_only": "kmp"}[block]
        else:
            action = "erase"

        def no_disk(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("eligibility touched disk on the UI thread")

        with monkeypatch.context() as patch:
            patch.setattr(Path, "stat", no_disk)
            patch.setattr(Path, "read_bytes", no_disk)
            error = outcome(lambda: services.start_reconcile(part, action))
        assert isinstance(error, ProjectError), f"not safely refused: {error!r}"
        assert error.hint
        assert not work.calls and not services.launch.busy
        if block == "none":
            assert error.user_message == "No project is open."
        services.project = project
        services.status.clear()


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_closed_project_is_refused_before_starting(
    qtbot: QtBot, tmp_path: Path, action: str
) -> None:
    with owned(tmp_path) as (services, project, work):
        project.close()
        error = outcome(lambda: services.start_reconcile("kcl", action))
        assert isinstance(error, ProjectError)
        assert not work.calls and not services.launch.busy
