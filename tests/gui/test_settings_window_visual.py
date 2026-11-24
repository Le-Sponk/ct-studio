"""P5-T08a local evidence: the Settings window at its Tools and Editors pages, light/dark,
normal/enlarged. Also run on a real 800x600 screen (test_editors_small_screen).

Pictures stay in tests/artifacts/screens (git-ignored, never uploaded). Fonts and palettes
are installed-font proxies (see outside_visual_helpers); native Linux pixels are not shown.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from editor_request_helpers import settled
from editor_settings_helpers import write_settings
from outside_visual_helpers import visual_style
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel
from pytestqt.qtbot import QtBot
from settings_visual_helpers import assert_list_readable, assert_readable, wrapped_fit
from settings_window_helpers import (
    action,
    go,
    main_window,
    page_list,
    settings_dialog,
    shown_page,
)
from tools_fakes import FakeDoctor, doctor, settings_file
from wizard_fakes import SCREENS, shot

from ctstudio.gui.settings_window import PAGES

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
__all__ = ["doctor", "settings_file"]  # fixtures used by name
CASES = [
    (page, dark, enlarged)
    for page in ("Tools", "Editors")
    for dark in (False, True)
    for enlarged in (False, True)
]


@pytest.mark.parametrize(
    ("page", "dark", "enlarged"),
    CASES,
    ids=[f"{p.lower()}-{'dark' if d else 'light'}{'-big' if e else ''}" for p, d, e in CASES],
)
def test_settings_window_pictures(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    page: str,
    dark: bool,
    enlarged: bool,
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    write_settings({"format": 1, "editor_preferences": {".kmp": "kmp_cloud"}})
    name = f"p5-t08a-{page.lower()}-{'dark' if dark else 'light'}{'-big' if enlarged else ''}"
    with (
        visual_style(app, dark, enlarged),
        main_window(qtbot, doctor, settings_file) as (
            window,
            _preferences,
        ),
    ):
        action(window, "toolsAction" if page == "Tools" else "editorsAction").trigger()
        dialog = settings_dialog(window)
        made = window.tools_window.page if page == "Tools" else window.editors_window.page
        assert made is not None
        assert settled(qtbot, lambda: not made.busy), "the page's first read never ended"
        assert settled(qtbot, lambda: wrapped_fit(dialog)), "the window never refitted"
        assert shown_page(dialog) == page
        assert_readable(dialog)
        shot(dialog, f"{name}.png")
        dialog.resize(dialog.width(), 1)  # the user drags it as short as it goes
        QApplication.processEvents()
        assert_readable(dialog)
    assert (SCREENS / f"{name}.png").stat().st_size > 0


@pytest.mark.parametrize(
    "folder",
    ["onefoldernamewithnobreaks" * 4, "a_long_folder_name_without_any_spaces_0123456789"],
    ids=["one-long-name", "underscored"],
)
def test_the_tools_page_banner_wraps_a_long_settings_path(
    qtbot: QtBot, doctor: FakeDoctor, tmp_path: Path, folder: str
) -> None:
    """The Tools page names a damaged settings file too; beside the page list at the
    enlarged font its path must wrap inside the screen width (P5-T08a repair). Height is not
    checked: on an 800x600 screen the Tools page with a very long path is taller than the
    screen (TD-022)."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    damaged = tmp_path / folder / "settings.json"
    damaged.parent.mkdir(parents=True)
    damaged.write_text("{damaged", encoding="utf-8")
    with visual_style(app, False, True), main_window(qtbot, doctor, damaged) as (window, _):
        action(window, "toolsAction").trigger()
        dialog = settings_dialog(window)
        tools = window.tools_window.page
        assert tools is not None
        assert settled(qtbot, lambda: not tools.busy), "the Tools check never ended"
        banners = [b for b in dialog.findChildren(QLabel, "settingsProblem") if b.isVisible()]
        assert len(banners) == 1 and "settings.json" in banners[0].text(), "no damaged-file banner"
        screen = dialog.screen().availableGeometry()
        assert dialog.width() <= screen.width(), f"{dialog.width()} > {screen.width()}"
        assert_list_readable(page_list(dialog))
        line = banners[0].fontMetrics().lineSpacing()
        assert banners[0].heightForWidth(banners[0].width()) > 2 * line, "the path did not wrap"


def test_every_page_fits_the_screen_width_with_a_wider_font(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    """Ubuntu's fonts are wider than the Windows ones these pictures use: with the page list
    beside them (as wide as "Appearance" since P5-T08d), the widest page must still leave the
    window inside an 800 px screen at the enlarged font. Segoe UI (Windows) is stretched a
    further 15% to stand in for Ubuntu's; any other font (DejaVu Sans on Linux) is measured
    as it is. The Tools
    page's button row set the width ("Open download page": 845 px on Windows, 829 with
    DejaVu)."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with (
        visual_style(app, False, True) as family,
        main_window(qtbot, doctor, settings_file) as (
            window,
            _preferences,
        ),
    ):
        if family == "Segoe UI":  # stand in for Ubuntu's wider font
            font = QFont(app.font())
            font.setStretch(font.stretch() * 115 // 100)
            app.setFont(font)
        action(window, "settingsAction").trigger()
        dialog = settings_dialog(window)
        for page in PAGES:
            go(dialog, page)
            QApplication.processEvents()
        screen = dialog.screen().availableGeometry()
        assert settled(qtbot, lambda: dialog.width() <= screen.width()), (
            f"{dialog.width()} > {screen.width()}"
        )
        assert_list_readable(page_list(dialog))
