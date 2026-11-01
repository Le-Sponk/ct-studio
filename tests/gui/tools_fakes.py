"""Shared pieces of the Tools page GUI tests (P2-T07b): a recording doctor and finders."""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)
from pytestqt.qtbot import QtBot

from ctstudio.core.tools.doctor import Report, ToolCheck
from ctstudio.gui.services import ToolsService
from ctstudio.gui.views.tools_page import ToolsPage

SCREENS = Path(__file__).resolve().parents[2] / "tests" / "artifacts" / "screens"
WAIT = 10_000


class FakeDoctor:
    """Answers like ``diagnose``: a set wszst is found, otherwise it is missing."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.threads: list[threading.Thread] = []
        self.gate: threading.Event | None = None
        self.error: Exception | None = None

    def __call__(self, *, force: bool, configured: Mapping[str, Path]) -> Report:
        gate = self.gate  # read once: a test may swap it while this call waits
        self.calls.append({"force": force, "configured": dict(configured)})
        self.threads.append(threading.current_thread())
        if gate is not None:
            assert gate.wait(WAIT / 1000)
        if self.error is not None:
            raise self.error
        chosen = configured.get("wszst")
        wszst = (
            ToolCheck(
                "wszst",
                "Wiimms SZS Tool",
                "found",
                True,
                "SZS assembly",
                version="2.42a",
                path=chosen,
                launcher="direct",
                source="setting",
            )
            if chosen is not None
            else ToolCheck(
                "wszst",
                "Wiimms SZS Tool",
                "missing",
                True,
                "SZS assembly",
                fix="Install Wiimms SZS Tool from https://szs.wiimm.de/download.html.",
            )
        )
        blender = ToolCheck(
            "blender",
            "Blender",
            "found",
            False,
            "Authoring",
            version="4.5.3",
            path=Path("C:/Program Files/Blender é/blender.exe"),
            launcher="direct",
            source="standard",
        )
        wine = ToolCheck(
            "wine", "Wine", "not_needed", False, "Windows editors", note="Only used on Linux."
        )
        return Report("windows", (wszst, blender, wine))


@pytest.fixture
def doctor() -> FakeDoctor:
    return FakeDoctor()


@pytest.fixture
def settings_file(tmp_path: Path) -> Path:
    return tmp_path / "config é" / "settings.json"


@pytest.fixture
def opened() -> list[str]:
    return []


@pytest.fixture
def chosen() -> list[Path | None]:
    return []


def make_page(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> ToolsPage:
    service = ToolsService(settings_path=settings_file, diagnose=doctor)
    page = ToolsPage(
        service, choose_file=lambda _parent, _title: chosen.pop(0), open_url=opened.append
    )
    qtbot.addWidget(page)
    page.resize(900, 520)
    page.show()
    qtbot.waitUntil(lambda: not page.busy, timeout=WAIT)
    return page


def tools_table(page: ToolsPage) -> QTableWidget:
    table = page.findChild(QTableWidget, "toolsTable")
    assert table is not None
    return table


def button(page: ToolsPage, name: str) -> QPushButton:
    button = page.findChild(QPushButton, name)
    assert button is not None
    return button


def label(page: ToolsPage, name: str) -> QLabel:
    label = page.findChild(QLabel, name)
    assert label is not None
    return label


def item(page: ToolsPage, row: int, column: int) -> QTableWidgetItem:
    item = tools_table(page).item(row, column)
    assert item is not None
    return item


def rows(page: ToolsPage) -> list[tuple[str, str, str]]:
    return [
        (item(page, r, 0).text(), item(page, r, 1).text(), item(page, r, 2).text())
        for r in range(tools_table(page).rowCount())
    ]


def select(page: ToolsPage, tool_id: str) -> None:
    grid = tools_table(page)
    for row in range(grid.rowCount()):
        if item(page, row, 0).data(Qt.ItemDataRole.UserRole) == tool_id:
            grid.selectRow(row)
            return
    raise AssertionError(f"{tool_id} is not listed")


def shot(page: ToolsPage, name: str) -> None:
    QApplication.processEvents()  # let the layout follow the last change before the picture
    SCREENS.mkdir(parents=True, exist_ok=True)
    assert page.grab().save(str(SCREENS / name), "PNG")


def saved(settings_file: Path) -> dict[str, str]:
    return json.loads(settings_file.read_text(encoding="utf-8"))["tools"]


def busy_bar(page: ToolsPage) -> QProgressBar:
    bar = page.findChild(QProgressBar, "busyBar")
    assert bar is not None
    return bar
