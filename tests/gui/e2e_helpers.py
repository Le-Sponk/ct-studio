"""End-to-end flow setup (P5-T09): the real main window and services on fake Wiimm tools.

The window is the real ``MainWindow`` with the real New project wizard, status check, file
assignment and build controller. The build runs ``build_project`` on the real stage,
assemble and validate steps for the parts the user assigned, with the fake Wiimm programs
on PATH (the ``fake_tools_path`` fixture). Three steps the fakes cannot do are replayed
from the recorded real ``wszst`` 2.42a runs on the same committed ``course.kcl`` and
``course.kmp``: reading the KMP's objects, ``wszst analyze`` and ``wszst check``. No game
file is used; all folders are temporary.
"""

from __future__ import annotations

import json
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from editor_owner_helpers import outcome
from editor_request_helpers import settled
from pytestqt.qtbot import QtBot
from wizard_fakes import Choices

from ctstudio.core.build import assemble, validate
from ctstudio.core.build.assemble import assemble_step
from ctstudio.core.build.graph import from_manifest
from ctstudio.core.build.node import Node, Profile
from ctstudio.core.build.objects import ObjectCheck
from ctstudio.core.build.project_build import BuildPlan, build_project
from ctstudio.core.build.runner import BuildRequest
from ctstudio.core.build.stage import manual_parts
from ctstudio.core.build.validate import validate_step
from ctstudio.core.components.registry import ComponentSpec
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.validation.issues import Issue
from ctstudio.core.validation.wszst_check import parse_check
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.new_project import NewProjectWizard
from ctstudio.gui.watchdog import StallWatchdog

RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a"
INPUTS = RECORDINGS / "inputs"
VERSIONS: dict[str, str | None] = {"wszst": "2.42a", "wkmpt": "2.42a"}
WAIT = 10_000


def _recorded(case: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = json.loads(
        (RECORDINGS / "windows-ops.json").read_text(encoding="utf-8")
    )
    return next(row for row in rows if row["case"] == case)


def replayed_analyze(_szs: Path, **_kwargs: object) -> Any:
    """``wszst analyze`` as recorded on an archive of the same KCL and KMP."""
    return json.loads(_recorded("analyze json")["stdout"].replace('"<usec>"', "0"))


def replayed_check(szs: Path, **_kwargs: object) -> list[Issue]:
    """``wszst check`` as recorded, named after the archive this build made."""
    row = _recorded("check")
    return parse_check(row["stdout"].replace("t.szs", szs.name), szs, exit_code=row["exit_code"])


def no_objects(*_args: object) -> ObjectCheck:
    return ObjectCheck(None, ())


def assigned_parts_plan(
    root: Path, manifest: Manifest, profile: Profile, **_kwargs: object
) -> BuildPlan:
    """The real steps for the parts the user assigned, then assemble and validate."""
    make = manual_parts(root, manifest)

    def steps(spec: ComponentSpec, mode: str) -> Iterable[Node] | None:
        return make(spec, mode) if mode == "manual" else []

    tail = (assemble_step(root, manifest, profile), validate_step(root, manifest, profile))
    graph = from_manifest(root, manifest, steps, tail)
    return BuildPlan(graph, BuildRequest(manifest, profile, {}, VERSIONS))


@contextmanager
def studio(
    qtbot: QtBot, location: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[MainWindow, AppServices]]:
    """The main window with real services; the wizard creates projects under ``location``."""
    monkeypatch.setattr(assemble, "check_objects", no_objects)
    monkeypatch.setattr(validate, "analyze", replayed_analyze)
    monkeypatch.setattr(validate, "check", replayed_check)
    services = AppServices(build=BuildController(plan=assigned_parts_plan, build=build_project))
    choices = Choices()

    def wizard(parent: MainWindow) -> NewProjectWizard:
        return NewProjectWizard(
            default_location=location,
            choose_folder=choices.choose_folder,
            choose_blend=choices.choose_blend,
            parent=parent,
        )

    window = MainWindow(services=services, new_project=wizard)
    qtbot.addWidget(window)
    window.resize(1280, 900)
    window.show()
    # REVIEW_CHECKLIST §3: the UI thread never stalls during the flow (the watchdog log is
    # clean; P5-GATE review). Closing joins the workers on purpose, so it is not watched.
    stalls: list[str] = []
    watchdog = StallWatchdog(report=stalls.append)  # developer mode's 100 ms limit
    try:
        assert settled(qtbot, lambda: not window.welcome.busy, WAIT), "the welcome page hung"
        watchdog.start()
        assert watchdog.watching, "the stall watchdog did not start"
        yield window, services
    finally:
        assert watchdog.stop(5.0), "the watchdog thread did not end"
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"
        window.close()
    product = [stall for stall in stalls if in_product(stall)]
    assert product == [], "\n\n".join(product)


SHOT_FILE = "wizard_fakes.py"  # the screenshot helper the end-to-end tests use


def in_product(stall: str) -> bool:
    """False only for a stall inside a test screenshot's ``grab().save(...)``.

    Grabbing and PNG encoding run on the UI thread inside the test and can pass the 100 ms
    limit on a loaded machine (P5-GATE delta review: 2 of 18 runs). Everything else counts,
    including a stall while the test waits in the event loop (a product slot, Qt laying out
    or painting product widgets, or a worker holding the GIL) and the ``processEvents`` call
    before the grab, which runs product slots (second delta review).
    """
    lines = stall.splitlines()
    innermost: tuple[str, str] | None = None  # (file:function, its source line)
    for index, line in enumerate(lines):
        text = line.strip()
        if text.startswith('File "'):
            name = Path(text[6 : text.index('"', 6)]).name
            source = lines[index + 1].strip() if index + 1 < len(lines) else ""
            innermost = (f"{name}:{text.rsplit(' in ', 1)[-1]}", source)
    if innermost is None:
        return True
    where, source = innermost
    return not (where == f"{SHOT_FILE}:shot" and "grab()" in source)


def idle(window: MainWindow, services: AppServices) -> bool:
    """No assignment, status check or build is running, and the dashboard shows the result."""
    return not (
        services.launch.busy
        or services.status.busy
        or services.build.running
        or window.dashboard.busy
    )
