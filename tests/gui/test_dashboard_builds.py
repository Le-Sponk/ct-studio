"""P5-T03e22: real owners, synthetic builds and separate live card presentation."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from copy import copy
from dataclasses import replace
from pathlib import Path

import pytest
from build_fakes import FakeBuilds, summary
from pytestqt.qtbot import QtBot

from ctstudio.core.build.events import (
    BuildFinished,
    BuildStarted,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
)
from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.components.status import ComponentStatus, State
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def no_tools(**_kw: object) -> tuple[str, ...]:
    return ()


def release_gate(fake: FakeBuilds) -> None:
    gate = fake.gate
    assert gate is not None
    gate.set()


def finish_build(qtbot: QtBot, services: AppServices, fake: FakeBuilds) -> None:
    release_gate(fake)
    qtbot.waitUntil(lambda: not services.build.running and not services.status.busy)


@pytest.fixture
def setup(qtbot: QtBot, tmp_path: Path) -> Iterator[tuple[Dashboard, AppServices, FakeBuilds]]:
    fake = FakeBuilds()
    fake.gate = threading.Event()
    fake.events = [BuildStarted(("stage:kcl",)), BuildFinished(summary())]
    status = StatusService(
        evaluate=lambda _p, _t: {
            spec.id: ComponentStatus(State.STALE, ("Last checked reason",)) for spec in COMPONENTS
        },
        find_tools=no_tools,
        settings_path=tmp_path / "settings.json",
        delay_ms=1,
    )
    controller = BuildController(
        plan=fake.plan, build=fake.run, settings_path=tmp_path / "settings.json"
    )
    services = AppServices(build=controller, status=status)
    project = Project.create(tmp_path / "Pistë 日本", "Pistë")
    services.adopt(project)
    page = Dashboard(services)
    qtbot.addWidget(page)
    page.set_project(project)
    qtbot.waitUntil(lambda: not status.busy and not page.busy)
    for cls in (Dashboard, type(page.builds)):
        print(f"origin: {__import__(cls.__module__, fromlist=['']).__file__}")
    try:
        yield page, services, fake
    finally:
        release_gate(fake)
        assert services.shutdown(10)


@pytest.mark.parametrize("release", [False, True])
def test_routes_profile_and_waits_for_joined_result(
    setup: tuple[Dashboard, AppServices, FakeBuilds], qtbot: QtBot, release: bool
) -> None:
    page, services, fake = setup
    controls = page.builds.controls
    button = controls.release_button if release else controls.test_button
    assert button.isEnabled()
    button.click()
    qtbot.waitUntil(lambda: len(fake.ran) == 1)
    assert (
        services.build.running,
        fake.planned[0]["profile"],
        controls.last_result.text(),
        button.isEnabled(),
        controls.cancel_button.isEnabled(),
    ) == (True, "release" if release else "test", "", False, True)
    services.build.build_event.emit(BuildFinished(summary()))
    assert controls.last_result.text() == ""  # a core event is not joined completion
    finish_build(qtbot, services, fake)
    assert "succeeded" in controls.last_result.text()
    assert (button.isEnabled(), page.busy) == (True, False)
    assert all(thread is not threading.main_thread() for thread in fake.threads)
    assert page._layout.indexOf(controls) == page._layout.count() - 1


@pytest.mark.parametrize(
    ("event", "text"),
    [
        (NodeStarted("stage:kcl"), "Build: working"),
        (NodeFinished("stage:kcl", 0.1, ()), "Build: done"),
        (NodeSkipped("stage:kcl"), "Build: unchanged"),
        (NodeFailed("stage:kcl", "bad", "Retry", False), "Build: failed"),
        (NodeFailed("stage:kcl", "stop", None, True), "Build: cancelled"),
    ],
)
def test_live_overlay_preserves_checked_status(
    setup: tuple[Dashboard, AppServices, FakeBuilds], qtbot: QtBot, event: object, text: str
) -> None:
    page, services, _fake = setup
    page.builds.start()
    qtbot.waitUntil(lambda: page.builds.controls.progress.maximum() == 1)
    services.build.build_event.emit(event)
    card = page.cards["kcl"]
    if not isinstance(event, NodeStarted):
        services.build.build_event.emit(NodeStarted("stage:kcl"))
    assert card.build_label.text() == text
    assert card.build_label.toolTip() == text
    assert card.build_label.accessibleDescription() == text
    assert (
        card.status_label.text() == "out of date" and card.summary.text() == "Last checked reason"
    )
    card.show_status(ComponentStatus(State.READY, ("Rechecked reason",)))
    assert card.build_label.text() == text and card.summary.text() == "Rechecked reason"


@pytest.mark.parametrize(
    "field,text",
    [("ran", "done"), ("skipped", "unchanged"), ("failed", "failed"), ("cancelled", "cancelled")],
)
def test_only_planned_stage_ids_update_cards_and_summary_reconciles(
    setup: tuple[Dashboard, AppServices, FakeBuilds], qtbot: QtBot, field: str, text: str
) -> None:
    page, services, fake = setup
    fields = {"ran": (), "not_run": ("stage:kmp",), field: ("stage:kcl",)}
    fake.events = [
        BuildStarted(("stage:kcl", "assemble", "validate")),
        BuildFinished(
            summary(field if field in ("failed", "cancelled") else "succeeded", **fields)
        ),
    ]
    page.builds.start()
    services.build.build_event.emit(NodeStarted("stage:kcl"))
    assert page.cards["kcl"].build_label.text() == ""
    qtbot.waitUntil(lambda: page.builds.controls.progress.maximum() == 3)
    for name in ("stage:kmp", "kcl", "assemble", "validate", "stage:unknown"):
        services.build.build_event.emit(NodeStarted(name))
    assert all(card.build_label.text() == "" for card in page.cards.values())
    finish_build(qtbot, services, fake)
    assert page.cards["kcl"].build_label.text() == f"Build: {text}"
    assert page.cards["kmp"].build_label.text() == "Build: not run"
    assert page.cards["kcl"].status_label.text() == "out of date"


def test_same_project_navigation_preserves_overlay_new_request_and_binding_clear_it(
    setup: tuple[Dashboard, AppServices, FakeBuilds], qtbot: QtBot
) -> None:
    page, services, fake = setup
    project = services.project
    assert project is not None
    page.builds.start()
    qtbot.waitUntil(lambda: len(fake.ran) == 1)
    services.build.build_event.emit(NodeStarted("stage:kcl"))
    page.set_project(project)
    assert page.cards["kcl"].build_label.text() == "Build: working"
    finish_build(qtbot, services, fake)
    page.set_project(project)
    qtbot.waitUntil(lambda: not page.busy)
    assert page.cards["kcl"].build_label.text() == "Build: done"
    page.builds.controls.show_notice("Old warning")
    fake.gate = threading.Event()
    page.builds.start()
    assert page.cards["kcl"].build_label.text() == ""
    assert page.builds.controls.notice.text() == ""
    page.set_project(project, changed=True)
    assert page.builds.controls.activity.text() == ""
    assert all(card.build_label.isHidden() for card in page.cards.values())


@pytest.mark.parametrize(
    "guard", ["view", "owner", "readonly", "edit", "launch", "build", "check", "history", "status"]
)
def test_start_and_controls_use_explicit_guards(
    setup: tuple[Dashboard, AppServices, FakeBuilds], monkeypatch: pytest.MonkeyPatch, guard: str
) -> None:
    page, services, fake = setup
    project = services.project
    assert project is not None
    with monkeypatch.context() as patch:
        targets = {
            "view": (page, "_project", None),
            "owner": (services, "project", None),
            "readonly": (project, "lock", None),
            "edit": (services, "editing", True),
            "launch": (services.launch, "_busy", True),
            "build": (services.build, "_running", True),
            "check": (page, "_checking", True),
            "history": (page.builds, "can_start", lambda: False),
            "status": (services.status, "_pending", True),
        }
        target, name, value = targets[guard]
        patch.setattr(target, name, value)
        page._sync()
        assert page.builds.controls.test_button.isEnabled() == (guard == "history")
        page.builds.start()
        assert fake.planned == []
    page.setEnabled(False)
    page._sync()
    page.setEnabled(True)
    assert page.builds.controls.test_button.isEnabled()


@pytest.mark.parametrize("boundary", ["owner", "view", "root", "manifest", "service"])
@pytest.mark.parametrize("crash", [False, True])
def test_changed_context_drops_events_notices_and_result(
    setup: tuple[Dashboard, AppServices, FakeBuilds],
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    crash: bool,
) -> None:
    page, services, fake = setup
    fake.run_error = RuntimeError("Wrong context failure") if crash else None
    project = services.project
    assert project is not None
    page.builds.start()
    qtbot.waitUntil(lambda: page.builds.controls.progress.maximum() == 1)
    with monkeypatch.context() as patch:
        if boundary == "owner":
            patch.setattr(services, "project", None)
        elif boundary == "service":
            patch.setattr(page, "services", copy(services))
        elif boundary == "view":
            patch.setattr(page, "_project", None)
        elif boundary == "root":
            patch.setattr(project, "root", project.root / "different")
        else:
            patch.setattr(project, "manifest", replace(project.manifest))
        services.build.build_event.emit(NodeStarted("stage:kcl"))
        services.build.notice.emit("Wrong context warning")
        finish_build(qtbot, services, fake)
        assert (
            page.cards["kcl"].build_label.text(),
            page.builds.controls.notice.text(),
            page.builds.controls.last_result.text(),
        ) == ("", "", "")


@pytest.mark.parametrize(
    "error",
    [ProjectError("Bad input", hint="Choose another file"), RuntimeError(), KeyboardInterrupt()],
)
def test_errors_end_working_overlay_and_retry_clears_notices(
    setup: tuple[Dashboard, AppServices, FakeBuilds], qtbot: QtBot, error: BaseException
) -> None:
    page, services, fake = setup
    fake.run_error = error
    page.builds.start()
    qtbot.waitUntil(lambda: page.builds.controls.progress.maximum() == 1)
    services.build.build_event.emit(NodeStarted("stage:kcl"))
    services.build.notice.emit("Paths ignored for this build")
    assert "Paths ignored" in page.builds.controls.notice.text()
    finish_build(qtbot, services, fake)
    text = "Build: failed" if isinstance(error, Exception) else "Build: cancelled"
    assert page.cards["kcl"].build_label.text() == text
    notice = page.builds.controls.notice
    assert (str(error) or type(error).__name__) in notice.text()
    assert ("retry" in notice.text(), "Paths ignored" in notice.text()) == (True, True)
    assert notice.toolTip() == notice.text() == notice.accessibleDescription()
    assert (page.builds.controls.activity.text(), page.builds.controls.test_button.isEnabled()) == (
        "",
        True,
    )
    fake.run_error = None
    fake.gate = threading.Event()
    page.builds.start()
    assert notice.text() == notice.toolTip() == notice.accessibleDescription() == ""
    assert page.cards["kcl"].build_label.text() == ""


@pytest.mark.parametrize("startup", ["service", "sync", "idle", "live"])
def test_startup_failure_does_not_strand_planning_or_release_live_owner(
    setup: tuple[Dashboard, AppServices, FakeBuilds],
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    startup: str,
) -> None:
    page, services, fake = setup
    original = services.start_build
    error = ProjectError("Cannot start build", hint="Fix input then retry")

    def start(*, release: bool = False) -> bool:
        if startup == "service":
            raise error
        if startup == "sync":
            services.build.failed.emit(error)
        if startup == "live":
            original(release=release)
        return False

    monkeypatch.setattr(services, "start_build", start)
    page.builds.start()
    if startup == "live":
        qtbot.waitUntil(lambda: len(fake.ran) == 1)
        assert services.build.running and page.builds.controls.cancel_button.isEnabled()
        assert not page.builds.controls.test_button.isEnabled()
        assert services.project is not None and not services.project.read_only
    else:
        qtbot.waitUntil(lambda: not services.status.busy)
        assert page.builds.controls.activity.text() == ""
        assert "retry" in page.builds.controls.notice.text().lower()
        assert page.builds.controls.test_button.isEnabled()


def test_cancel_uses_existing_owner_once_and_post_refresh_recovers(
    setup: tuple[Dashboard, AppServices, FakeBuilds], qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    page, services, fake = setup
    project = services.project
    assert project is not None
    fake.events[-1] = BuildFinished(summary("cancelled", ran=(), cancelled=("stage:kcl",)))
    calls: list[bool] = []
    original = services.build.cancel

    def cancel() -> None:
        calls.append(True)
        original()

    monkeypatch.setattr(services.build, "cancel", cancel)
    page.builds.controls.cancel_requested.emit()
    assert calls == []
    page.builds.start()
    qtbot.waitUntil(lambda: len(fake.cancels) == 1)
    page.builds.controls.cancel_button.click()
    page._sync()
    page.builds.controls.cancel_button.click()
    page.builds.cancel()
    assert (calls, fake.cancels[0].cancelled, page.builds.controls.cancel_button.isEnabled()) == (
        [True],
        True,
        False,
    )
    assert (services.project, project.read_only, services.build.running) == (project, False, True)
    finish_build(qtbot, services, fake)
    assert "cancelled" in page.builds.controls.last_result.text()
    assert page.cards["kcl"].build_label.text() == "Build: cancelled"
    assert (page.busy, page.builds.controls.test_button.isEnabled()) == (False, True)
    assert (services.project, project.read_only) == (project, False)


def test_window_wires_history_guard_and_refused_close_keeps_build_visible(
    setup: tuple[Dashboard, AppServices, FakeBuilds], qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    _page, services, fake = setup
    from ctstudio.gui.views.welcome_page import WelcomePage

    window = MainWindow(services)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: not window.welcome.busy and not services.status.busy)
    builds = window.dashboard.builds
    try:
        with monkeypatch.context() as patch:
            patch.setattr(WelcomePage, "busy", property(lambda _self: True))
            window._navigation()
            window.dashboard._sync()
            builds.start()
            assert fake.planned == []
        window._navigation()
        assert builds.controls.test_button.isEnabled()
        builds.start()
        qtbot.waitUntil(lambda: len(fake.ran) == 1)
        monkeypatch.setattr("ctstudio.gui.main_window._SHUTDOWN_WAIT", 0)
        for _ in range(2):
            assert (window.close(), window.pages.currentIndex()) == (False, 1)
            assert "still stopping" in builds.controls.notice.text()
            assert services.project is not None
            assert not services.project.read_only
        finish_build(qtbot, services, fake)
        assert (window.dashboard.busy, builds.controls.test_button.isEnabled()) == (False, True)
    finally:
        release_gate(fake)
