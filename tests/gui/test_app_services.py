"""P5-T01a: the app's services: one current project, the tools, the build controller."""

from __future__ import annotations

from pathlib import Path

import pytest
from build_fakes import WAIT, FakeBuilds, fake, project
from pytestqt.qtbot import QtBot

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.services import AppServices, ToolsService
from ctstudio.gui.status_service import StatusService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["fake", "project"]  # fixtures used by name


def services(fake: FakeBuilds) -> AppServices:
    quiet = StatusService(evaluate=lambda _project, _tools: {}, find_tools=lambda **_kw: ())
    return AppServices(build=BuildController(plan=fake.plan, build=fake.run), status=quiet)


def second(tmp_path: Path) -> Path:
    other = tmp_path / "Autre piste"
    Project.create(other, "Autre", slot="castle_course").close()
    return other


def test_nothing_is_open_at_first_and_the_parts_are_there(fake: FakeBuilds) -> None:
    made = services(fake)
    assert made.project is None
    assert isinstance(made.tools, ToolsService)
    assert isinstance(made.build, BuildController)
    assert isinstance(made.status, StatusService)
    assert made.shutdown(1)


def test_opening_a_project_makes_it_current_and_locks_it(
    fake: FakeBuilds, project: Project
) -> None:
    root = project.root
    project.close()
    made = services(fake)
    opened = made.open_project(root)
    assert made.project is opened
    assert opened.root == root
    assert not opened.read_only
    assert Project.open(root).read_only  # this app holds it
    assert made.shutdown(1)


def test_opening_another_project_closes_the_first(
    fake: FakeBuilds, project: Project, tmp_path: Path
) -> None:
    root = project.root
    project.close()
    made = services(fake)
    first = made.open_project(root)
    made.open_project(second(tmp_path))
    assert first.read_only  # its lock was given back
    with Project.open(root) as again:
        assert not again.read_only
    assert made.shutdown(1)


def test_opening_the_open_project_again_keeps_it(fake: FakeBuilds, project: Project) -> None:
    root = project.root
    project.close()
    made = services(fake)
    first = made.open_project(root)
    assert made.open_project(root) is first
    assert not first.read_only
    assert made.shutdown(1)


def test_a_folder_that_cannot_be_opened_leaves_the_current_project_open(
    fake: FakeBuilds, project: Project, tmp_path: Path
) -> None:
    root = project.root
    project.close()
    made = services(fake)
    first = made.open_project(root)
    with pytest.raises(ProjectError):
        made.open_project(tmp_path / "not a project")
    assert made.project is first
    assert not first.read_only
    assert made.shutdown(1)


def test_closing_gives_the_lock_back(fake: FakeBuilds, project: Project) -> None:
    root = project.root
    project.close()
    made = services(fake)
    made.open_project(root)
    made.close_project()
    assert made.project is None
    with Project.open(root) as again:
        assert not again.read_only
    made.close_project()  # nothing open: nothing to do
    assert made.shutdown(1)


def test_a_project_is_not_switched_or_closed_while_it_builds(
    qtbot: QtBot, fake: FakeBuilds, project: Project, tmp_path: Path
) -> None:
    import threading

    root = project.root
    project.close()
    fake.gate = threading.Event()
    made = services(fake)
    current = made.open_project(root)
    with qtbot.waitSignal(made.build.build_event, timeout=WAIT):
        made.build.start(current)
    with pytest.raises(ProjectError, match="being built"):
        made.open_project(second(tmp_path))
    with pytest.raises(ProjectError, match="being built"):
        made.close_project()
    assert made.project is current
    assert not current.read_only
    with qtbot.waitSignal(made.build.finished, timeout=WAIT):
        fake.gate.set()
    made.close_project()
    assert made.project is None
    assert made.shutdown(1)


def test_shutdown_stops_the_build_then_closes_the_project(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    import threading

    root = project.root
    project.close()
    fake.gate = threading.Event()
    made = services(fake)
    current = made.open_project(root)
    with qtbot.waitSignal(made.build.build_event, timeout=WAIT):
        made.build.start(current)
    threading.Timer(0.05, fake.gate.set).start()
    assert made.shutdown(WAIT / 1000)
    assert fake.cancels[0].cancelled
    assert made.project is None
    assert current.read_only


def test_shutdown_keeps_the_project_while_a_build_will_not_stop(
    qtbot: QtBot, fake: FakeBuilds, project: Project
) -> None:
    import threading

    root = project.root
    project.close()
    fake.gate = threading.Event()
    made = services(fake)
    current = made.open_project(root)
    with qtbot.waitSignal(made.build.build_event, timeout=WAIT):
        made.build.start(current)
    assert not made.shutdown(0.05)
    assert not current.read_only  # the build still uses it
    fake.gate.set()
    assert made.shutdown(WAIT / 1000)
    assert current.read_only
