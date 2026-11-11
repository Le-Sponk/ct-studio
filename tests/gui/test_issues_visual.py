"""P5-T05b screenshots: the Issues panel with the recorded check, light and dark."""

# pyright: reportPrivateUsage=false
# The window integration test uses its existing project-open completion slot.

from __future__ import annotations

from pathlib import Path

import pytest
from issues_helpers import finding, write_issues
from PySide6.QtWidgets import QApplication, QScrollArea
from pytestqt.qtbot import QtBot
from test_component_mode_visual import dark_palette
from test_new_project_window import quiet_services
from wizard_fakes import SCREENS, shot

from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def test_issues_panel_images(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(quiet_services())
    qtbot.addWidget(window)
    window.resize(1100, 900)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    project = Project.create(tmp_path / "Pistë 日本", "Pistë 日本")
    write_issues(project.root)
    window._opened(project)
    page = window.dashboard
    qtbot.waitUntil(lambda: not page.busy and not window.services.status.busy)
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    try:
        panel = page.issues
        panel.tree.setCurrentItem(finding(panel.tree, 3, 0))
        area = page.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        assert isinstance(area, QScrollArea), "the dashboard scrolls"
        area.ensureWidgetVisible(panel)
        QApplication.processEvents()
        lines = panel.detail.fontMetrics().lineSpacing()
        assert panel.detail.height() >= 2 * lines, "the next step is not squeezed"
        assert panel.tree.height() >= 6 * lines, "several findings show at once"
        shot(window, "p5-t05b-issues-light.png")
        original = dark_palette(app)
        try:
            shot(window, "p5-t05b-issues-dark.png")
        finally:
            app.setPalette(original)
        sizes = [
            (SCREENS / f"p5-t05b-issues-{name}.png").stat().st_size for name in ("light", "dark")
        ]
        assert min(sizes) > 0
    finally:
        window.close()
