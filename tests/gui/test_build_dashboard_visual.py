"""P5-T03e22: actual dashboard build states in native/scaled light and dark windows."""

from pathlib import Path

import pytest
from build_fakes import FakeBuilds, summary
from build_window_helpers import build_window, finished, started
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QScrollArea
from pytestqt.qtbot import QtBot
from wizard_fakes import shot

from ctstudio.core.build.events import (
    BuildFinished,
    BuildStarted,
    NodeFailed,
    NodeSkipped,
    NodeStarted,
)
from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.components.status import ComponentStatus, State
from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.status_service import StatusResult

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def _palette(original: QPalette, dark: bool) -> QPalette:
    palette = QPalette(original)
    if dark:
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
            palette.setColor(role, QColor("#202530"))
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            for role in (
                QPalette.ColorRole.WindowText,
                QPalette.ColorRole.Text,
                QPalette.ColorRole.ButtonText,
                QPalette.ColorRole.PlaceholderText,
            ):
                palette.setColor(group, role, QColor("#f3f5f8"))
    return palette


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("scaled", [False, True], ids=["native", "font150"])
def test_integrated_build_dashboard_screenshots(
    qtbot: QtBot, tmp_path: Path, dark: bool, scaled: bool
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    old_palette, old_font = app.palette(), app.font()
    font = QFont(old_font)
    if scaled:
        font.setPointSizeF(old_font.pointSizeF() * 1.5)
    app.setPalette(_palette(old_palette, dark))
    app.setFont(font)
    try:
        with build_window(qtbot, tmp_path) as (view, project, fake):
            view.resize(720, 480) if scaled else view.resize(1280, 1200)
            _busy(qtbot, view, project, fake)
            _check_layout(view)
            name = f"{'dark' if dark else 'light'}-{'small-150' if scaled else 'native'}"
            shot(view, f"p5-t03e22-build-working-{name}.png")
            fake.events[-1] = BuildFinished(
                summary(
                    "failed",
                    ran=(),
                    skipped=("stage:course_model",),
                    failed=("stage:kcl",),
                    not_run=("assemble",),
                )
            )
            view.services.build.build_event.emit(
                NodeFailed(
                    "stage:kcl",
                    "Cannot read the collision source.",
                    "Check the chosen file.",
                    False,
                )
            )
            finished(qtbot, view, fake)
            _check_result_visible(view)
            shot(view, f"p5-t03e22-build-failed-{name}.png")
            assert "Check the chosen file" in view.dashboard.builds.controls.notice.text()
            assert "failed" in view.dashboard.builds.controls.last_result.text()
    finally:
        app.setPalette(old_palette)
        app.setFont(old_font)


def _busy(qtbot: QtBot, view: MainWindow, project: Project, fake: FakeBuilds) -> None:
    fake.events[0] = BuildStarted(("stage:course_model", "stage:kcl", "assemble"))
    view.services.status.updated.emit(
        StatusResult(
            project.root,
            {
                spec.id: ComponentStatus(State.READY, ("Last checked before this build.",))
                for spec in COMPONENTS
            },
        )
    )
    controls = view.dashboard.builds.controls
    controls.test_button.click()
    started(qtbot, view, fake)
    view.services.build.build_event.emit(NodeSkipped("stage:course_model"))
    view.services.build.build_event.emit(NodeStarted("stage:kcl"))
    view.services.build.notice.emit("Using the tools configured for this build.")
    assert controls.fontMetrics().inFontUcs4(ord("B"))
    assert view.dashboard.cards["kcl"].build_label.text() == "Build: working"
    assert view.dashboard.cards["kcl"].status_label.text() == "ready"


def _check_result_visible(view: MainWindow) -> None:
    viewport = _reveal_footer(view).viewport()
    controls = view.dashboard.builds.controls
    notice_top = controls.notice.mapTo(viewport, controls.notice.rect().topLeft())
    result_bottom = controls.last_result.mapTo(viewport, controls.last_result.rect().bottomLeft())
    assert viewport.rect().contains(notice_top)
    assert viewport.rect().contains(result_bottom)


def _reveal_footer(view: MainWindow) -> QScrollArea:
    QApplication.processEvents()
    scroll = view.findChild(QScrollArea, "dashboardScroll")
    assert scroll is not None
    scroll.ensureWidgetVisible(view.dashboard.builds.controls)
    QApplication.processEvents()
    return scroll


def _check_layout(view: MainWindow) -> None:
    scroll = _reveal_footer(view)
    controls = view.dashboard.builds.controls
    assert view.dashboard.width() <= scroll.viewport().width()
    assert controls.geometry().right() <= view.dashboard.width()
    assert controls.progress.maximum() == 3 and controls.progress.value() == 1
    for button in (controls.test_button, controls.release_button, controls.cancel_button):
        assert button.width() >= button.sizeHint().width()
    assert controls.cancel_button.isEnabled()
