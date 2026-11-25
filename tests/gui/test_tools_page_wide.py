"""P5-T10i: Settings → Tools with wide fonts (TD-022 core) and its pictures (TD-007).

The Tools page's buttons sit in two rows, so the page fits an 800 px screen even with a
font stretched to 132 %; Tab leaves the tools table instead of walking its cells; every
cell that can be shortened with "…" shows its whole text in a tooltip. Pictures of the full
tool list (every tool CT Studio knows) at 1280x720, normal and enlarged, go to
tests/artifacts/screens (git-ignored).
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest
from editor_request_helpers import settled
from outside_visual_helpers import visual_style
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QStyle, QTableWidget
from pytestqt.qtbot import QtBot
from settings_window_helpers import action, go, main_window, settings_dialog
from tools_fakes import FakeDoctor, doctor, settings_file
from wide_font_helpers import WIDE, wide_font
from wizard_fakes import shot

from ctstudio.core.tools.doctor import Report, ToolCheck
from ctstudio.core.tools.registry import TOOL_SPECS
from ctstudio.gui.views.tools_page import ToolsPage

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
__all__ = ["doctor", "settings_file"]  # fixtures used by name


class FullDoctor(FakeDoctor):
    """Every tool CT Studio knows, alternately found (with version and path) and missing:
    the longest names and "Used for" texts the list can show."""

    def __call__(self, *, force: bool, configured: Mapping[str, Path]) -> Report:
        super().__call__(force=force, configured=configured)
        checks = tuple(
            ToolCheck(
                spec.id,
                spec.name,
                "found",
                False,
                spec.used_for,
                version="1.0",
                path=Path("C:/Programs") / spec.id,
                source="search",
            )
            if index % 2
            else ToolCheck(
                spec.id, spec.name, "missing", True, spec.used_for, fix=f"Install {spec.name}."
            )
            for index, spec in enumerate(TOOL_SPECS)
        )
        return Report("windows", checks)


def shown(table: QTableWidget, row: int, column: int) -> float:
    """How much of the cell's text Qt has room for (its own margins and the cell's font):
    1 or more when the whole text is drawn, less when Qt cuts it with "…"."""
    item = table.item(row, column)
    assert item is not None
    style = table.style()
    margin = style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, table) + 1
    room = table.visualItemRect(item).width() - 2 * margin
    metrics = QFontMetrics(item.font())
    if metrics.elidedText(item.text(), Qt.TextElideMode.ElideRight, room) == item.text():
        return 1.0
    return room / metrics.horizontalAdvance(item.text())


@contextmanager
def tools_page(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> Generator[tuple[QDialog, QTableWidget]]:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        action(window, "settingsAction").trigger()
        dialog = settings_dialog(window)
        go(dialog, "Tools")
        table = dialog.findChild(QTableWidget, "toolsTable")
        assert table is not None
        assert settled(qtbot, lambda: table.rowCount() > 0), "the list never filled"
        yield dialog, table


def test_tab_leaves_the_tools_table(qtbot: QtBot, doctor: FakeDoctor, settings_file: Path) -> None:
    with tools_page(qtbot, doctor, settings_file) as (dialog, table):
        dialog.activateWindow()
        table.setFocus()
        table.setCurrentCell(0, 0)
        QApplication.processEvents()
        assert QApplication.focusWidget() is table
        QTest.keyClick(table, Qt.Key.Key_Tab)
        focus = QApplication.focusWidget()
        assert focus is not table, "Tab walked into the next cell"
        assert focus is not None and focus.objectName() == "browseButton", focus
        assert table.currentRow() == 0 and table.currentColumn() == 0


def test_every_cell_shows_its_whole_text_in_a_tooltip(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with tools_page(qtbot, doctor, settings_file) as (_dialog, table):
        for row in range(table.rowCount()):
            for column in (0, 2, 3):  # name, version, used for (status keeps its own tip)
                item = table.item(row, column)
                assert item is not None and item.toolTip() == item.text(), (row, column)
            status = table.item(row, 1)
            assert status is not None and status.toolTip() not in ("", status.text()), row


@pytest.mark.parametrize("stretch", WIDE)
def test_the_tools_page_fits_800_px_with_a_wide_font(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, stretch: int
) -> None:
    with wide_font(stretch), tools_page(qtbot, doctor, settings_file) as (dialog, _table):
        QApplication.processEvents()
        need = dialog.minimumSizeHint().width()  # what the page needs, not the screen's cap
        assert need <= 800, f"{need} px > 800 at {stretch} %"
        assert settled(qtbot, lambda: dialog.width() <= 800), f"{dialog.width()} > 800"
        shot(dialog, f"p5-t10i-tools-wide-{stretch}.png")


def test_the_selected_tool_stays_in_view_when_the_window_shrinks(
    qtbot: QtBot, settings_file: Path
) -> None:
    """A tool chosen from elsewhere (Open in…'s "Set up…") is scrolled into view; when the
    window then gets shorter (the taller two-row buttons, a small screen), it must stay
    there. Ubuntu CI caught the row scrolled out (P5-T10i)."""
    with tools_page(qtbot, FullDoctor(), settings_file) as (dialog, table):
        assert settled(qtbot, lambda: table.rowCount() == len(TOOL_SPECS))
        page = dialog.findChild(ToolsPage)
        assert page is not None
        dialog.resize(1000, 900)
        qtbot.waitUntil(lambda: table.viewport().height() > 0)
        page.select(TOOL_SPECS[-1].id)
        row = table.selectionModel().selectedRows()[0].row()
        dialog.resize(1000, dialog.minimumSizeHint().height())

        def in_view() -> bool:
            cell = table.visualRect(table.model().index(row, 0))
            return table.viewport().rect().contains(cell)

        assert settled(qtbot, in_view), "the selected tool is scrolled out of view"


@pytest.mark.parametrize("enlarged", [False, True], ids=["normal", "enlarged"])
def test_tools_pictures_at_1280x720(qtbot: QtBot, settings_file: Path, enlarged: bool) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with (
        visual_style(app, False, enlarged),
        tools_page(qtbot, FullDoctor(), settings_file) as (dialog, table),
    ):
        assert settled(qtbot, lambda: table.rowCount() == len(TOOL_SPECS))
        dialog.resize(1280, 720)
        fits = lambda: table.horizontalScrollBar().maximum() == 0  # noqa: E731
        assert settled(qtbot, fits), "the list scrolls sideways"
        cut = {
            (row, column): round(fraction, 2)
            for row in range(table.rowCount())
            for column in range(4)
            if (fraction := shown(table, row, column)) < 1
        }
        # Tool, status and version size to their text; only "Used for" may give way: with
        # the enlarged font on Linux it loses some pixels (89-99 % shown), and then its
        # tooltip has the whole text. A squeezed or fixed-width column shows far less.
        assert all(column == 3 for _row, column in cut), cut
        assert all(fraction >= 0.75 for fraction in cut.values()), cut
        shot(dialog, f"p5-t10i-tools-1280x720{'-enlarged' if enlarged else ''}.png")
