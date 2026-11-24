"""P5-T08c local evidence: Settings → Build, "This computer" (build steps at once).

A saved number with no project, the note after a save, and a damaged settings file whose long
path must wrap inside the screen; light/dark, normal/enlarged. Also run on a real 800x600
screen (test_editors_small_screen). Pictures stay in tests/artifacts/screens (git-ignored,
never uploaded); fonts and palettes are installed-font proxies.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from editor_request_helpers import settled
from outside_visual_helpers import visual_style
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from settings_window_helpers import action, go, settings_dialog
from test_build_page_visual import window_in
from test_settings_window_visual import assert_readable, wrapped_fit
from wizard_fakes import SCREENS, shot

from ctstudio.core.project import settings

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
CASES = [
    ("saved", False, False),
    ("saved", True, True),
    ("picked", False, True),
    ("damaged", True, True),
    ("damaged", False, False),
]
LONG = ("onefoldernamewithnobreaks" * 4, "settings for CT Studio on this computer " * 2)


@pytest.mark.parametrize(
    ("state", "dark", "enlarged"),
    CASES,
    ids=[f"{s}-{'dark' if d else 'light'}{'-big' if e else ''}" for s, d, e in CASES],
)
def test_build_jobs_pictures(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    dark: bool,
    enlarged: bool,
) -> None:
    path = tmp_path / LONG[0] / LONG[1].strip() / "settings.json"
    assert len(str(path)) > 200, "the path is not long enough to need wrapping"
    monkeypatch.setattr(settings, "default_path", lambda: path)
    path.parent.mkdir(parents=True)
    text = '{"format": 1, "build_jobs": 0}' if state == "damaged" else '{"build_jobs": 6}'
    path.write_text(text, encoding="utf-8")
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    name = f"p5-t08c-jobs-{state}-{'dark' if dark else 'light'}{'-big' if enlarged else ''}"
    with visual_style(app, dark, enlarged), window_in(qtbot, tmp_path, "none") as window:
        action(window, "settingsAction").trigger()
        dialog = settings_dialog(window)
        go(dialog, "Build")
        page = window.settings_window.build_page
        assert page is not None and settled(qtbot, lambda: not page.busy and not page.jobs.busy)
        page.tabs.setCurrentWidget(page.jobs)
        if state == "damaged":
            assert page.jobs.banner.isVisible() and page.jobs.combo.isHidden()
        else:
            assert page.jobs.combo.isVisible() and page.jobs.combo.currentData() == 6
        if state == "picked":
            page.jobs.combo.setCurrentIndex(page.jobs.combo.findData(2))
            page.jobs.combo.activated.emit(page.jobs.combo.currentIndex())
            assert settled(qtbot, lambda: "Saved" in page.jobs.note.text())
        assert settled(qtbot, lambda: wrapped_fit(dialog)), "the window never refitted"
        assert_readable(dialog)
        screen = dialog.screen().availableGeometry()
        assert dialog.width() <= screen.width(), f"{dialog.width()} > {screen.width()}"
        shot(dialog, f"{name}.png")
        dialog.resize(dialog.width(), 1)  # the user drags it as short as it goes
        QApplication.processEvents()
        assert_readable(dialog)
    assert (SCREENS / f"{name}.png").stat().st_size > 0
