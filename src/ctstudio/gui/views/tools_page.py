"""Settings → Tools (P2-T07b): which external tools are ready, and what to do about the rest.

Shows the doctor report as a table with a status chip per tool and, for the selected tool,
where it is, how it was found, the fix and any note. Browse… and Clear change the path
saved in the user's settings (P2-T07a), then check again; Re-check probes versions anew;
Open download page opens the tool's official page. Every check and save runs in a worker
thread (ARCHITECTURE §10) behind a busy bar, and only the newest check is shown. A damaged
settings file is shown in a banner and Browse/Clear stay off, so it is never overwritten.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.errors import CTStudioError
from ctstudio.core.tools.doctor import STATUS_LABELS, ToolCheck, found_how
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.gui.services import ToolsResult, ToolsService

_LOG = logging.getLogger(__name__)
ChooseFile = Callable[[QWidget, str], Path | None]
OpenUrl = Callable[[str], object]
_HEADERS = ("Tool", "Status", "Version", "Used for")
_CHIP_COLOURS = {"ok": "#3d9a40", "attention": "#c77700", "blocking": "#d32f2f"}
_CHIP_TIPS = {
    "ok": "Ready, or not used on this system.",
    "attention": "Optional: CT Studio works without it, with less. See the details below.",
    "blocking": "CT Studio needs this tool (required) to build tracks.",
}
_NO_SELECTION = "Select a tool to see where it is and what to do about it."


def _choose_file(parent: QWidget, title: str) -> Path | None:
    chosen, _filter = QFileDialog.getOpenFileName(parent, title)
    return Path(chosen) if chosen else None


def _open_url(url: str) -> bool:
    return QDesktopServices.openUrl(QUrl(url))


def chip(check: ToolCheck) -> str:
    """How urgent a row is: ``ok``, ``attention`` (optional, not ready) or ``blocking``."""
    if check.status in ("found", "not_needed"):
        return "ok"
    return "blocking" if check.required else "attention"


def details(check: ToolCheck) -> str:
    lines = [f"{check.name}: {STATUS_LABELS[check.status]}"]
    if check.path is not None:
        through = " through Wine" if check.launcher == "wine" else ""
        lines.append(f"Path: {check.path} (runs{through}; {found_how(check)})")
    if check.fix:
        lines.append(f"What to do: {check.fix}")
    if check.note:
        lines.append(f"Note: {check.note}")
    return "\n".join(lines)


class _Relay(QObject):
    """Carries a worker's result back to the UI thread (a queued signal)."""

    done = Signal(int, object)


