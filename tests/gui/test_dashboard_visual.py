"""P5-T03b: native light/dark rendering, scroll reachability and keyboard actions."""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QScrollArea
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services
from wizard_fakes import shot

from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.components.status import ComponentStatus, State
from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.status_service import StatusResult

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def window(qtbot: QtBot, tmp_path: Path) -> MainWindow:
    view = MainWindow(quiet_services())
    qtbot.addWidget(view)
    view.resize(1000, 1000)
    view.show()
    qtbot.waitUntil(lambda: not view.welcome.busy)
    view._opened(Project.create(tmp_path / "Piste de Nuit é", "Piste de Nuit é"))
    qtbot.waitUntil(lambda: not view.dashboard.busy)
    return view


def sample(view: MainWindow) -> None:
    project = view.services.project
    assert project is not None
    states = (
        State.ERROR,
        State.MANUAL,
        State.STALE,
        State.EDITED_EXTERNALLY,
        State.MISSING,
        State.WARNING,
        State.READY,
        State.WARNING,
    )
    reasons = (
        "Configure Blender on the Tools page.",
        "Using your supplied collision file.",
        "Collision changed since this map was made.",
        "Review changes before rebuilding.",
        "No course data file chosen.",
        "Check the lighting settings.",
        "Object files are available.",
        "The author has not been set.",
    )
    view.services.status.updated.emit(
        StatusResult(
            project.root,
            {
                spec.id: ComponentStatus(state, (reason,))
                for spec, state, reason in zip(COMPONENTS, states, reasons, strict=True)
            },
        )
    )


def test_header_does_not_stretch_into_empty_space(qtbot: QtBot, tmp_path: Path) -> None:
    view = window(qtbot, tmp_path)
    page = view.dashboard
    assert page.access_label.height() <= 3 * page.access_label.fontMetrics().lineSpacing()
    assert page.notice.height() <= 3 * page.notice.fontMetrics().lineSpacing()
    view.close()


def test_native_dashboard_screenshots(qtbot: QtBot, tmp_path: Path) -> None:
    view = window(qtbot, tmp_path)
    sample(view)
    shot(view, "p5-t03b-dashboard-light.png")
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
        shot(view, "p5-t03b-dashboard-dark.png")
    finally:
        app.setPalette(original)
    view.services.status.failed.emit(RuntimeError("The project folder is temporarily unavailable."))
    shot(view, "p5-t03b-dashboard-error.png")
    view.dashboard.refresh()
    shot(view, "p5-t03b-dashboard-checking.png")
    view.close()


def test_tab_order_and_small_window_reach_every_available_component_action(
    qtbot: QtBot, tmp_path: Path
) -> None:
    view = window(qtbot, tmp_path)
    page = view.dashboard
    view.resize(720, 480)
    page.refresh_button.setFocus()
    qtbot.keyClick(page.refresh_button, Qt.Key.Key_Tab)
    assert page.copy_project.hasFocus()
    qtbot.keyClick(page.copy_project, Qt.Key.Key_Tab)
    assert page.edit_button.hasFocus()
    for card in page.cards.values():
        for button in (card.mode_button, card.copy_button, card.more_button):
            if button.isEnabled() and button.isVisible():
                focus = QApplication.focusWidget()
                assert focus is not None
                qtbot.keyClick(focus, Qt.Key.Key_Tab)
                assert button.hasFocus()
    scroll = view.findChild(QScrollArea, "dashboardScroll")
    assert scroll is not None and scroll.verticalScrollBar().value() > 0
    shot(view, "p5-t03b-dashboard-small.png")
    view.close()
