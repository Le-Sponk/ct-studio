"""Bounded, literal build output for a virtual Qt list view."""

from collections.abc import Iterator
from enum import IntEnum

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from ctstudio.core.build.events import LogLine

_ROOT_INDEX = QModelIndex()
type _Row = tuple[str, str, bool]


class LogRole(IntEnum):
    NodeId = Qt.ItemDataRole.UserRole + 1
    Text = Qt.ItemDataRole.UserRole + 2
    Truncated = Qt.ItemDataRole.UserRole + 3


def _limit(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("Build log limits must be positive integers.")
    return value


def _tail(text: str, limit: int) -> str:
    return text if len(text) <= limit else "…" + text[len(text) - limit + 1 :]


def _line_spans(text: str, limit: int) -> Iterator[tuple[int, int]]:
    end = len(text)
    lf, cr = text.rfind("\n"), text.rfind("\r")
    for _ in range(limit):
        boundary = max(lf, cr)
        yield boundary + 1, end
        if boundary < 0:
            break
        end = cr if boundary == lf and cr >= 0 and cr == lf - 1 else boundary
        # Refresh only consumed cursors: repeatedly searching an absent kind is quadratic.
        if lf >= end:
            lf = text.rfind("\n", 0, end)
        if cr >= end:
            cr = text.rfind("\r", 0, end)


class BuildLogModel(QAbstractListModel):
    """Newest physical rows; character budgets count Python Unicode code points.

    Message caps include the visible truncation marker, but exclude the separately
    capped node ID. No source event or hidden original text is retained.
    """

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        max_rows: int = 20_000,
        max_chars: int = 2_000_000,
        max_line_chars: int = 4096,
    ) -> None:
        super().__init__(parent)
        self._max_rows = _limit(max_rows)
        self._max_chars = _limit(max_chars)
        self._line_chars = min(_limit(max_line_chars), self._max_chars)
        # Contiguous integer keys give O(1) lookup and head eviction, without list shifts.
        self._rows: dict[int, _Row] = {}
        self._head = 0
        self._chars = 0
        self._dropped = 0

    @property
    def retained_chars(self) -> int:
        return self._chars

    @property
    def dropped_rows(self) -> int:
        return self._dropped

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            LogRole.NodeId: QByteArray(b"nodeId"),
            LogRole.Text: QByteArray(b"text"),
            LogRole.Truncated: QByteArray(b"truncated"),
        }

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def _valid(self, index: QModelIndex | QPersistentModelIndex) -> bool:
        return (
            index.isValid()
            and index.model() is self
            and index.column() == 0
            and 0 <= index.row() < len(self._rows)
        )

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> str | bool | None:
        if not self._valid(index):
            return None
        node, text, truncated = self._rows[self._head + index.row()]
        if role in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.ToolTipRole,
            Qt.ItemDataRole.AccessibleTextRole,
        ):
            return f"[{node}] {text}"
        values: dict[int, str | bool] = {
            LogRole.NodeId: node,
            LogRole.Text: text,
            LogRole.Truncated: truncated,
        }
        return values.get(role)

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not self._valid(index):
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def _evict(self, incoming_rows: int, incoming_chars: int, drop_all: bool) -> None:
        count, chars = len(self._rows), self._chars
        removed = 0
        while count and (
            drop_all
            or count + incoming_rows > self._max_rows
            or chars + incoming_chars > self._max_chars
        ):
            chars -= len(self._rows[self._head + removed][1])
            removed += 1
            count -= 1
        if removed:
            self.beginRemoveRows(QModelIndex(), 0, removed - 1)
            for _ in range(removed):
                self._rows.pop(self._head)
                self._head += 1
            self._chars = chars
            self._dropped += removed
            self.endRemoveRows()

    def _prepare(self, event: LogLine) -> tuple[list[_Row], int]:
        # Count in C, then visit only the bounded newest tail on the GUI thread.
        total = 1 + event.text.count("\n") + event.text.count("\r") - event.text.count("\r\n")
        node = _tail(event.node_id, 128)
        rows: list[_Row] = []
        chars = 0
        for start, end in _line_spans(event.text, self._max_rows):
            truncated = end - start > self._line_chars
            # Bound the slice BEFORE allocation, including the visible ellipsis in the cap.
            if truncated:
                start = end - self._line_chars + 1
            text = ("…" if truncated else "") + event.text[start:end]
            if chars + len(text) > self._max_chars:
                break
            rows.append((node, text, truncated or len(event.node_id) > 128))
            chars += len(text)
        rows.reverse()
        return rows, total - len(rows)

    def append(self, event: LogLine) -> None:
        rows, omitted = self._prepare(event)
        chars = sum(len(row[1]) for row in rows)
        # An omitted incoming row also separates all old rows from the newest suffix.
        self._evict(len(rows), chars, bool(omitted))
        count = len(self._rows)
        self.beginInsertRows(QModelIndex(), count, count + len(rows) - 1)
        for offset, row in enumerate(rows):
            self._rows[self._head + count + offset] = row
        self._chars += chars
        self._dropped += omitted
        self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self._rows.clear()
        self._head = self._chars = self._dropped = 0
        self.endResetModel()
