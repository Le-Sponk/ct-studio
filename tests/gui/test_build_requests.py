"""P5-T03e1: the app's current-project build boundary, without discovery or tools."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from build_fakes import FakeBuilds
from pytestqt.qtbot import QtBot

from ctstudio.core.build.events import BuildFinished, BuildStarted
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.launch_controller import LaunchController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def no_tools(**_kw: object) -> tuple[()]:
    return ()


def refused_start(*_args: object, **_kw: object) -> bool:
    return False


@pytest.fixture
def app(qtbot: QtBot, tmp_path: Path) -> Iterator[tuple[AppServices, Project, FakeBuilds]]:
    fake = FakeBuilds()
    build = BuildController(plan=fake.plan, build=fake.run)
    status = StatusService(evaluate=lambda _p, _t: {}, find_tools=no_tools)
    services = AppServices(build=build, status=status)
    project = Project.create(tmp_path / "Build 日本", "Build 日本")
    services.adopt(project)
    qtbot.waitUntil(lambda: not status.busy)
    try:
        yield services, project, fake
    finally:
        if fake.gate is not None:
            fake.gate.set()
        for worker in set(fake.threads):
            worker.join(10)  # drain even when a mutant abandoned its controller reference
            assert not worker.is_alive()
        services.editing = False
        assert services.shutdown(10)


@pytest.mark.parametrize("release,force,only", [(True, True, "kcl"), (False, False, None)])
def test_current_project_build_passes_exact_options(
    qtbot: QtBot,
    app: tuple[AppServices, Project, FakeBuilds],
    release: bool,
    force: bool,
    only: str | None,
) -> None:
    services, project, fake = app
    assert services.start_build(release=release, force=force, only=only)
    qtbot.waitUntil(lambda: not services.build.running)
    assert len(fake.planned) == len(fake.ran) == 1
    planned = fake.planned[0]
    assert planned["root"] == project.root and planned["manifest"] is project.manifest
    assert planned["profile"] == ("release" if release else "test") and planned["only"] == only
    assert fake.ran[0]["force"] is force


@pytest.mark.parametrize(
    "state,words",
    [
        ("no_project", "No project"),
        ("read_only", "read-only"),
        ("editing", "details"),
        ("building", "being built"),
        ("launching", "still finishing"),
        ("checking", "checked"),
    ],
)
def test_ineligible_request_is_refused_in_memory_before_controller_start(
    app: tuple[AppServices, Project, FakeBuilds],
    state: str,
    words: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services, project, fake = app
    calls: list[object] = []

    def record(*args: object, **kwargs: object) -> bool:
        calls.append((args, kwargs))
        return True

    def forbidden(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("build eligibility must not read files")

    if state == "read_only":
        project.close()
    with monkeypatch.context() as patch:
        patch.setattr(services.build, "start", record)
        patch.setattr(Path, "read_bytes", forbidden)
        if state == "no_project":
            patch.setattr(services, "project", None)
        elif state == "editing":
            patch.setattr(services, "editing", True)
        elif state == "building":
            patch.setattr(BuildController, "running", property(lambda _self: True))
        elif state == "launching":
            patch.setattr(LaunchController, "busy", property(lambda _self: True))
        elif state == "checking":
            services.status.request(project)  # debounce itself is busy, before any worker runs
        with pytest.raises(ProjectError) as caught:
            services.start_build()
        assert words in caught.value.user_message and caught.value.hint
        assert calls == [] and fake.planned == []


def test_build_request_keeps_project_lock_until_shutdown_joins(
    qtbot: QtBot, app: tuple[AppServices, Project, FakeBuilds], tmp_path: Path
) -> None:
    from build_fakes import summary

    services, project, fake = app
    fake.gate = threading.Event()
    fake.events = [BuildStarted(("stage:kcl",)), BuildFinished(summary())]
    assert services.start_build()
    qtbot.waitUntil(lambda: bool(fake.cancels))
    with pytest.raises(ProjectError, match="being built"):
        services.start_build(release=True)
    with pytest.raises(ProjectError, match="being built"):
        services.close_project()
    with pytest.raises(ProjectError, match="being built"):
        services.open_project(tmp_path / "not read")
    incoming = Project.create(tmp_path / "Other 日本", "Other")
    with pytest.raises(ProjectError, match="being built"):
        services.adopt(incoming)
    assert incoming.read_only  # only the refused incoming project's lock was released
    assert services.shutdown(0) is False
    assert services.project is project and not project.read_only and services.build.running
    assert fake.cancels[0].cancelled
    assert len(fake.planned) == 1
    fake.gate.set()
    assert services.shutdown(10) is True
    assert project.read_only and services.project is None
    with Project.open(project.root) as reopened:
        assert not reopened.read_only


def test_controller_refusal_is_not_reported_as_a_started_build(
    app: tuple[AppServices, Project, FakeBuilds], monkeypatch: pytest.MonkeyPatch
) -> None:
    services, _project, fake = app
    monkeypatch.setattr(services.build, "start", refused_start)
    assert services.start_build() is False
    assert fake.planned == [] and not services.build.running
