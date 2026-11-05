"""Guard probes for rebinding and planned non-component step namespaces."""

from pathlib import Path

import pytest
from build_fakes import FakeBuilds
from pytestqt.qtbot import QtBot
from test_dashboard_builds import finish_build, setup

from ctstudio.core.build.events import BuildStarted, NodeStarted
from ctstudio.core.project.project import Project
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["setup"]
Setup = tuple[Dashboard, AppServices, FakeBuilds]


def test_rebinding_discards_still_queued_build_presentation(setup: Setup, qtbot: QtBot) -> None:
    page, services, fake = setup
    project = services.project
    assert project is not None
    page.builds.start()
    qtbot.waitUntil(lambda: len(fake.ran) == 1)
    page.set_project(project, changed=True)
    services.build.build_event.emit(BuildStarted(("stage:kcl",)))
    services.build.build_event.emit(NodeStarted("stage:kcl"))
    services.build.notice.emit("Old run warning")
    assert page.builds.controls.activity.text() == ""
    assert page.builds.controls.notice.text() == ""
    assert page.cards["kcl"].build_label.text() == ""


def test_planned_non_stage_namespace_is_overall_progress_only(setup: Setup, qtbot: QtBot) -> None:
    page, services, fake = setup
    fake.events[0] = BuildStarted(("export:kcl",))
    page.builds.start()
    qtbot.waitUntil(lambda: page.builds.controls.progress.maximum() == 1)
    services.build.build_event.emit(NodeStarted("export:kcl"))
    assert "export:kcl" in page.builds.controls.activity.text()
    assert page.cards["kcl"].build_label.text() == ""


def test_owner_and_view_replacement_cannot_reuse_an_old_run(
    setup: Setup, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page, services, fake = setup
    page.builds.start()
    qtbot.waitUntil(lambda: page.builds.controls.progress.maximum() == 1)
    with Project.create(tmp_path / "Other é", "Other é") as replacement:
        with monkeypatch.context() as patch:
            patch.setattr(services, "project", replacement)
            patch.setattr(page, "_project", replacement)
            services.build.build_event.emit(NodeStarted("stage:kcl"))
            services.build.notice.emit("Wrong project warning")
            finish_build(qtbot, services, fake)
            assert page.builds.controls.notice.text() == ""
            assert page.builds.controls.last_result.text() == ""
            assert page.cards["kcl"].build_label.text() == ""
