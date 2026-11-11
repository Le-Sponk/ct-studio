"""P5-T06a screenshots: a part edited outside CT Studio, and the watching-stopped notice."""

# pyright: reportPrivateUsage=false
# The test opens the project the way the window does after the Open dialog.

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from test_component_mode_visual import dark_palette
from test_dashboard_watch import MODEL, made_project, real_services
from test_watcher_bridge import Watchers
from wizard_fakes import SCREENS, shot

from ctstudio.core.components.state import GENERATED_DIR
from ctstudio.core.errors import ProjectError
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.watcher_bridge import WatcherBridge

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def test_edited_outside_and_watch_notice_images(qtbot: QtBot, tmp_path: Path) -> None:
    watchers = Watchers()
    window = MainWindow(real_services(WatcherBridge(make=watchers)))
    qtbot.addWidget(window)
    window.resize(1100, 900)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    project = made_project(tmp_path)
    (project.root / GENERATED_DIR / MODEL).write_bytes(b"edited in BrawlCrate")
    window._opened(project)
    page = window.dashboard
    qtbot.waitUntil(lambda: not page.busy and not window.services.status.busy, timeout=10_000)
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    try:
        assert page.cards["course_model"].status_label.text() == "edited outside CT Studio"
        error = ProjectError(
            f"CT Studio cannot notice changes in {project.root} (The device is not ready).",
            hint="After changing files outside CT Studio, press Refresh statuses.",
        )
        watchers.made[-1].fail(error)
        qtbot.waitUntil(lambda: page.watch.notice.isVisible(), timeout=10_000)
        lines = page.watch.notice.fontMetrics().lineSpacing()
        assert page.watch.notice.height() >= 2 * lines, "the notice and its next step both show"
        shot(window, "p5-t06a-watch-light.png")
        original = dark_palette(app)
        try:
            shot(window, "p5-t06a-watch-dark.png")
        finally:
            app.setPalette(original)
        sizes = [(SCREENS / f"p5-t06a-watch-{n}.png").stat().st_size for n in ("light", "dark")]
        assert min(sizes) > 0
    finally:
        window.close()
