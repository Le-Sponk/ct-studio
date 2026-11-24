"""P5-T08e1 acceptance: with tool commands hidden, the next GUI build sends no command rows
to the dashboard while the build log file still lists them; shown, they reach it.

The build is the real ``BuildController`` and ``build_project`` running the real assemble
step with the fake Wiimm programs (as in ``test_build_settings_builds.py``), so the commands
are the ones the runner really reports and writes to ``.ctstudio/logs``.
"""

from __future__ import annotations

import shutil
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest
from editor_owner_helpers import outcome
from editor_request_helpers import settled
from pytestqt.qtbot import QtBot

from ctstudio.core.build import assemble
from ctstudio.core.build.assemble import assemble_step
from ctstudio.core.build.events import BuildSummary, CommandRun, LogLine, NodeFailed
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import Profile
from ctstudio.core.build.objects import ObjectCheck
from ctstudio.core.build.project_build import BuildPlan, build_project
from ctstudio.core.build.runner import BuildRequest
from ctstudio.core.components.status import ComponentStatus
from ctstudio.core.project import settings
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.gui.advanced import AdvancedService
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
INPUTS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a" / "inputs"
VERSIONS: dict[str, str | None] = {"wszst": "2.42a", "wkmpt": "2.42a"}
DAMAGED = '{"format": 1, "show_tool_commands": "no"}\n'


def assemble_only(root: Path, manifest: Manifest, profile: Profile, **_kw: object) -> BuildPlan:
    graph = BuildGraph(root, [assemble_step(root, manifest, profile)])
    return BuildPlan(graph, BuildRequest(manifest, profile, {}, VERSIONS))


def no_statuses(_project: object, _tools: object) -> Mapping[str, ComponentStatus]:
    return {}


def no_tools(**_kwargs: object) -> tuple[()]:
    return ()


def no_objects(*_args: object) -> ObjectCheck:
    return ObjectCheck(None, ())


@contextmanager
def packed_project(
    qtbot: QtBot, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[AppServices, Project]]:
    monkeypatch.setattr(assemble, "check_objects", no_objects)
    services = AppServices(
        status=StatusService(evaluate=no_statuses, find_tools=no_tools),
        build=BuildController(plan=assemble_only, build=build_project),
    )
    project = Project.create(folder / "Packed é", "Packed é")
    stage = project.root / ".ctstudio" / "stage"
    stage.mkdir(parents=True)
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(INPUTS / name, stage / name)
    services.adopt(project)
    try:
        yield services, project
    finally:
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def built(qtbot: QtBot, services: AppServices) -> list[object]:
    """Run one forced test build (nothing skipped); the events the GUI received."""
    summaries: list[BuildSummary] = []
    events: list[object] = []
    services.build.finished.connect(summaries.append)
    services.build.build_event.connect(events.append)
    assert settled(qtbot, lambda: not services.status.busy), "the status check hung"
    assert services.start_build(force=True) is True, "the build did not start"
    assert settled(qtbot, lambda: len(summaries) == 1), "the build never finished"
    services.build.finished.disconnect(summaries.append)
    services.build.build_event.disconnect(events.append)
    failures = [e for e in events if isinstance(e, NodeFailed)]
    assert summaries[0].outcome == "succeeded", f"the build failed: {failures}"
    return events


def newest_log(project: Project) -> str:
    logs = sorted((project.root / ".ctstudio" / "logs").glob("build-*.log"))
    assert logs, "the build wrote no log file"
    return logs[-1].read_text(encoding="utf-8")


def commands(events: list[object]) -> list[CommandRun]:
    return [event for event in events if isinstance(event, CommandRun)]


def test_hidden_commands_stay_out_of_the_dashboard_but_not_out_of_the_log_file(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_tools_path: object
) -> None:
    assert fake_tools_path is not None
    with packed_project(qtbot, tmp_path, monkeypatch) as (services, project):
        shown = built(qtbot, services)
        assert commands(shown), "a build with the default setting sent no command"
        assert any(isinstance(event, LogLine) for event in shown), "the build sent no output"
        assert AdvancedService().save_tool_commands(False) is False
        hidden = built(qtbot, services)
        assert commands(hidden) == [], "a hidden command reached the dashboard"
        assert "command: " in newest_log(project), "the build log file lost the commands"
        assert len(hidden) == len(shown) - len(commands(shown)), "other events went missing"
        assert AdvancedService().save_tool_commands(True) is True
        again = built(qtbot, services)
        assert len(commands(again)) == len(commands(shown)), "shown again, commands are missing"


def test_a_damaged_settings_file_shows_the_commands_and_says_so(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_tools_path: object
) -> None:
    assert fake_tools_path is not None
    with packed_project(qtbot, tmp_path, monkeypatch) as (services, _project):
        path = settings.default_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DAMAGED, encoding="utf-8")
        notices: list[str] = []
        services.build.notice.connect(notices.append)
        events = built(qtbot, services)
        assert commands(events), "a damaged file hid the commands"
        assert notices and "cannot be used" in notices[0], notices
        assert path.read_text(encoding="utf-8") == DAMAGED
