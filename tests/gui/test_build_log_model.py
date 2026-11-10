"""Synthetic build output contracts for the bounded Qt list model."""

from functools import partial
from typing import cast

import pytest
from PySide6.QtCore import QModelIndex, QObject, QPersistentModelIndex, Qt

from ctstudio.core.build.events import LogLine
from ctstudio.gui.build_log_model import BuildLogModel, LogRole

pytestmark = pytest.mark.gui


def test_literal_roles_and_index_contract() -> None:
    parent = QObject()
    model = BuildLogModel(parent)
    model.append(LogLine("step", "$ <b>😀 & literal</b>"))
    index = model.index(0, 0)
    assert model.parent() is parent
    assert model.rowCount() == 1
    assert model.rowCount(index) == 0
    assert model.rowCount(QPersistentModelIndex(index)) == 0
    assert [int(role) for role in LogRole] == [257, 258, 259, 260]  # e33b added Command
    assert model.roleNames() == {
        int(LogRole.NodeId): b"nodeId",
        int(LogRole.Text): b"text",
        int(LogRole.Truncated): b"truncated",
        int(LogRole.Command): b"command",
    }
    for role in (
        Qt.ItemDataRole.DisplayRole,
        Qt.ItemDataRole.ToolTipRole,
        Qt.ItemDataRole.AccessibleTextRole,
    ):
        assert model.data(index, role) == "[step] $ <b>😀 & literal</b>"


def test_custom_roles_and_valid_flags() -> None:
    model = BuildLogModel()
    model.append(LogLine("step", "$ <b>😀 & literal</b>"))
    index = model.index(0, 0)
    assert model.data(QPersistentModelIndex(index), LogRole.Text) == "$ <b>😀 & literal</b>"
    assert model.data(index, LogRole.NodeId) == "step"
    assert model.data(index, LogRole.Truncated) is False
    assert model.data(index, LogRole.Command) is None  # tool output is never a command
    assert model.flags(index) == (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    assert model.data(index, Qt.ItemDataRole.EditRole) is None
    assert model.retained_chars == len("$ <b>😀 & literal</b>")
    assert model.dropped_rows == 0


def test_invalid_indexes_have_no_data_or_flags() -> None:
    model = BuildLogModel()
    model.append(LogLine("step", "literal"))
    foreign = BuildLogModel()
    foreign.append(LogLine("other", "text"))
    for invalid in (
        QModelIndex(),
        foreign.index(0, 0),
        model.createIndex(9, 0),
        model.createIndex(0, 1),
        QPersistentModelIndex(),
    ):
        assert model.data(invalid) is None
        assert model.flags(invalid) == Qt.ItemFlag.NoItemFlags


@pytest.mark.parametrize("key", ["max_rows", "max_chars", "max_line_chars"])
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "2", None])
def test_limits_reject_nonpositive_and_non_int(key: str, value: object) -> None:
    with pytest.raises(ValueError):
        BuildLogModel(
            max_rows=cast(int, value) if key == "max_rows" else 1,
            max_chars=cast(int, value) if key == "max_chars" else 1,
            max_line_chars=cast(int, value) if key == "max_line_chars" else 1,
        )


def test_truncation_limits_message_and_node_independently() -> None:
    model = BuildLogModel(max_rows=1, max_chars=5, max_line_chars=9)
    model.append(LogLine("N" * 100_000 + "😀", "hidden" * 100_000 + "abc😀"))
    index = model.index(0, 0)
    assert model.data(index, LogRole.Text) == "…abc😀"
    assert model.data(index, LogRole.NodeId) == "…" + "N" * 126 + "😀"
    assert model.data(index, LogRole.Truncated) is True
    assert model.retained_chars == 5
    assert model.dropped_rows == 0
    model.append(LogLine("short", "a"))
    assert model.data(model.index(0, 0), LogRole.Truncated) is False
    assert model.dropped_rows == 1
    model.append(LogLine("N" * 129, "a"))
    assert model.data(model.index(0, 0), LogRole.Truncated) is True
    assert model.data(model.index(0, 0), LogRole.Text) == "a"


@pytest.mark.parametrize(
    "raw, expected, truncated",
    [("", "", False), ("ab", "ab", False), ("abc", "abc", False), ("abcd", "…cd", True)],
)
def test_line_length_boundary(raw: str, expected: str, truncated: bool) -> None:
    model = BuildLogModel(max_line_chars=3)
    model.append(LogLine("n", raw))
    index = model.index(0, 0)
    assert model.data(index, LogRole.Text) == expected
    assert model.data(index, LogRole.Truncated) is truncated
    assert model.retained_chars == len(expected)


def test_one_character_cap_preserves_visible_truncation() -> None:
    tiny = BuildLogModel(max_chars=1, max_line_chars=1)
    tiny.append(LogLine("n", "😀x"))
    assert tiny.data(tiny.index(0, 0), LogRole.Text) == "…"


