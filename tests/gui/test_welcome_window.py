"""P5-T02b window navigation, saved history and reviewed light/dark welcome screenshots."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QListWidget, QPushButton
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services
from wizard_fakes import shot

from ctstudio.core.project import settings
from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.recent_projects import RecentProjects

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
WAIT = 10000


def make(qtbot: QtBot, file: Path, chosen: Path | None = None) -> MainWindow:
    window = MainWindow(
        quiet_services(), recent_projects=RecentProjects(file), choose_folder=lambda _parent: chosen
    )
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy, timeout=WAIT)
    return window


def action(window: MainWindow, name: str) -> QAction:
    found = window.findChild(QAction, name)
    assert found is not None
    return found


def test_open_menu_remembers_project_and_restart_can_open_recent(
    qtbot: QtBot, tmp_path: Path
) -> None:
    root = tmp_path / "Ma piste é"
    Project.create(root, "Ma piste é").close()
    file = tmp_path / "settings.json"
    window = make(qtbot, file, root)
    with qtbot.waitSignal(window.welcome.opened, timeout=WAIT):
        action(window, "openProjectAction").trigger()
    assert window.windowTitle() == "Ma piste é — CT Studio"
    project = window.services.project
    assert project is not None and not project.read_only
    # Opening the same current project again must not acquire a read-only duplicate.
    with qtbot.waitSignal(window.welcome.opened, timeout=WAIT):
        action(window, "openProjectAction").trigger()
    assert window.services.project is project and not project.read_only
    window.close()
    restarted = make(qtbot, file)
    listed = restarted.findChild(QListWidget, "recentProjects")
    button = restarted.findChild(QPushButton, "openRecent")
    assert listed is not None and button is not None
    assert listed.count() == 1
    listed.setCurrentRow(0)
    with qtbot.waitSignal(restarted.welcome.opened, timeout=WAIT):
        button.click()
    current = restarted.services.project
    assert current is not None and current.root == root
    assert settings.load(file).other["recent_projects"] == [str(root.resolve())]


def test_invalid_open_does_not_replace_current_project(qtbot: QtBot, tmp_path: Path) -> None:
    root = tmp_path / "Valid"
    original = Project.create(root, "Valid")
    window = make(qtbot, tmp_path / "settings.json", tmp_path / "Absent")
    window.services.adopt(original)
    with qtbot.waitSignal(window.welcome.checked, timeout=WAIT):
        action(window, "openProjectAction").trigger()
    assert window.services.project is original and not original.read_only
    problem = window.findChild(QLabel, "welcomeProblem")
    assert problem is not None and problem.text()
    assert RecentProjects(tmp_path / "settings.json").check().entries == ()


def test_project_open_elsewhere_is_clearly_read_only(qtbot: QtBot, tmp_path: Path) -> None:
    root = tmp_path / "Held"
    with Project.create(root, "Held"):
        window = make(qtbot, tmp_path / "settings.json", root)
        with qtbot.waitSignal(window.welcome.opened, timeout=WAIT):
            action(window, "openProjectAction").trigger()
        title = window.findChild(QLabel, "emptyTitle")
        assert title is not None and "read-only" in title.text()
        current = window.services.project
        assert current is not None and current.read_only


def test_welcome_screenshots(qtbot: QtBot, tmp_path: Path) -> None:
    file = tmp_path / "settings.json"
    window = make(qtbot, file)
    shot(window, "p5-t02b-welcome-empty.png")
    history = RecentProjects(file)
    history.remember(tmp_path / "Missing project")
    root = tmp_path / "Piste des Neiges é"
    Project.create(root, "Piste des Neiges é").close()
    history.remember(root)
    with qtbot.waitSignal(window.welcome.checked, timeout=WAIT):
        window.welcome.refresh()
    listed = window.findChild(QListWidget, "recentProjects")
    assert listed is not None
    listed.setCurrentRow(1)
    shot(window, "p5-t02b-welcome-recent.png")
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    original = app.palette()
    dark = QPalette(original)
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
        dark.setColor(role, QColor("#202530"))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        dark.setColor(role, QColor("#f3f5f8"))
    app.setPalette(dark)
    try:
        shot(window, "p5-t02b-welcome-dark.png")
    finally:
        app.setPalette(original)
    file.write_text("broken", encoding="utf-8")
    with qtbot.waitSignal(window.welcome.checked, timeout=WAIT):
        window.welcome.refresh()
    shot(window, "p5-t02b-welcome-settings-error.png")


def test_busy_startup_disables_menus_and_close_waits(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from test_welcome_page import History

    from ctstudio.gui import main_window

    history = History()
    history.gate = threading.Event()
    window = MainWindow(quiet_services(), recent_projects=history)
    qtbot.addWidget(window)
    window.show()
    try:
        assert not action(window, "newProjectAction").isEnabled()
        assert not action(window, "openProjectAction").isEnabled()
        shot(window, "p5-t02b-welcome-busy.png")
        monkeypatch.setattr(main_window, "_SHUTDOWN_WAIT", 0)
        assert not window.close()
        assert window.isVisible()
    finally:
        history.gate.set()
        qtbot.waitUntil(lambda: not window.welcome.busy, timeout=WAIT)
    assert action(window, "newProjectAction").isEnabled()
    assert action(window, "openProjectAction").isEnabled()
    assert window.close()
