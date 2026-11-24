"""P5-T08e1 local evidence: Settings → Advanced.

No project; a project whose reserved Wiimm arguments hold a long path that must wrap; the
note after a pick; and a damaged settings file with a long path; light/dark,
normal/enlarged. Also run on a real 800x600 screen (test_editors_small_screen). Pictures
stay in tests/artifacts/screens (git-ignored, never uploaded); fonts and palettes are
installed-font proxies.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from advanced_helpers import open_advanced, pick, project_with_args
from editor_request_helpers import settled
from outside_visual_helpers import visual_style
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from settings_visual_helpers import assert_readable, wrapped_fit
from settings_window_helpers import main_window, settings_dialog
from tools_fakes import FakeDoctor, doctor, settings_file
from wizard_fakes import SCREENS, shot

from ctstudio.core.project import settings

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
__all__ = ["doctor", "settings_file"]  # fixtures used by name
CASES = [
    ("none", False, False),
    ("project", True, True),
    ("project", False, False),
    ("picked", False, True),
    ("damaged", True, True),
]
LONG = ("onefoldernamewithnobreaks" * 4, "settings for CT Studio on this computer " * 2)
ARGUMENTS = ("--szs-dir", "C:\\" + "averylongfoldernamewithoutanybreaks" * 3, "--verbose")


@pytest.mark.parametrize(
    ("state", "dark", "enlarged"),
    CASES,
    ids=[f"{s}-{'dark' if d else 'light'}{'-big' if e else ''}" for s, d, e in CASES],
)
def test_advanced_pictures(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
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
    text = '{"format": 1, "show_tool_commands": 1}' if state == "damaged" else "{}"
    path.write_text(text, encoding="utf-8")
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    name = f"p5-t08e1-advanced-{state}-{'dark' if dark else 'light'}{'-big' if enlarged else ''}"
    with (
        visual_style(app, dark, enlarged),
        main_window(qtbot, doctor, settings_file) as (
            window,
            _preferences,
        ),
    ):
        if state in ("project", "damaged"):
            project = project_with_args(tmp_path, ARGUMENTS)
            window._opened(project)  # pyright: ignore[reportPrivateUsage]
            assert settled(qtbot, lambda: not window.dashboard.busy), "the dashboard hung"
        page = open_advanced(qtbot, window)
        dialog = settings_dialog(window)
        if state == "damaged":
            assert page.commands.banner.isVisible() and page.commands.combo.isHidden()
        else:
            assert page.commands.combo.isVisible()
        if state == "picked":
            pick(page, False)
            assert settled(qtbot, lambda: "Saved" in page.commands.note.text())
        if state in ("none", "project"):
            page.tabs.setCurrentWidget(page.project_tab)  # measured only when shown
            assert page.reserved.isVisible()
        assert settled(qtbot, lambda: wrapped_fit(dialog)), "the window never refitted"
        assert_readable(dialog)
        shot(dialog, f"{name}.png")
        dialog.resize(dialog.width(), 1)  # the user drags it as short as it goes
        QApplication.processEvents()
        assert_readable(dialog)
    assert (SCREENS / f"{name}.png").stat().st_size > 0
