"""P5-T08b local evidence: Settings → Build with a project, without one and read-only (a long
project name), light/dark, normal/enlarged. Also run on a real 800x600 screen
(test_editors_small_screen).

Pictures stay in tests/artifacts/screens (git-ignored, never uploaded). Fonts and palettes
are installed-font proxies (see outside_visual_helpers); native Linux pixels are not shown.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from editor_owner_helpers import outcome
from editor_request_helpers import settled
from outside_visual_helpers import visual_style
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from settings_window_helpers import action, go, settings_dialog, shown_page
from test_build_window import Checks, no_tools
from test_settings_window_visual import assert_readable, wrapped_fit
from wizard_fakes import SCREENS, shot

from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
LONG_NAME = "A rather long project name for the Build page note " * 2
CASES = [
    ("project", False, False),
    ("project", True, False),
    ("project", False, True),
    ("project", True, True),
    ("none", False, True),
    ("read-only", True, True),
]


@contextmanager
def window_in(qtbot: QtBot, folder: Path, state: str) -> Generator[MainWindow]:
    services = AppServices(status=StatusService(evaluate=Checks().evaluate, find_tools=no_tools))
    window = MainWindow(services)
    qtbot.addWidget(window)
    window.show()
    holder = Project.create(folder / "Held", LONG_NAME.strip()) if state == "read-only" else None
    try:
        assert settled(qtbot, lambda: not window.welcome.busy), "the welcome check hung"
        if state != "none":
            opened = (
                Project.open(holder.root)
                if holder is not None
                else Project.create(folder / "Pictured é", "Pictured é")
            )
            window._opened(opened)  # pyright: ignore[reportPrivateUsage]
            assert settled(qtbot, lambda: not window.dashboard.busy), "the dashboard hung"
        yield window
    finally:
        stopped = outcome(lambda: services.shutdown(10))
        if holder is not None:
            holder.close()
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


@pytest.mark.parametrize(
    ("state", "dark", "enlarged"),
    CASES,
    ids=[f"{s}-{'dark' if d else 'light'}{'-big' if e else ''}" for s, d, e in CASES],
)
def test_build_page_pictures(
    qtbot: QtBot, tmp_path: Path, state: str, dark: bool, enlarged: bool
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    name = f"p5-t08b-build-{state}-{'dark' if dark else 'light'}{'-big' if enlarged else ''}"
    with visual_style(app, dark, enlarged), window_in(qtbot, tmp_path, state) as window:
        action(window, "settingsAction").trigger()
        dialog = settings_dialog(window)
        go(dialog, "Build")
        page = window.settings_window.build_page
        assert page is not None
        assert settled(qtbot, lambda: not page.busy and not page.jobs.busy)
        assert shown_page(dialog) == "Build"
        assert page.fields.isHidden() is (state == "none")
        if state == "read-only":
            assert "read-only" in page.blocked.text() and page.blocked.isVisible()
        if state == "project":
            page.d_copy.setChecked(False)  # Save and Undo on, as while editing
        assert settled(qtbot, lambda: wrapped_fit(dialog)), "the window never refitted"
        assert_readable(dialog)
        shot(dialog, f"{name}.png")
        dialog.resize(dialog.width(), 1)  # the user drags it as short as it goes
        QApplication.processEvents()
        assert_readable(dialog)
        page.undo()
    assert (SCREENS / f"{name}.png").stat().st_size > 0
