"""Pending context guards also apply before any native busy signal can run."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from reconcile_helpers import outcome, owned, settled

from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_reentrant_service_callback_cannot_dispatch_a_second_request(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned(tmp_path) as (services, project, _work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        calls: list[tuple[str, str]] = []

        def reenter(part: str, action: str) -> bool:
            calls.append((part, action))
            if len(calls) == 1:
                page.outside_edits.request(part, action)
            return False

        monkeypatch.setattr(services, "start_reconcile", reenter)
        assert outcome(lambda: page.outside_edits.request("kcl", "lock")) is None
        assert calls == [("kcl", "lock")], "presentation was not captured before dispatch"
        assert not page.outside_edits.pending
        assert page.cards["kcl"].outside.progress.isHidden()
        assert "did not start" in page.cards["kcl"].outside.note.text()


@pytest.mark.parametrize("foreign", ["manifest", "part", "action"])
def test_an_unmatched_result_cannot_end_the_active_card_request(
    qtbot: QtBot, tmp_path: Path, foreign: str
) -> None:
    with owned(tmp_path) as (services, project, work):
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        assert settled(qtbot, lambda: not page.busy and not services.status.busy)
        banner = page.cards["kcl"].outside
        banner.lock_button.click()
        assert services.launch.busy and page.outside_edits.pending
        result = LaunchResult(project, project.root, project.manifest, "kcl", edit_action="lock")
        if foreign == "manifest":
            result = replace(result, manifest=replace(project.manifest))
        elif foreign == "part":
            result = replace(result, component_id="course_model")
        else:
            result = replace(result, edit_action="discard")
        services.launch.completed.emit(result)
        assert page.outside_edits.pending and services.launch.busy
        assert not banner.progress.isHidden() and not banner.note.text()
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy and not services.status.busy)
        assert len(work.calls) == 1 and "Locked as manual" in banner.note.text()