def test_notifications_persistent_indexes_and_clear() -> None:
    model = BuildLogModel(max_rows=3, max_chars=8)

    for text in ("a", "bb", "ccc"):
        model.append(LogLine("n", text))
    removed = QPersistentModelIndex(model.index(0, 0))
    survivor = QPersistentModelIndex(model.index(2, 0))
    seen: list[tuple[str, int, int, int, int, int]] = []

    def record(kind: str, parent: QModelIndex, first: int, last: int) -> None:
        assert not parent.isValid()
        seen.append((kind, first, last, model.rowCount(), model.retained_chars, model.dropped_rows))

    model.rowsAboutToBeRemoved.connect(partial(record, "before-remove"))
    model.rowsRemoved.connect(partial(record, "removed"))
    model.rowsAboutToBeInserted.connect(partial(record, "before-insert"))
    model.rowsInserted.connect(partial(record, "inserted"))
    model.modelAboutToBeReset.connect(partial(record, "before-reset", QModelIndex(), -1, -1))
    model.modelReset.connect(partial(record, "reset", QModelIndex(), -1, -1))
    model.append(LogLine("n", "DDDD"))
    assert seen == [
        ("before-remove", 0, 1, 3, 6, 0),
        ("removed", 0, 1, 1, 3, 2),
        ("before-insert", 1, 1, 1, 3, 2),
        ("inserted", 1, 1, 2, 7, 2),
    ]
    assert not removed.isValid()
    assert survivor.isValid() and survivor.row() == 0
    assert model.data(survivor, LogRole.Text) == "ccc"
    model.clear()
    assert seen[-2:] == [("before-reset", -1, -1, 2, 7, 2), ("reset", -1, -1, 0, 0, 0)]
    assert not survivor.isValid()
    model.append(LogLine("new", "reuse"))
    assert model.data(model.index(0, 0)) == "[new] reuse"
    assert model.retained_chars == 5 and model.dropped_rows == 0


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", [""]),
        ("\na", ["", "a"]),
        ("a\r\nb\rc\n", ["a", "b", "c", ""]),
        ("\r\r\n\n", ["", "", "", ""]),
        ("a\u2028b\v\f", ["a\u2028b\v\f"]),
    ],
)
def test_physical_rows_preserve_empty_and_literal_output(raw: str, expected: list[str]) -> None:
    model = BuildLogModel()
    inserted: list[tuple[int, int]] = []

    def record(_parent: QModelIndex, first: int, last: int) -> None:
        inserted.append((first, last))

    model.rowsInserted.connect(record)
    model.append(LogLine("step", raw))
    assert texts(model) == expected
    assert model.retained_chars == sum(map(len, expected))
    assert inserted == [(0, len(expected) - 1)]
    assert model.dropped_rows == 0


def texts(model: BuildLogModel) -> list[str | bool | None]:
    return [model.data(model.index(i, 0), LogRole.Text) for i in range(model.rowCount())]


@pytest.mark.parametrize("rows, chars, line", [(3, 100, 7), (20, 8, 5), (1, 1, 1)])
def test_burst_and_stream_keep_newest_under_both_caps(rows: int, chars: int, line: int) -> None:
    model = BuildLogModel(max_rows=rows, max_chars=chars, max_line_chars=line)
    expected: list[str] = []
    dropped = 0
    for raw in ["old\r\nbb\n😀😀\rccc\r\n", "x" * 100 + "END\nlast", "", "\n"] * 30:
        limit = min(chars, line)
        for text in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            expected.append(
                text if len(text) <= limit else "…" + text[-(limit - 1) :] if limit > 1 else "…"
            )
        while len(expected) > rows or sum(map(len, expected)) > chars:
            expected.pop(0)
            dropped += 1
        model.append(LogLine("n", raw))
        assert texts(model) == expected
        assert model.dropped_rows == dropped
        assert model.retained_chars == sum(map(len, expected))


def test_huge_event_allocations_are_bounded_before_splitting() -> None:
    import tracemalloc

    model = BuildLogModel(max_rows=4, max_chars=32, max_line_chars=8)
    raw = ("a\r\nb\rc\n" * 100_000) + "x" * 4_000_000 + "😀END\r\n"
    event = LogLine("node" * 1_000_000, raw)
    tracemalloc.start()
    try:
        model.append(event)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 500_000
    assert texts(model) == ["b", "c", "…xxx😀END", ""]
    assert model.dropped_rows == 299_998
    assert model.data(model.index(2, 0), LogRole.Truncated) is True
    assert model.retained_chars == 10


def test_stream_storage_does_not_retain_originals() -> None:
    import tracemalloc

    model = BuildLogModel(max_rows=17, max_chars=1000, max_line_chars=32)
    tracemalloc.start()
    try:
        for i in range(2000):
            model.append(LogLine("n" * 5000 + str(i), "x" * 5000 + str(i)))
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert current < 100_000 and peak < 300_000
    assert model.rowCount() == 17 and model.dropped_rows == 1983
    assert model.retained_chars == 17 * 32
    assert model.data(model.index(16, 0), LogRole.Text) == "…" + "x" * 27 + "1999"


def test_default_row_cap_and_line_cap() -> None:
    model = BuildLogModel()
    model.append(LogLine("n", "x\n" * 20_000))
    assert model.rowCount() == 20_000 and model.dropped_rows == 1
    model.clear()
    model.append(LogLine("n", "x" * 4097))
    assert model.retained_chars == 4096
    assert model.data(model.index(0, 0), LogRole.Text) == "…" + "x" * 4095
    model.clear()
    model.append(LogLine("n", ("x" * 4096 + "\n") * 489))
    assert model.rowCount() == 489 and model.dropped_rows == 1
    assert model.retained_chars == 1_998_848
