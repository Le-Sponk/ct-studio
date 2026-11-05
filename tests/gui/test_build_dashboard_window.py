"""P5-T03e22: integrated buttons, shortcuts, navigation and cancellation ownership."""

from pathlib import Path
from threading import main_thread

import pytest
from build_fakes import summary
from build_window_helpers import build_window, eventually, finished, result, started
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QScrollArea
from pytestqt.qtbot import QtBot

from ctstudio.core.build.events import BuildFinished, NodeStarted
from ctstudio.core.components.status import ComponentStatus, State
from ctstudio.gui.status_service import StatusResult

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("release", [False, True])
def test_build_buttons_use_service_boundary_and_keep_checked_status(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, release: bool
) -> None:
    with build_window(qtbot, tmp_path) as (view, project, fake):
        page = view.dashboard
        calls: list[bool] = []
        original = view.services.start_build

        def start_build(*, release: bool = False) -> bool:
            calls.append(release)
            return original(release=release)

        monkeypatch.setattr(view.services, "start_build", start_build)
        page.services.status.updated.emit(
            StatusResult(project.root, {"kcl": ComponentStatus(State.READY, ("Last check",))})
        )
        controls = page.builds.controls
        (controls.release_button if release else controls.test_button).click()
        started(qtbot, view, fake)
        assert calls == [release], "the button bypassed AppServices.start_build"
        assert fake.planned[0]["profile"] == ("release" if release else "test")
        assert all(worker is not main_thread() for worker in fake.threads)
        page.services.build.build_event.emit(NodeStarted("stage:kcl"))
        assert page.cards["kcl"].build_label.text() == "Build: working"
        assert page.cards["kcl"].status_label.text() == "ready"
        assert page.cards["kcl"].summary.text() == "Last check"
        finished(qtbot, view, fake)
        assert "succeeded" in controls.last_result.text()
        assert page.cards["kcl"].build_label.text() == "Build: done"


@pytest.mark.parametrize("release", [False, True])
def test_build_shortcuts_reach_the_window_owner(
    qtbot: QtBot, tmp_path: Path, release: bool
) -> None:
    with build_window(qtbot, tmp_path) as (view, _project, fake):
        modifier = Qt.KeyboardModifier.ControlModifier
        if release:
            modifier |= Qt.KeyboardModifier.ShiftModifier
        QTest.keyClick(view, Qt.Key.Key_B, modifier)
        started(qtbot, view, fake)
        assert fake.planned[0]["profile"] == ("release" if release else "test")
        assert not view.new_project_action.isEnabled()
        assert not view.open_project_action.isEnabled()
        finished(qtbot, view, fake)
        assert view.new_project_action.isEnabled()


def test_escape_cancels_without_releasing_a_live_project(qtbot: QtBot, tmp_path: Path) -> None:
    with build_window(qtbot, tmp_path) as (view, project, fake):
        fake.events[-1] = BuildFinished(
            summary("cancelled", ran=(), cancelled=("stage:kcl",), not_run=("assemble",))
        )
        controls = view.dashboard.builds.controls
        controls.test_button.click()
        started(qtbot, view, fake)
        cancelled = QSignalSpy(controls.cancel_requested)
        QTest.keyClick(view, Qt.Key.Key_Escape)
        if cancelled.count() == 0:
            cancelled.wait(1000)
        assert cancelled.count() == 1
        assert fake.cancels[0].cancelled
        assert view.services.project is project and not project.read_only
        assert view.services.build.running and not controls.test_button.isEnabled()
        assert "Cancelling" in controls.activity.text()
        finished(qtbot, view, fake)
        assert "cancelled" in controls.last_result.text()
        assert "succeeded" not in controls.last_result.text()
        assert controls.test_button.isEnabled()


