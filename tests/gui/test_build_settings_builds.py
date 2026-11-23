"""P5-T08b acceptance: a compression saved on the Build page is the one the next GUI build
passes to ``wszst create`` (the fake Wiimm program records its argv).

The build is the real ``BuildController`` and ``build_project`` running the real assemble
step; only planning is narrowed to that step (the other steps need Blender or files these
tests do not make, and ``test_build_project.py`` covers planning). The object check is left
out as in ``test_build_assemble.py``.
"""

from __future__ import annotations

import shutil
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, cast

import pytest
from editor_owner_helpers import outcome
from editor_request_helpers import settled
from pytestqt.qtbot import QtBot

from ctstudio.core.build import assemble
from ctstudio.core.build.assemble import assemble_step
from ctstudio.core.build.events import BuildSummary, NodeFailed
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import Profile
from ctstudio.core.build.objects import ObjectCheck
from ctstudio.core.build.project_build import BuildPlan, build_project
from ctstudio.core.build.runner import BuildRequest
from ctstudio.core.components.status import ComponentStatus
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.build_page import BuildPage

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
INPUTS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a" / "inputs"
VERSIONS: dict[str, str | None] = {"wszst": "2.42a", "wkmpt": "2.42a"}


class FakeTools(Protocol):
    """The ``fake_tools_path`` fixture (tests/conftest.py): the fakes' recorded calls."""

    def calls(self) -> list[dict[str, object]]: ...


def assemble_only(root: Path, manifest: Manifest, profile: Profile, **_kw: object) -> BuildPlan:
    """The real assemble step for the manifest the build was started with."""
    graph = BuildGraph(root, [assemble_step(root, manifest, profile)])
    return BuildPlan(graph, BuildRequest(manifest, profile, {}, VERSIONS))


def no_statuses(_project: object, _tools: object) -> Mapping[str, ComponentStatus]:
    return {}


def no_tools(**_kwargs: object) -> tuple[()]:
    return ()


def no_objects(*_args: object) -> ObjectCheck:
    return ObjectCheck(None, ())


@contextmanager
def project_and_page(
    qtbot: QtBot, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[AppServices, BuildPage]]:
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
    page = BuildPage(services)
    qtbot.addWidget(page)
    try:
        assert settled(qtbot, lambda: not page.busy), "the page never read the project"
        yield services, page
    finally:
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def built(qtbot: QtBot, services: AppServices, *, release: bool) -> BuildSummary:
    summaries: list[BuildSummary] = []
    events: list[object] = []
    services.build.finished.connect(summaries.append)
    services.build.build_event.connect(events.append)
    assert settled(qtbot, lambda: not services.status.busy), "the status check hung"
    assert services.start_build(release=release) is True, "the build did not start"
    assert settled(qtbot, lambda: len(summaries) == 1), "the build never finished"
    services.build.finished.disconnect(summaries.append)
    services.build.build_event.disconnect(events.append)
    failures = [e for e in events if isinstance(e, NodeFailed)]
    assert summaries[0].outcome == "succeeded", f"the build failed: {failures}"
    return summaries[0]


def create_flags(fake_tools_path: FakeTools) -> list[list[str]]:
    """The options after ``create stage --dest <file>`` of every ``wszst create`` so far."""
    argvs = [call["argv"] for call in fake_tools_path.calls()]
    texts = [[str(part) for part in cast("list[object]", a)] for a in argvs if isinstance(a, list)]
    return [argv[4:] for argv in texts if argv[0] == "create"]


def save(qtbot: QtBot, page: BuildPage, combo_name: str, value: str) -> None:
    combo = getattr(page, combo_name)
    combo.setCurrentIndex(combo.findData(value))
    assert page.save_button.isEnabled(), "Save is off after a change"
    page.save_button.click()
    assert settled(qtbot, lambda: not page.busy) and "Saved" in page.problem.text()


def test_the_saved_test_compression_is_the_next_test_build_command(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_tools_path: FakeTools
) -> None:
    with project_and_page(qtbot, tmp_path, monkeypatch) as (services, page):
        built(qtbot, services, release=False)
        save(qtbot, page, "test_compression", "best")  # the fake cannot list an unpacked file
        built(qtbot, services, release=False)
        assert create_flags(fake_tools_path) == [["--fast"], []], (
            "the test build did not use the saved compression"
        )


def test_the_saved_release_compression_is_the_next_release_build_command(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_tools_path: FakeTools
) -> None:
    with project_and_page(qtbot, tmp_path, monkeypatch) as (services, page):
        built(qtbot, services, release=True)
        save(qtbot, page, "release_compression", "fast")
        built(qtbot, services, release=True)
        assert create_flags(fake_tools_path) == [[], ["--fast"]], (
            "the release build did not use the saved compression"
        )
