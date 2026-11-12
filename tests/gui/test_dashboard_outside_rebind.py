"""Rebinding presentation must not discard mandatory joined saved-state recovery."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from reconcile_helpers import owned, settled

from ctstudio.core.components.assign import Assigned
from ctstudio.core.components.edited import lock_as_manual
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("replace_memory", [False, True])
def test_rebound_current_project_never_stays_writable_with_stale_saved_state(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replace_memory: bool
) -> None:
    with owned(tmp_path) as (services, project, _work):
        written, release = threading.Event(), threading.Event()

        def saved_then_wait(given: Project, part: str) -> Assigned:
            receipt = lock_as_manual(given, part)
            written.set()
            assert release.wait(10), "the post-write worker was not released"
            return receipt

        monkeypatch.setattr(services.launch, "_lock", saved_then_wait)
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        before, held = project.manifest, project.lock
        try:
            page.cards["kcl"].outside.lock_button.click()
            assert settled(qtbot, written.is_set), "the action never reached the post-write hold"
            assert services.launch.busy
            if replace_memory:
                project.manifest = replace(
                    before, project=replace(before.project, name="New live edit")
                )
            live = project.manifest
            page.set_project(project, changed=True)
            assert services.launch.busy and project.lock is held
            assert not page.cards["kcl"].outside.activity.text()
            release.set()
            assert settled(
                qtbot,
                lambda: not services.launch.busy and not services.status.busy and not page.busy,
            )
            saved = manifest_io.load(project.manifest_path)
            assert saved.components.kcl.mode == "manual", "the real joined action did not run"
            assert project.manifest == saved or project.read_only, (
                "rebind discarded recovery but left stale memory writable"
            )
            assert project.lock is held and held is not None
            if replace_memory:
                assert project.manifest is live and project.read_only
                assert "reopen" in page.launch_notice.text()
            else:
                assert project.manifest == saved and not project.read_only
                assert "Locked as manual" in page.cards["kcl"].outside.note.text()
        finally:
            release.set()
