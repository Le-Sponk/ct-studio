"""Live output uses the joined owner and the dashboard's captured run context."""

from copy import copy
from dataclasses import replace
from threading import Event

import pytest
from build_fakes import FakeBuilds, summary
from pytestqt.qtbot import QtBot
from test_dashboard_builds import finish_build, setup

from ctstudio.core.build.events import BuildFinished, BuildStarted, LogLine
from ctstudio.gui.build_log_model import LogRole
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["setup"]
Setup = tuple[Dashboard, AppServices, FakeBuilds]


def test_worker_output_is_live_literal_and_collected_while_collapsed(
    setup: Setup, qtbot: QtBot
) -> None:
    page, services, fake = setup
    assert hasattr(page.builds, "log"), "The dashboard needs a live build log"
    log = page.builds.log
    observed: list[tuple[int, bool]] = []

    def observe(event: object) -> None:
        if isinstance(event, BuildStarted):
            observed.append((log.model.rowCount(), services.build.running))

    services.build.build_event.connect(observe)
    fake.events = [
        LogLine("tool", "Café 日本\r\n<b>not a command</b>"),
        BuildStarted(("stage:kcl",)),
        BuildFinished(summary()),
    ]
    assert fake.gate is not None
    fake.gate.set()
    page.builds.start()
    finish_build(qtbot, services, fake)
    assert observed == [(2, True)]  # output arrived before joined completion
    assert [log.model.data(log.model.index(i), LogRole.Text) for i in range(2)] == [
        "Café 日本",
        "<b>not a command</b>",
    ]
    assert log.body.isHidden() and not log.toggle.isChecked()
    layout = page.layout()
    assert layout is not None
    assert layout.indexOf(log) == layout.indexOf(page.builds.controls) - 1
    assert page.builds.controls.test_button.isEnabled()


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled", "error"])
def test_log_survives_navigation_and_outcome_but_new_run_and_rebind_clear(
    setup: Setup, qtbot: QtBot, outcome: str
) -> None:
    page, services, fake = setup
    project = services.project
    assert project is not None
    fake.events[-1] = BuildFinished(summary(outcome if outcome != "error" else "failed"))
    fake.run_error = RuntimeError("Synthetic failure") if outcome == "error" else None
    page.builds.start()
    qtbot.waitUntil(lambda: page.builds.controls.progress.maximum() == 1)
    log = page.builds.log
    services.build.build_event.emit(LogLine("stage:kcl", "Keep this output"))
    log.toggle.click()
    page.set_project(project)
    assert log.model.rowCount() == 1 and log.toggle.isChecked()
    finish_build(qtbot, services, fake)
    page.set_project(project)
    qtbot.waitUntil(lambda: not page.busy)
    services.build.build_event.emit(LogLine("old", "Late output after completion"))
    assert log.model.rowCount() == 1 and log.toggle.isChecked()
    page.builds.can_start = lambda: False
    page.builds.start()
    assert log.model.rowCount() == 1  # a refused request must not destroy the last log
    page.builds.can_start = lambda: True
    fake.run_error, fake.gate = None, Event()
    page.builds.start()
    assert log.model.rowCount() == 0 and log.toggle.isChecked()
    services.build.build_event.emit(LogLine("stage:kcl", "New output"))
    assert log.model.rowCount() == 1
    page.set_project(project, changed=True)
    services.build.build_event.emit(LogLine("old", "Queued output from the previous binding"))
    assert (log.model.rowCount(), log.model.dropped_rows, log.toggle.isChecked()) == (0, 0, False)


@pytest.mark.parametrize(
    "boundary", ["owner", "view", "root", "manifest", "service", "replacement"]
)
def test_changed_context_cannot_append_output(
    setup: Setup, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    page, services, _fake = setup
    project = services.project
    assert project is not None
    page.builds.start()
    qtbot.waitUntil(lambda: page.builds.controls.progress.maximum() == 1)
    log = page.builds.log
    services.build.build_event.emit(LogLine("n", "Current run"))
    targets = {
        "owner": (services, "project", None),
        "view": (page, "_project", None),
        "root": (project, "root", project.root / "different"),
        "manifest": (project, "manifest", replace(project.manifest)),
        "service": (page, "services", copy(services)),
        "replacement": (page, "_project", copy(project)),
    }
    target, name, value = targets[boundary]
    with monkeypatch.context() as patch:
        patch.setattr(target, name, value)
        if boundary == "replacement":
            patch.setattr(services, "project", value)
        services.build.build_event.emit(LogLine("n", "Wrong context"))
        assert log.model.rowCount() == 1
        assert log.model.data(log.model.index(0), LogRole.Text) == "Current run"
