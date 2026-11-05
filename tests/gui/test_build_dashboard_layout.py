"""The integrated header must accommodate wider desktop button-font metrics."""

from pathlib import Path

import pytest
from build_window_helpers import build_window, eventually
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QScrollArea
from pytestqt.qtbot import QtBot
from wizard_fakes import shot

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_wide_header_buttons_do_not_force_horizontal_scrolling(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with build_window(qtbot, tmp_path) as (view, _project, _fake):
        view.resize(720, 480)
        page = view.dashboard
        buttons = (page.refresh_button, page.copy_project, page.edit_button, page.open_blender)
        for button in buttons:
            font = QFont(button.font())
            font.setPointSizeF(font.pointSizeF() * 1.5)
            font.setStretch(120)
            button.setFont(font)
        QApplication.processEvents()
        eventually(
            qtbot,
            lambda: all(button.width() >= button.sizeHint().width() for button in buttons),
            "wide header labels remain clipped after layout",
        )
        scroll = view.findChild(QScrollArea, "dashboardScroll")
        assert scroll is not None
        assert page.width() <= scroll.viewport().width()
        for button in buttons:
            assert button.width() >= button.sizeHint().width()
            assert page.rect().contains(button.mapTo(page, button.rect().bottomRight()))
        assert scroll.horizontalScrollBar().maximum() == 0
        shot(view, "p5-t03e22-wide-header.png")