class ToolsPage(QWidget):
    checked = Signal()  # a check (the newest one) finished and is shown

    def __init__(
        self,
        service: ToolsService,
        *,
        choose_file: ChooseFile = _choose_file,
        open_url: OpenUrl = _open_url,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.pool = QThreadPool(self)  # first child: deleted (and waited for) first
        self._relay = _Relay(self)
        self._relay.done.connect(self._finished)
        self._choose_file, self._open_url = choose_file, open_url
        self._latest = self._shown = 0
        self._result: ToolsResult | None = None
        self._build()
        self.recheck(force=False)

    # --- layout ---------------------------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            "CT Studio uses these programs. Choose where one is installed, or open its "
            "official download page.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self._banner = QLabel(self)
        self._banner.setObjectName("settingsProblem")
        self._banner.setWordWrap(True)
        self._banner.setFrameShape(QLabel.Shape.StyledPanel)
        self._banner.hide()
        layout.addWidget(self._banner)
        self._busy = QProgressBar(self)
        self._busy.setObjectName("busyBar")
        self._busy.setRange(0, 0)  # an activity bar: checks have no known length
        self._busy.setTextVisible(False)
        self._busy.setMaximumHeight(6)
        self._busy.hide()
        layout.addWidget(self._busy)
        layout.addWidget(self._make_table(), 1)
        self._details = QLabel(_NO_SELECTION, self)
        self._details.setObjectName("toolDetails")
        self._details.setWordWrap(True)
        self._details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._details.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lines = self._details.fontMetrics().lineSpacing()
        self._details.setMinimumHeight(4 * lines + 4)  # status, path, fix, note: no jumping
        layout.addWidget(self._details)
        layout.addLayout(self._make_buttons())

    def _make_table(self) -> QTableWidget:
        table = QTableWidget(0, len(_HEADERS), self)
        table.setObjectName("toolsTable")
        table.setHorizontalHeaderLabels(list(_HEADERS))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        header = table.horizontalHeader()
        for column in range(3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        table.itemSelectionChanged.connect(self._update)
        self._table = table
        return table

    def _make_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._browse = self._button("browseButton", "Browse…", self._browse_clicked, row)
        self._clear = self._button("clearButton", "Clear", self._clear_clicked, row)
        self._download = self._button(
            "downloadButton", "Open download page", self._download_clicked, row
        )
        row.addStretch(1)
        self._recheck = self._button(
            "recheckButton", "Re-check", lambda: self.recheck(force=True), row
        )
        return row

    def _button(
        self, name: str, text: str, slot: Callable[[], object], row: QHBoxLayout
    ) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName(name)
        button.clicked.connect(slot)
        row.addWidget(button)
        return button

    # --- actions --------------------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._shown != self._latest

    def recheck(self, *, force: bool) -> None:
        """Check every tool again in a worker; ``force`` re-runs the version probes."""
        self._start(lambda: self.service.check(force=force))

    def _browse_clicked(self) -> None:
        tool_id = self._selected()
        if tool_id is None:
            return
        path = self._choose_file(self, f"Choose {TOOL_BY_ID[tool_id].name}")
        if path is not None:
            self._start(lambda: self.service.set_path(tool_id, path))

    def _clear_clicked(self) -> None:
        tool_id = self._selected()
        if tool_id is not None:
            self._start(lambda: self.service.set_path(tool_id, None))

    def _download_clicked(self) -> None:
        tool_id = self._selected()
        if tool_id is not None:
            self._open_url(TOOL_BY_ID[tool_id].download_page)

    def _start(self, work: Callable[[], ToolsResult]) -> None:
        self._latest += 1
        generation, relay = self._latest, self._relay

        def job() -> None:
            payload: ToolsResult | Exception
            try:
                payload = work()
            except CTStudioError as exc:
                payload = exc
            except Exception as exc:  # any failure must reach the page, not die here
                _LOG.exception("The tool check failed")
                payload = exc
            relay.done.emit(generation, payload)

        self._update()
        self.pool.start(job)

    def _finished(self, generation: int, payload: object) -> None:
        if generation != self._latest:
            return  # an older check finished after a newer one started
        self._shown = generation
        if isinstance(payload, ToolsResult):
            self._show(payload)
        else:
            self._problem(_failure_text(payload))
        self._update()
        self.checked.emit()

    # --- showing --------------------------------------------------------------------------------

    def _show(self, result: ToolsResult) -> None:
        # Rows keep the registry's order, so the selected row stays on the same tool.
        self._result = result
        self._table.setRowCount(len(result.report.tools))
        for row, check in enumerate(result.report.tools):
            self._fill(row, check)
        self._problem(result.settings_problem)

    def _fill(self, row: int, check: ToolCheck) -> None:
        name = QTableWidgetItem(check.name)
        name.setData(Qt.ItemDataRole.UserRole, check.tool_id)
        status = QTableWidgetItem(STATUS_LABELS[check.status])
        level = chip(check)
        status.setData(Qt.ItemDataRole.UserRole, level)
        status.setForeground(QBrush(QColor(_CHIP_COLOURS[level])))
        status.setToolTip(_CHIP_TIPS[level])
        font = status.font()
        font.setBold(True)
        status.setFont(font)
        cells = (name, status, QTableWidgetItem(check.version or "-"))
        for column, item in enumerate((*cells, QTableWidgetItem(check.used_for))):
            self._table.setItem(row, column, item)

    def _problem(self, text: str | None) -> None:
        self._banner.setText(text or "")
        self._banner.setVisible(bool(text))

    def _selected(self) -> str | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    def _check_of(self, tool_id: str | None) -> ToolCheck | None:
        if tool_id is None or self._result is None:
            return None
        return next((c for c in self._result.report.tools if c.tool_id == tool_id), None)

    def _update(self) -> None:
        tool_id = self._selected()
        check = self._check_of(tool_id)
        self._details.setText(details(check) if check is not None else _NO_SELECTION)
        result = self._result
        editable = (
            not self.busy
            and tool_id is not None
            and result is not None
            and result.settings_problem is None
        )
        self._browse.setEnabled(editable)
        self._clear.setEnabled(editable and result is not None and tool_id in result.configured)
        self._download.setEnabled(tool_id is not None)
        self._recheck.setEnabled(not self.busy)
        self._busy.setVisible(self.busy)


def _failure_text(error: object) -> str:
    if isinstance(error, CTStudioError):
        return str(error)
    return f"CT Studio could not check the tools: {error}\nNext: Try Re-check again."
