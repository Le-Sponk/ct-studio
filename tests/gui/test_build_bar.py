"""P5-T10b (owner decision D1): the build buttons stay in a bar pinned to the bottom of the
dashboard, outside the scrolling cards, so they are always on screen."""

from __future__ import annotations

from pathlib import Path

import pytest
from build_window_helpers import build_window, finished, started
from outside_visual_helpers import visual_style
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget
from pytestqt.qtbot import QtBot
from wizard_fakes import shot

from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]

SIZES = [(1280, 720), (800, 600)]


def on_screen(view: MainWindow, widget: QWidget) -> bool:
    """Whether the whole widget lies inside the window's visible area."""
    top_left = widget.mapTo(view, QPoint(0, 0))
    return widget.isVisible() and view.rect().contains(QRect(top_left, widget.size()))


def scroll_area(view: MainWindow) -> QScrollArea:
    area = view.findChild(QScrollArea, "dashboardScroll")
    assert area is not None
    return area


@pytest.mark.parametrize("enlarged", [False, True], ids=["normal", "enlarged"])
@pytest.mark.parametrize("size", SIZES, ids=["1280x720", "800x600"])
def test_the_build_buttons_are_on_screen_without_scrolling(
    qtbot: QtBot, tmp_path: Path, size: tuple[int, int], enlarged: bool
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with visual_style(app, False, enlarged), build_window(qtbot, tmp_path) as (view, _p, _f):
        view.resize(*size)
        QApplication.processEvents()
        controls = view.dashboard.builds.controls
        area = scroll_area(view)
        assert area.verticalScrollBar().value() == 0
        assert not area.isAncestorOf(controls), "the build buttons scroll with the cards"
        bar = view.dashboard_page.bar
        assert bar.geometry().top() >= area.geometry().bottom(), "the bar is not below the cards"
        for button in (controls.test_button, controls.release_button, controls.cancel_button):
            assert on_screen(view, button), f"{button.text()} is off screen at {size}"
        assert area.viewport().height() >= 150, "the cards have no room left"
        assert bar.height() <= 2 * controls.test_button.height() + 24, "an idle bar wastes room"
        shot(view, f"p5-t10b-bar-{size[0]}x{size[1]}{'-enlarged' if enlarged else ''}.png")


def test_a_long_build_message_leaves_room_for_the_cards(qtbot: QtBot, tmp_path: Path) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with visual_style(app, False, True), build_window(qtbot, tmp_path) as (view, _p, fake):
        view.resize(800, 600)
        controls = view.dashboard.builds.controls
        controls.test_button.click()
        started(qtbot, view, fake)
        finished(qtbot, view, fake)
        long = "Cannot read the collision source. " * 12
        controls.show_error(RuntimeError(f"{long}\nCheck the file and build again."))
        QApplication.processEvents()
        assert on_screen(view, controls.test_button)
        assert on_screen(view, controls.notice), "the message runs off the window"
        assert scroll_area(view).viewport().height() >= 150, "the message pushed the cards out"


def test_tab_reaches_the_build_bar_and_the_shortcuts_work(qtbot: QtBot, tmp_path: Path) -> None:
    with build_window(qtbot, tmp_path) as (view, _project, fake):
        view.resize(800, 600)
        QApplication.processEvents()
        page = view.dashboard
        page.edit_button.setFocus()
        target = page.builds.controls.release_button
        for _step in range(80):
            focus = QApplication.focusWidget()
            if focus is target:
                break
            assert focus is not None
            QTest.keyClick(focus, Qt.Key.Key_Tab)
        assert target.hasFocus(), "Tab never reached the build bar"
        QTest.keyClick(view, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
        started(qtbot, view, fake)
        assert fake.planned[0]["profile"] == "test"
        finished(qtbot, view, fake)


def test_the_bar_is_off_while_the_dashboard_is(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While the welcome page is busy (a check it started), the cards and the bar are off."""
    with build_window(qtbot, tmp_path) as (view, _project, _fake):
        controls = view.dashboard.builds.controls
        assert controls.isEnabled()
        welcome = type(view.welcome)
        monkeypatch.setattr(welcome, "busy", property(lambda _self: True))
        view.welcome.busy_changed.emit(True)
        assert not controls.isEnabled() and not view.dashboard.isEnabled()
        monkeypatch.setattr(welcome, "busy", property(lambda _self: False))
        view.welcome.busy_changed.emit(False)
        assert controls.isEnabled() and view.dashboard.isEnabled()
