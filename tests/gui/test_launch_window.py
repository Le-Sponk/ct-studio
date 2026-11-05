"""P5-T03i: main-window launch routing, navigation guards, keyboard reach and screenshots."""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import pytest
from launch_controller_helpers import LaunchWork, outcome, services_with, writable_project
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QScrollArea
from pytestqt.qtbot import QtBot
from wizard_fakes import shot

from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
    raise AssertionError("A busy launch must not construct a wizard or browse a folder")


def launch_window(
    qtbot: QtBot, tmp_path: Path, *, source: bool = True
) -> tuple[MainWindow, Project, LaunchWork]:
    work = LaunchWork()
    services = services_with(work)
    view = MainWindow(services, new_project=forbidden, choose_folder=forbidden)
    qtbot.addWidget(view)
    view.resize(1000, 900)
    view.show()
    qtbot.waitUntil(lambda: not view.welcome.busy)
    project = writable_project(tmp_path, source=source)
    view._opened(project)
    qtbot.waitUntil(lambda: not view.dashboard.busy)
    return view, project, work


def close(view: MainWindow, work: LaunchWork) -> None:
    work.gate.set()
    assert outcome(view.close) is True
    assert view.services.project is None


def test_buttons_route_through_the_services_and_show_results(qtbot: QtBot, tmp_path: Path) -> None:
    view, project, work = launch_window(qtbot, tmp_path)
    page = view.dashboard
    page.open_blender.click()
    assert work.entered.wait(5)
    assert page.launch_notice.text() == "Opening Blender…"
    assert not view.new_project_action.isEnabled() and not view.home_action.isEnabled()
    work.gate.set()
    qtbot.waitUntil(lambda: not view.services.launch.busy)
    assert "process 123" in page.launch_notice.text()
    assert view.new_project_action.isEnabled() and view.home_action.isEnabled()
    page.cards["kcl"].reveal_action.trigger()
    qtbot.waitUntil(lambda: len(work.calls) == 2 and not view.services.launch.busy)
    assert work.calls[1][:2] == (project, "kcl")
    assert "Asked the system to open" in page.launch_notice.text()
    close(view, work)


def test_a_refusal_is_shown_without_starting(qtbot: QtBot, tmp_path: Path) -> None:
    view, _project, work = launch_window(qtbot, tmp_path, source=False)
    view._open_blender()  # the button is disabled; a direct call is still refused
    assert "no Blender source" in view.dashboard.launch_notice.text()
    assert not work.calls and not view.services.launch.busy
    close(view, work)


@pytest.mark.parametrize("action", ["new", "browse", "home"])
def test_navigation_is_refused_while_launching(qtbot: QtBot, tmp_path: Path, action: str) -> None:
    view, project, work = launch_window(qtbot, tmp_path)
    view.dashboard.open_blender.click()
    assert work.entered.wait(5)
    assert not view.open_project_action.isEnabled() and not view.dashboard_action.isEnabled()
    assert not view.welcome.isEnabled()
    {"new": view._new_project, "browse": view._browse, "home": view._go_home}[action]()
    assert view.pages.currentIndex() == 1
    assert view.services.project is project and not project.read_only
    close(view, work)


def test_closing_during_a_launch_waits_and_keeps_the_lock(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ctstudio.gui.main_window as main_window

    monkeypatch.setattr(main_window, "_SHUTDOWN_WAIT", 0.0)
    view, project, work = launch_window(qtbot, tmp_path)
    view.dashboard.open_blender.click()
    assert work.entered.wait(5)
    for _attempt in range(2):  # repeated refusals must not strand the dashboard
        assert outcome(view.close) is False  # refused: the worker still owns the project
        assert view.services.project is project and not project.read_only
        assert view.pages.currentIndex() == 1  # stays where the launch result will appear
        assert "still stopping" in view.dashboard.launch_notice.text()
    work.gate.set()
    qtbot.waitUntil(lambda: not view.services.launch.busy)
    assert "process" in view.dashboard.launch_notice.text()  # the result was shown
    assert not view.dashboard.busy, "a refused close left the dashboard checking"
    assert view.dashboard.refresh_button.isEnabled() and view.dashboard.open_blender.isEnabled()
    assert outcome(view.close) is True
    assert project.read_only


def test_dashboard_requests_are_ignored_while_editing(qtbot: QtBot, tmp_path: Path) -> None:
    view, _project, work = launch_window(qtbot, tmp_path)
    view.services.editing = True  # a details dialog owns the project
    try:
        view._open_blender()
        assert view.dashboard.launch_notice.text() == ""  # silent: the dialog is in charge
        assert not work.calls and not view.services.launch.busy
    finally:
        view.services.editing = False
    close(view, work)


def palette_dark(app: QApplication) -> QPalette:
    dark = QPalette(app.palette())
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
        dark.setColor(role, QColor("#202530"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text):
        dark.setColor(role, QColor("#f3f5f8"))
    dark.setColor(QPalette.ColorRole.ButtonText, QColor("#f3f5f8"))
    return dark


def test_launch_screenshots_light_dark_and_scaled(qtbot: QtBot, tmp_path: Path) -> None:
    view, _project, work = launch_window(qtbot, tmp_path)
    page = view.dashboard
    page.open_blender.click()
    assert work.entered.wait(5)
    shot(view, "p5-t03i-launching-light.png")
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    original, font = app.palette(), app.font()
    try:
        app.setPalette(palette_dark(app))
        work.gate.set()
        qtbot.waitUntil(lambda: not view.services.launch.busy)
        shot(view, "p5-t03i-launched-dark.png")
        app.setPalette(original)
        scaled = app.font()
        scaled.setPointSizeF(scaled.pointSizeF() * 1.5)
        app.setFont(scaled)
        view.resize(720, 480)
        QApplication.processEvents()
        row = page.open_blender.parentWidget()
        assert row is not None
        assert page.open_blender.geometry().right() <= page.width()
        shot(view, "p5-t03i-launched-small-150pct.png")
    finally:
        app.setPalette(original)
        app.setFont(font)
    close(view, work)


def test_keyboard_reaches_the_launch_controls_in_a_small_window(
    qtbot: QtBot, tmp_path: Path
) -> None:
    view, _project, work = launch_window(qtbot, tmp_path)
    page = view.dashboard
    view.resize(720, 480)
    page.edit_button.setFocus()
    qtbot.keyClick(page.edit_button, Qt.Key.Key_Tab)
    assert page.open_blender.hasFocus()
    qtbot.keyClick(page.open_blender, Qt.Key.Key_Space)
    assert work.entered.wait(5)
    work.gate.set()
    qtbot.waitUntil(lambda: not view.services.launch.busy)
    card = page.cards["posteffect"]
    for _ in range(40):  # Tab, as a user would, until the last card's More button
        focus = QApplication.focusWidget()
        if focus is card.more_button:
            break
        assert focus is not None
        qtbot.keyClick(focus, Qt.Key.Key_Tab)
    assert card.more_button.hasFocus()
    scroll = view.findChild(QScrollArea, "dashboardScroll")
    assert scroll is not None and scroll.verticalScrollBar().value() > 0
    menu = card.more_button.menu()
    assert menu is not None and card.reveal_action in menu.actions()
    assert card.reveal_action.isEnabled()
    close(view, work)