def test_history_busy_refuses_direct_start_and_recovers_without_refresh(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with build_window(qtbot, tmp_path) as (view, _project, fake):
        page = view.dashboard
        with monkeypatch.context() as changed:
            changed.setattr(type(view.welcome), "busy", property(lambda _self: True))
            view._navigation()
            page._sync()  # a status callback may arrive while the ancestor is disabled
            page.builds.start(False)
            assert not fake.planned
            assert not page.isEnabled()
        view._navigation()  # recovery must not need another status callback or project rebind
        assert page.builds.controls.test_button.isEnabled()
        page.builds.controls.test_button.click()
        started(qtbot, view, fake)
        finished(qtbot, view, fake)


def test_repeated_refused_close_keeps_build_results_visible_and_project_locked(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ctstudio.gui.main_window as main_window

    monkeypatch.setattr(main_window, "_SHUTDOWN_WAIT", 0.0)
    with build_window(qtbot, tmp_path) as (view, project, fake):
        controls = view.dashboard.builds.controls
        controls.test_button.click()
        started(qtbot, view, fake)
        for _attempt in range(2):
            assert result(view.close) is False
            assert view.dashboard.isVisible(), "refusal hid the owner behind the welcome page"
            assert "still stopping" in controls.notice.text()
            assert view.services.project is project and not project.read_only
        assert not view.dashboard.busy, "refusal started a status request it cannot finish"
        finished(qtbot, view, fake)
        assert "succeeded" in controls.last_result.text()
        assert controls.test_button.isEnabled()


def test_returning_to_dashboard_keeps_live_progress(qtbot: QtBot, tmp_path: Path) -> None:
    with build_window(qtbot, tmp_path) as (view, _project, fake):
        page = view.dashboard
        controls = page.builds.controls
        controls.test_button.click()
        started(qtbot, view, fake)
        page.services.build.build_event.emit(NodeStarted("stage:kcl"))
        view.home_action.trigger()
        assert not page.isVisible()
        view.dashboard_action.trigger()
        assert page.isVisible()
        assert page.cards["kcl"].build_label.text() == "Build: working"
        assert controls.progress.maximum() == 2
        assert "stage:kcl" in controls.activity.text()
        assert not page.busy
        finished(qtbot, view, fake)


def test_tab_reaches_footer_build_controls_and_scrolls(qtbot: QtBot, tmp_path: Path) -> None:
    with build_window(qtbot, tmp_path) as (view, _project, fake):
        view.resize(720, 480)
        QApplication.processEvents()
        page = view.dashboard
        page.edit_button.setFocus()
        target = page.builds.controls.release_button
        for _step in range(60):
            focus = QApplication.focusWidget()
            if focus is target:
                break
            assert focus is not None
            QTest.keyClick(focus, Qt.Key.Key_Tab)
        assert target.hasFocus(), "Tab never reached the build footer"
        scroll = view.findChild(QScrollArea, "dashboardScroll")
        assert scroll is not None
        assert scroll.verticalScrollBar().value() > 0
        QTest.keyClick(target, Qt.Key.Key_Space)
        started(qtbot, view, fake)
        assert fake.planned[0]["profile"] == "release"
        finished(qtbot, view, fake)


def test_worker_failure_is_visible_and_the_build_can_be_retried(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with build_window(qtbot, tmp_path) as (view, _project, fake):
        fake.plan_error = RuntimeError("Synthetic planner problem")
        controls = view.dashboard.builds.controls
        controls.test_button.click()
        eventually(qtbot, lambda: not view.services.build.running, "failed build did not release")
        eventually(qtbot, lambda: not view.dashboard.busy, "failed build status did not settle")
        assert "Synthetic planner problem" in controls.notice.text()
        assert controls.activity.text() == ""
        assert controls.test_button.isEnabled()
        fake.plan_error = None
        controls.release_button.click()
        started(qtbot, view, fake)
        assert "Synthetic planner problem" not in controls.notice.text()
        finished(qtbot, view, fake)
        assert "succeeded" in controls.last_result.text()
        assert len(fake.planned) == 2
