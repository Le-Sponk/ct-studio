"""P5-T08d local evidence: Settings → Appearance (the colour scheme).

A saved scheme, the note after a pick, and a damaged settings file whose long path must wrap
inside the screen; light/dark, normal/enlarged. Also run on a real 800x600 screen
(test_editors_small_screen). The pictures' light/dark comes from the test palette, not from
Qt's colour-scheme request (the offscreen platform ignores it; see ``gui/appearance.py``).
Pictures stay in tests/artifacts/screens (git-ignored, never uploaded); fonts and palettes
are installed-font proxies.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from appearance_helpers import install_hints, open_appearance, pick
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
def test_appearance_pictures(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    dark: bool,
    enlarged: bool,
) -> None:
    install_hints(monkeypatch)
    path = tmp_path / LONG[0] / LONG[1].strip() / "settings.json"
    assert len(str(path)) > 200, "the path is not long enough to need wrapping"
    monkeypatch.setattr(settings, "default_path", lambda: path)
    path.parent.mkdir(parents=True)
    text = (
        '{"format": 1, "colour_scheme": 7}' if state == "damaged" else '{"colour_scheme": "dark"}'
    )
    path.write_text(text, encoding="utf-8")
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    name = f"p5-t08d-appearance-{state}-{'dark' if dark else 'light'}{'-big' if enlarged else ''}"
    with (
        visual_style(app, dark, enlarged),
        main_window(qtbot, doctor, settings_file) as (
            window,
            _preferences,
        ),
    ):
        page = open_appearance(qtbot, window)
        dialog = settings_dialog(window)
        if state == "damaged":
            assert page.banner.isVisible() and page.combo.isHidden()
        else:
            assert page.combo.isVisible() and page.combo.currentData() == "dark"
        if state == "picked":
            pick(page, "light")
            assert settled(qtbot, lambda: "Saved" in page.note.text())
        assert settled(qtbot, lambda: wrapped_fit(dialog)), "the window never refitted"
        assert_readable(dialog)
        shot(dialog, f"{name}.png")
        dialog.resize(dialog.width(), 1)  # the user drags it as short as it goes
        QApplication.processEvents()
        assert_readable(dialog)
    assert (SCREENS / f"{name}.png").stat().st_size > 0
