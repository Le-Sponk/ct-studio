"""Settings → Editors… → Wine (Linux) tab helpers (P5-T07f3): read the rows, pick one, and
choose or clear its prefix the way a user does (the folder dialog's ``fileSelected``)."""

from __future__ import annotations

from pathlib import Path

from editor_request_helpers import settled
from PySide6.QtWidgets import QDialog, QFileDialog
from pytestqt.qtbot import QtBot

from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.gui.views.editors_page import EditorsPage

# The built-in Windows editors, in the order the tab lists them (the Wine recipes' order).
BUILT_IN = ("brawlcrate", "kmp_cloud", "riistudio", "kmp_editor_lorenzi")
NONE = "no prefix chosen"


def row(name: str, prefix: Path | str | None) -> str:
    return f"{name}: {NONE if prefix is None else prefix}"


def built_in_rows(prefixes: dict[str, Path] | None = None) -> list[str]:
    chosen = prefixes or {}
    return [row(TOOL_BY_ID[tool].name, chosen.get(tool)) for tool in BUILT_IN]


def wine_rows(page: EditorsPage) -> list[str]:
    rows = page.wine.rows
    return [rows.item(index).text() for index in range(rows.count())]


def show_wine(page: EditorsPage) -> None:
    page.tabs.setCurrentWidget(page.wine)
    assert page.wine.isVisible(), "the Wine tab does not show"


def select_wine(page: EditorsPage, name: str) -> None:
    """Select the row of the editor called ``name``."""
    rows = page.wine.rows
    found = [index for index in range(rows.count()) if rows.item(index).text().startswith(name)]
    assert len(found) == 1, f"{name!r} rows: {found} in {wine_rows(page)}"
    rows.setCurrentRow(found[0])
    assert page.wine.selected() is not None, f"{name!r} is not selected"


def folder_dialog(qtbot: QtBot, page: EditorsPage) -> QFileDialog:
    assert settled(qtbot, lambda: page.wine.folder_dialog is not None), "no folder dialog"
    dialog = page.wine.folder_dialog
    assert dialog is not None and dialog.isVisible(), "the folder dialog is not shown"
    return dialog


def pick(dialog: QFileDialog, folder: Path) -> None:
    """Answer the folder dialog with ``folder`` as a user does: it reports the folder, then
    closes. (``QFileDialog.accept`` would check the folder and ask about a missing one.)"""
    dialog.fileSelected.emit(str(folder))
    QDialog.done(dialog, QDialog.DialogCode.Accepted.value)


def choose_folder(qtbot: QtBot, page: EditorsPage, name: str, folder: Path) -> None:
    """Choose ``folder`` as ``name``'s prefix through Choose folder… and wait for the save."""
    select_wine(page, name)
    assert page.wine.choose_button.isEnabled(), "Choose folder… is off"
    page.wine.choose_button.click()
    pick(folder_dialog(qtbot, page), folder)
    assert settled(qtbot, lambda: not page.busy), "the save never finished"


def clear_prefix(qtbot: QtBot, page: EditorsPage, name: str) -> None:
    select_wine(page, name)
    assert page.wine.clear_button.isEnabled(), "Clear is off"
    page.wine.clear_button.click()
    assert settled(qtbot, lambda: not page.busy), "the save never finished"
