"""Enlarged native mode labels must not push dashboard cards beyond half-width."""

from pathlib import Path

import pytest
from build_window_helpers import build_window
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QScrollArea
from pytestqt.qtbot import QtBot

from ctstudio.gui.views.component_card import ComponentCard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def _assert_complete_mode_controls(card: ComponentCard) -> None:
    mode = card.mode_label
    assert mode.width() >= mode.sizeHint().width()
    assert card.rect().contains(mode.mapTo(card, mode.rect().bottomRight()))
    if not card.mode_button.isHidden():
        assert card.mode_button.width() >= card.mode_button.sizeHint().width()
        assert card.rect().contains(
            card.mode_button.mapTo(card, card.mode_button.rect().bottomRight())
        )
        assert mode.mapTo(card, mode.rect().bottomLeft()).y() < card.mode_button.y()


def test_wide_mode_row_keeps_full_labels_and_dashboard_width(qtbot: QtBot, tmp_path: Path) -> None:
    with build_window(qtbot, tmp_path) as (window, _project, _fake):
        window.resize(720, 480)
        for card in window.dashboard.cards.values():
            font = QFont(card.font())
            font.setPointSizeF(font.pointSizeF() * 1.5)
            font.setStretch(160)
            card.setFont(font)
        QApplication.processEvents()
        QApplication.processEvents()
        area = window.findChild(QScrollArea, "dashboardScroll")
        assert area is not None
        assert area.horizontalScrollBar().maximum() == 0
        assert window.dashboard.width() <= area.viewport().width()
        for card in window.dashboard.cards.values():
            _assert_complete_mode_controls(card)
        assert window.dashboard.cards["posteffect"].mode_label.text() == "Mode: template"
        layout = window.dashboard.layout()
        assert layout is not None
        assert layout.alignment() == Qt.AlignmentFlag.AlignTop
