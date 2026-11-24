"""P5-T08e2 acceptance in CT Studio: after the next GUI build only the saved number of build
logs remain in the project; back at the default, 20; a damaged settings file keeps the
default (and the build says the settings are ignored).

The build is the real ``BuildController`` and ``build_project`` with the real runner on a
plan with no steps, so the build log written and the pruning are the runner's own.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest
from editor_owner_helpers import outcome
from editor_request_helpers import settled
from pytestqt.qtbot import QtBot

from ctstudio.core.build.build_log import KEEP, LOG_DIR
from ctstudio.core.build.events import BuildSummary
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import Profile
from ctstudio.core.build.project_build import BuildPlan, build_project
from ctstudio.core.build.runner import BuildRequest
from ctstudio.core.components.status import ComponentStatus
from ctstudio.core.project import settings
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.project.settings import BUILD_IGNORED
from ctstudio.gui.advanced import AdvancedService
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
OLD = 30
DAMAGED = '{"format": 1, "build_logs_kept": 0}\n'


def no_steps(root: Path, manifest: Manifest, profile: Profile, **_kw: object) -> BuildPlan:
    return BuildPlan(BuildGraph(root, []), BuildRequest(manifest, profile, {}, {}))


def no_statuses(_project: object, _tools: object) -> Mapping[str, ComponentStatus]:
    return {}


def no_tools(**_kwargs: object) -> tuple[()]:
    return ()


@contextmanager
def opened(folder: Path) -> Generator[tuple[AppServices, Project]]:
    services = AppServices(
        status=StatusService(evaluate=no_statuses, find_tools=no_tools),
        build=BuildController(plan=no_steps, build=build_project),
    )
    project = Project.create(folder / "Logs é", "Logs é")
    services.adopt(project)
    try:
        yield services, project
    finally:
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def seed(project: Project) -> list[Path]:
    folder = project.root / LOG_DIR
    folder.mkdir(parents=True, exist_ok=True)
    made = [folder / f"build-2000-01-01T00-00-{n:02d}.000000Z.log" for n in range(OLD)]
    for path in made:
        path.write_text("old\n", encoding="utf-8")
    return made


def logs(project: Project) -> list[Path]:
    return sorted((project.root / LOG_DIR).glob("build-*.log"))


def built(qtbot: QtBot, services: AppServices) -> list[str]:
    """Run one build; the notices it gave."""
    summaries: list[BuildSummary] = []
    notices: list[str] = []
    services.build.finished.connect(summaries.append)
    services.build.notice.connect(notices.append)
    assert settled(qtbot, lambda: not services.status.busy), "the status check hung"
    assert services.start_build() is True, "the build did not start"
    assert settled(qtbot, lambda: len(summaries) == 1), "the build never finished"
    services.build.finished.disconnect(summaries.append)
    services.build.notice.disconnect(notices.append)
    assert summaries[0].outcome == "succeeded", summaries[0]
    return notices


def test_the_next_gui_build_keeps_the_saved_number_of_build_logs(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with opened(tmp_path) as (services, project):
        old = seed(project)
        assert AdvancedService().save_build_logs_kept(5) == 5
        assert built(qtbot, services) == []
        left = logs(project)
        assert len(left) == 5, f"{len(left)} build logs left, not 5"
        assert left[:-1] == old[-4:] and left[-1] not in old, "not the newest logs were kept"
        assert AdvancedService().save_build_logs_kept(100) == 100
        seed(project)
        before = len(logs(project))
        assert before > KEEP, "too few logs to show that more than the default are kept"
        assert built(qtbot, services) == []
        assert len(logs(project)) == before + 1, "a larger number deleted logs"
        assert AdvancedService().save_build_logs_kept(None) is None
        assert built(qtbot, services) == []
        assert len(logs(project)) == KEEP, "back at the default, not 20 logs were kept"


def test_a_damaged_settings_file_keeps_the_default(qtbot: QtBot, tmp_path: Path) -> None:
    path = settings.default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DAMAGED, encoding="utf-8")
    with opened(tmp_path) as (services, project):
        seed(project)
        notices = built(qtbot, services)
        assert len(logs(project)) == KEEP, "a damaged file did not keep the default"
        assert notices and BUILD_IGNORED in notices[0], notices
    assert path.read_text(encoding="utf-8") == DAMAGED
