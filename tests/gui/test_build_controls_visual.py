"""Build bar reachability and native rendering before e22 dashboard integration."""

import os
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from pytestqt.qtbot import QtBot
from wizard_fakes import shot

from ctstudio.core.build.events import BuildStarted, NodeSkipped, NodeStarted
from ctstudio.gui.views.build_controls import BuildControls

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_tab_reaches_build_buttons_and_scrolls(qtbot: QtBot) -> None:
    area = QScrollArea()
    qtbot.addWidget(area)
    area.setWidgetResizable(True)
    content = QWidget()
    layout = QVBoxLayout(content)
    first = QPushButton("Earlier dashboard action")
    layout.addWidget(first)
    layout.addSpacing(500)
    controls = BuildControls()
    layout.addWidget(controls)
    area.setWidget(content)
    area.resize(720, 480)
    area.show()
    QApplication.processEvents()  # deliver show/activation before exercising native Tab routing
    controls.set_state(enabled=True, running=False)
    first.setFocus()
    QTest.keyClick(first, Qt.Key.Key_Tab)
    assert controls.test_button.hasFocus()
    QTest.keyClick(controls.test_button, Qt.Key.Key_Tab)
    assert controls.release_button.hasFocus()
    assert area.verticalScrollBar().value() > 0
    controls.begin(False)
    controls.set_state(enabled=False, running=True)
    first.setFocus()
    QTest.keyClick(first, Qt.Key.Key_Tab)
    assert controls.cancel_button.hasFocus()
    assert controls.cancel_button.isVisibleTo(area)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("scaled", [False, True], ids=["native", "font150"])
def test_minimum_build_bar_screenshots(
    qtbot: QtBot, tmp_path: Path, dark: bool, scaled: bool
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    old_palette, old_font = app.palette(), app.font()
    palette = QPalette(old_palette)
    if dark:
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
            palette.setColor(role, QColor("#202530"))
        for role in (
            QPalette.ColorRole.WindowText,
            QPalette.ColorRole.Text,
            QPalette.ColorRole.ButtonText,
            QPalette.ColorRole.PlaceholderText,
        ):
            palette.setColor(role, QColor("#f3f5f8"))
    font, added_font = _readable_font(old_font)
    if scaled:
        font.setPointSizeF(old_font.pointSizeF() * 1.5)
    app.setPalette(palette)
    app.setFont(font)
    try:
        _render(qtbot, tmp_path, dark, scaled)
    finally:
        app.setPalette(old_palette)
        app.setFont(old_font)
        if added_font is not None:
            QFontDatabase.removeApplicationFont(added_font)


def _readable_font(original: QFont) -> tuple[QFont, int | None]:
    """Windows offscreen Qt has no system font database; register a local OS font only."""
    font = QFont(original)
    if QFontDatabase.families():
        return font, None
    assert sys.platform == "win32", "Install system fonts before rendering screenshots."
    added = QFontDatabase.addApplicationFont(
        str(Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf")
    )
    assert added >= 0, "Could not load the local Windows Arial font."
    font.setFamily(QFontDatabase.applicationFontFamilies(added)[0])
    return font, added


def _assert_buttons_fit(controls: BuildControls) -> None:
    for button in (controls.test_button, controls.release_button, controls.cancel_button):
        assert button.width() >= button.sizeHint().width()
        assert button.geometry().right() <= controls.width()


def _assert_progress(controls: BuildControls) -> None:
    assert controls.progress.maximum() == 3
    assert controls.progress.value() == 1


def _render(qtbot: QtBot, tmp_path: Path, dark: bool, scaled: bool) -> None:
    area = QScrollArea()
    qtbot.addWidget(area)
    area.setWidgetResizable(True)
    controls = BuildControls()
    assert controls.fontMetrics().inFontUcs4(ord("B")), "screenshots need readable Latin glyphs"
    area.setWidget(controls)
    area.resize(720, 480)
    area.show()
    controls.begin(True)
    controls.set_state(enabled=False, running=True)
    controls.show_event(BuildStarted(("stage:kcl", "assemble", "validate")))
    controls.show_event(NodeSkipped("stage:kcl"))
    controls.show_event(NodeStarted("assemble"))
    warning = "Paths ignored for this build: " + str(tmp_path / ("long-path-" * 40))
    controls.show_notice(warning)
    suffix = f"{'dark' if dark else 'light'}-{'150' if scaled else 'native'}"
    shot(area, f"p5-t03e21-build-busy-{suffix}.png")
    assert controls.width() <= area.viewport().width()
    _assert_progress(controls)
    assert controls.notice.toolTip() == warning
    assert controls.notice.height() <= 4 * controls.notice.fontMetrics().lineSpacing() + 8
    _assert_buttons_fit(controls)
    controls.show_error(
        RuntimeError("Could not write the track. Check folder permissions, then retry.")
    )
    controls.set_state(enabled=True, running=False)
    shot(area, f"p5-t03e21-build-error-{suffix}.png")
    assert warning in controls.notice.text()
    assert controls.test_button.isEnabled()
