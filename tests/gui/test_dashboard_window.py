"""P5-T03b: project dashboard navigation stays integrated with New/Open/history."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_preopened_services_show_dashboard_on_startup(qtbot: QtBot, tmp_path: Path) -> None:
    services = quiet_services()
    project = Project.create(tmp_path / "Preopened", "Preopened")
    services.adopt(project)
    window = MainWindow(services)
    qtbot.addWidget(window)
    window.show()
    assert window.dashboard.isVisible()
    assert window.dashboard.name_label.text() == "Preopened"
    qtbot.waitUntil(lambda: not window.welcome.busy)
    assert window.dashboard_action.isEnabled()
    window.close()


def test_opened_project_replaces_welcome_with_live_overview(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(quiet_services())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    project = Project.create(tmp_path / "Dashboard é", "Dashboard é")
    window._opened(project)
    assert window.dashboard.isVisible()
    assert not window.welcome.isVisible()
    assert window.dashboard.name_label.text() == "Dashboard é"
    assert window.windowTitle() == "Dashboard é — CT Studio"
    window.home_action.trigger()
    assert window.welcome.isVisible() and not window.dashboard.isVisible()
    assert window.services.project is project and not project.read_only
    window.dashboard_action.trigger()
    assert window.dashboard.isVisible()
    window.close()
    with Project.open(project.root) as reopened:
        assert not reopened.read_only


@pytest.mark.parametrize("via_home", [False, True])
@pytest.mark.parametrize("checking", [False, True])
def test_same_project_navigation_retains_status_after_failed_refresh(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, via_home: bool, checking: bool
) -> None:
    from test_dashboard_states import ready

    window = MainWindow(quiet_services())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    project = Project.create(tmp_path / "Retained", "Retained")
    window._opened(project)
    qtbot.waitUntil(lambda: not window.dashboard.busy)
    monkeypatch.setattr(window.services.status, "request", lambda _project: None)
    window.services.status.updated.emit(ready(project.root))
    if checking:
        window.dashboard.refresh()
    if via_home:
        window.home_action.trigger()
    window.dashboard_action.trigger()  # the Ctrl+D action, also while already visible
    assert window.dashboard.isVisible()
    assert window.dashboard.cards["kcl"].status_label.text() == "ready"
    assert window.dashboard.busy
    window.services.status.failed.emit(RuntimeError("Synthetic refresh failure"))
    assert window.dashboard.cards["kcl"].status_label.text() == "ready"
    assert "Synthetic refresh failure" in window.dashboard.notice.text()
    assert not window.dashboard.busy
    window.close()


def test_open_worker_shows_welcome_progress_while_reading(qtbot: QtBot, tmp_path: Path) -> None:
    import threading

    gate = threading.Event()
    root = tmp_path / "Next project"
    Project.create(root, "Next project").close()

    class GatedWindow(MainWindow):
        def _open_from_disk(self, root: Path) -> Project:
            assert gate.wait(10)
            return Project.open(root)

    window = GatedWindow(quiet_services(), choose_folder=lambda _p: root)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    window._opened(Project.create(tmp_path / "Current", "Current"))
    try:
        window.open_project_action.trigger()
        assert window.welcome.busy
        assert window.welcome.isVisible() and not window.dashboard.isVisible()
        assert not window.open_project_action.isEnabled()
        with qtbot.waitSignal(window.welcome.opened):
            gate.set()
        assert window.dashboard.isVisible()
        assert window.services.project is not None and window.services.project.root == root
    finally:
        gate.set()
        window.close()


def test_open_error_is_visible_and_current_dashboard_remains_available(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(quiet_services(), choose_folder=lambda _p: tmp_path / "absent")
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    project = Project.create(tmp_path / "Valid", "Valid")
    window._opened(project)
    with qtbot.waitSignal(window.welcome.checked):
        window.open_project_action.trigger()
    assert window.welcome.isVisible()
    label = window.findChild(QLabel, "welcomeProblem")
    assert label is not None and label.text()
    assert window.services.project is project and not project.read_only
    assert window.dashboard_action.isEnabled()
    window.dashboard_action.trigger()
    assert window.dashboard.isVisible() and window.dashboard.name_label.text() == "Valid"
    window.close()


def test_history_problem_remains_visible_after_successful_open(
    qtbot: QtBot, tmp_path: Path
) -> None:
    from ctstudio.gui.recent_projects import RecentProjects, RecentResult

    class BrokenHistory(RecentProjects):
        def remember(self, root: Path) -> RecentResult:
            return RecentResult((), "The project opened, but history could not be saved.")

    root = tmp_path / "History failure"
    Project.create(root, "History failure").close()
    window = MainWindow(
        quiet_services(), recent_projects=BrokenHistory(), choose_folder=lambda _p: root
    )
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    with qtbot.waitSignal(window.welcome.opened):
        window.open_project_action.trigger()
    assert window.services.project is not None and not window.services.project.read_only
    assert window.welcome.isVisible()
    problem = window.findChild(QLabel, "welcomeProblem")
    assert problem is not None and "history could not be saved" in problem.text()
    assert window.dashboard_action.isEnabled()
    window.dashboard_action.trigger()
    assert window.dashboard.isVisible()
    window.close()


def test_close_timeout_is_visible_from_dashboard(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow(quiet_services())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    window._opened(Project.create(tmp_path / "Stopping", "Stopping"))
    with monkeypatch.context() as patcher:
        patcher.setattr(window.services, "shutdown", lambda _timeout: False)
        assert not window.close()
        assert window.welcome.isVisible()
        problem = window.findChild(QLabel, "welcomeProblem")
        assert problem is not None and "stopping" in problem.text()
    window.close()
