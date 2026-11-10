"""P5-T04b: the window keeps the project while an assignment runs, then shows its result."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from assign_helpers import AssignWork, assign_services, drop, kcl_bytes, local, write
from pytestqt.qtbot import QtBot

from ctstudio.core.project.project import Project
from ctstudio.gui import main_window
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def window_for(qtbot: QtBot, folder: Path, work: AssignWork) -> tuple[MainWindow, Project]:
    window = MainWindow(assign_services(work))
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    project = Project.create(folder / "Fenêtre 日本", "Fenêtre")
    window._opened(project)
    qtbot.waitUntil(lambda: not window.dashboard.busy)
    return window, project


def menu_state(window: MainWindow) -> tuple[bool, bool, bool]:
    return (
        window.open_project_action.isEnabled(),
        window.new_project_action.isEnabled(),
        window.home_action.isEnabled(),
    )


def assert_close_refused(window: MainWindow, project: Project) -> None:
    for _attempt in range(2):
        closed = window.close()
        assert (closed, window.pages.currentIndex()) == (False, 1)
        assert project.lock is not None
        assert "still stopping" in window.dashboard.launch_notice.text()


def test_close_waits_for_an_assignment_and_keeps_the_dashboard(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_window, "_SHUTDOWN_WAIT", 0.0)
    work = AssignWork()
    work.gate = threading.Event()
    window, project = window_for(qtbot, tmp_path, work)
    card = window.dashboard.cards["kcl"]
    try:
        assert drop(card, local(write(tmp_path / "mine.kcl", kcl_bytes())))
        assert window.services.launch.busy
        assert menu_state(window) == (False, False, False)
        assert_close_refused(window, project)
        window._edit_project()
        window._edit_component("kcl", "manual")
        assert window._details is None, "no editor opens while assigning"
        work.gate.set()
        qtbot.waitUntil(lambda: not window.services.launch.busy and not window.dashboard.busy)
        assert project.manifest.components.kcl.file == "files/course.kcl"
        assert card.assign_note.text().startswith("Now using files/course.kcl")
        assert menu_state(window) == (True, True, True)
    finally:
        work.gate.set()
        qtbot.waitUntil(lambda: not window.services.launch.busy)
        assert window.close()
    assert project.lock is None


def test_a_result_for_a_project_no_longer_shown_is_not_published(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = AssignWork()
    work.gate = threading.Event()
    window, project = window_for(qtbot, tmp_path, work)
    manifest = project.manifest
    try:
        assert drop(window.dashboard.cards["kcl"], local(write(tmp_path / "a.kcl", kcl_bytes())))
        window.services.project = None  # the project is no longer the current one
        work.gate.set()
        qtbot.waitUntil(lambda: not window.services.launch.busy)
        assert project.manifest is manifest
        assert window.dashboard.cards["kcl"].mode_label.text() == "Mode: auto"
    finally:
        work.gate.set()
        window.services.project = project
        qtbot.waitUntil(lambda: not window.services.launch.busy)
        assert window.close()
