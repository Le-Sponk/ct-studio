"""Bounded, literal build output for a virtual Qt list view."""

import sys
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
from PySide6.QtGui import QFont

from ctstudio.core.build.events import CommandRun, LogLine

_ROOT_INDEX = QModelIndex()
# node, shown text, shortened, and for a trusted CommandRun only: its exact text when the row
# shows it whole, else "" (a command too long to copy here). None marks ordinary output.
type _Row = tuple[str, str, bool, str | None]
COPY_SHORTCUT = "Ctrl+Shift+C"
_RAN = "Ran: "


class LogRole(IntEnum):
    NodeId = Qt.ItemDataRole.UserRole + 1
    Text = Qt.ItemDataRole.UserRole + 2
    Truncated = Qt.ItemDataRole.UserRole + 3
    Command = Qt.ItemDataRole.UserRole + 4  # exact copy text; None unless a trusted command


def _command_form() -> str:
    if sys.platform == "win32":
        return (
            "A Windows command line for PowerShell (type & and a space first) or CreateProcess;"
            " not for cmd.exe, where % and unquoted & ^ | < > change its meaning."
        )
    return "A command line for a POSIX shell (sh, bash)."


def _command_tip(command: str) -> str:
    if not command:
        return (
            "This command is too long to copy from this list. The build log on disk has it in full."
        )
    return f"{_command_form()} Copy it with {COPY_SHORTCUT} or the right-click menu."


def _one_line(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "↵").replace("\n", "↵")


def _size(row: _Row) -> int:
    return len(row[1]) + len(row[3] or "")


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
    capped node ID. No source event or hidden original text is retained, except the exact
    text of a trusted command shown whole, which counts against the character budget too.
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
            LogRole.Command: QByteArray(b"command"),
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
    ) -> str | bool | QFont | None:
        if not self._valid(index):
            return None
        node, text, truncated, command = self._rows[self._head + index.row()]
        shown = f"[{node}] {text}"
        if command is not None and role == Qt.ItemDataRole.FontRole:
            bold = QFont()
            bold.setBold(True)  # only trusted rows; output that copies the "Ran:" wording is not
            return bold
        if command is not None and role == Qt.ItemDataRole.ToolTipRole:
            return f"{shown}\n\n{_command_tip(command)}"
        if command is not None and role == Qt.ItemDataRole.AccessibleTextRole:
            return f"Command run by {node}: {text.removeprefix(_RAN)}"
        if role in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.ToolTipRole,
            Qt.ItemDataRole.AccessibleTextRole,
        ):
            return shown
        values: dict[int, str | bool | None] = {
            LogRole.NodeId: node,
            LogRole.Text: text,
            LogRole.Truncated: truncated,
            LogRole.Command: command or None,
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
            chars -= _size(self._rows[self._head + removed])
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
            rows.append((node, text, truncated or len(event.node_id) > 128, None))
            chars += len(text)
        rows.reverse()
        return rows, total - len(rows)

    def _command(self, event: CommandRun) -> _Row:
        """One row for a trusted command; copyable only when shown whole within the budgets."""
        node = _tail(event.node_id, 128)
        text = _RAN + _one_line(event.text)
        fits = len(text) <= self._line_chars
        if not fits:
            text = text[: self._line_chars - 1] + "…"
        copyable = fits and len(text) + len(event.text) <= self._max_chars
        named = len(event.node_id) > 128
        return node, text, not fits or named, event.text if copyable else ""

    def append(self, event: LogLine | CommandRun) -> None:
        if isinstance(event, CommandRun):
            rows, omitted = [self._command(event)], 0
        else:
            rows, omitted = self._prepare(event)
        chars = sum(map(_size, rows))
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
