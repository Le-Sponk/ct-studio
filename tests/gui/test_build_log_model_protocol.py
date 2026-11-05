"""Exercise the log as a real view's model, not just a Python container."""

from __future__ import annotations

from typing import Protocol

import pytest
from PySide6.QtCore import QAbstractItemModel, QPersistentModelIndex
from PySide6.QtWidgets import QListView
from pytestqt.qtbot import QtBot

from ctstudio.core.build.events import LogLine
from ctstudio.gui.build_log_model import BuildLogModel, LogRole

pytestmark = pytest.mark.gui


class ModelChecks(Protocol):
    def check(self, model: QAbstractItemModel, force_py: bool = False) -> None: ...


def test_native_view_keeps_surviving_selection(qtbot: QtBot) -> None:
    model = BuildLogModel(max_rows=4)
    view = QListView()
    qtbot.addWidget(view)
    view.setModel(model)
    view.show()
    model.append(LogLine("stage:kmp", "zero\none\ntwo"))
    view.setCurrentIndex(model.index(1, 0))
    kept = QPersistentModelIndex(view.currentIndex())
    model.append(LogLine("stage:kmp", "three\nfour"))
    assert kept.isValid() and kept.row() == 0
    assert view.currentIndex().data(LogRole.Text) == "one"
    selection = view.selectionModel()
    assert selection is not None
    assert selection.selectedIndexes() == [model.index(0, 0)]
    model.append(LogLine("stage:kmp", "five"))
    assert not kept.isValid()
    model.clear()
    assert not view.currentIndex().isValid()
    assert selection.selectedIndexes() == []
    model.append(LogLine("stage:kmp", "reused"))
    assert view.model() is model
    assert model.index(0, 0).data(LogRole.Text) == "reused"


def test_qt_model_protocol_and_reference_history(qtmodeltester: ModelChecks) -> None:
    model = BuildLogModel(max_rows=7, max_chars=36, max_line_chars=6)
    qtmodeltester.check(model, force_py=True)
    expected: list[tuple[str, bool]] = []
    dropped = 0
    for i in range(80):
        original = ["", "𐐀é literal", "<b>x</b>"][: i % 3 + 1]
        text = ("\r\n" if i % 2 else "\r").join(original)
        dropped += _push_expected(expected, original)
        model.append(LogLine("stage:kmp", text))
        _assert_history(model, expected, dropped)
    model.clear()
    assert model.rowCount() == model.retained_chars == model.dropped_rows == 0
    model.append(LogLine("stage:kmp", ""))
    assert model.index(0, 0).data(LogRole.Text) == ""


def _push_expected(expected: list[tuple[str, bool]], original: list[str]) -> int:
    for line in original:
        expected.append(("…" + line[-5:] if len(line) > 6 else line, len(line) > 6))
    dropped = 0
    while len(expected) > 7 or sum(len(t) for t, _ in expected) > 36:
        expected.pop(0)
        dropped += 1
    return dropped


def _assert_history(model: BuildLogModel, expected: list[tuple[str, bool]], dropped: int) -> None:
    actual = [
        (model.index(r, 0).data(LogRole.Text), model.index(r, 0).data(LogRole.Truncated))
        for r in range(model.rowCount())
    ]
    assert actual == expected
    assert model.dropped_rows == dropped
    assert model.retained_chars == sum(len(t) for t, _ in expected)
