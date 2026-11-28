"""The shared label and busy-bar setup the views use (Deep Clean #1 step d)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QWidget
from pytestqt.qtbot import QtBot

from ctstudio.gui.views.plain import busy_bar, plain_label

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]

IGNORED = QSizePolicy.Policy.Ignored
SELECT = Qt.TextInteractionFlag.TextSelectableByMouse


def _parent(qtbot: QtBot) -> QWidget:
    parent = QWidget()
    qtbot.addWidget(parent)
    return parent


def test_a_plain_label_shows_its_text_as_typed_and_wraps(qtbot: QtBot) -> None:
    parent = _parent(qtbot)
    label = plain_label(parent, "probeLabel", "<b>not bold</b>")
    assert label.parent() is parent and label.objectName() == "probeLabel"
    assert label.text() == "<b>not bold</b>"
    assert label.textFormat() == Qt.TextFormat.PlainText and label.wordWrap()
    assert label.sizePolicy().horizontalPolicy() != IGNORED
    assert not label.textInteractionFlags() & SELECT


def test_fill_and_selectable_are_separate_choices(qtbot: QtBot) -> None:
    parent = _parent(qtbot)
    filled = plain_label(parent, "filled", fill=True)
    assert filled.sizePolicy().horizontalPolicy() == IGNORED
    assert filled.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Preferred
    assert not filled.textInteractionFlags() & SELECT
    chosen = plain_label(parent, "chosen", selectable=True)
    assert chosen.textInteractionFlags() & SELECT
    assert chosen.sizePolicy().horizontalPolicy() != IGNORED


def test_an_unnamed_label_keeps_qt_s_empty_name(qtbot: QtBot) -> None:
    parent = _parent(qtbot)
    label = plain_label(parent, text="message")
    assert label.objectName() == "" and label.text() == "message"


def test_busy_bars_show_activity_and_slim_ones_are_thin(qtbot: QtBot) -> None:
    parent = _parent(qtbot)
    bar = busy_bar(parent, "probeBusy")
    assert bar.parent() is parent and bar.objectName() == "probeBusy"
    assert (bar.minimum(), bar.maximum()) == (0, 0)
    assert bar.isTextVisible() and bar.maximumHeight() > 6
    slim = busy_bar(parent, "probeSlim", slim=True)
    assert (slim.minimum(), slim.maximum()) == (0, 0)
    assert not slim.isTextVisible() and slim.maximumHeight() == 6
