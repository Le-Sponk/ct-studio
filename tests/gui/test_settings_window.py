"""P5-T08a: one Settings window with a page list on the left (Tools, Build, Editors so far).

Settings → Settings… opens it at the last page shown; Settings → Tools… and Settings →
Editors… open it at their page. A page is made the first time it is shown (Tools starts its
check then) and refreshed each time it is opened again, as the separate windows were.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from editor_request_helpers import settled
from editor_tools_helpers import selected_tool
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QWidget
from pytestqt.qtbot import QtBot
from settings_window_helpers import (
    action,
    go,
    main_window,
    page_list,
    settings_dialog,
    shown_page,
    stack,
)
from tools_fakes import FakeDoctor, doctor, settings_file

from ctstudio.gui.settings_window import PAGES

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
__all__ = ["doctor", "settings_file"]  # fixtures used by name


def test_settings_opens_one_window_with_a_page_list(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        opener = action(window, "settingsAction")
        assert opener.text() == "Settings…"
        assert opener.shortcut() == QKeySequence("Ctrl+,"), "no Settings shortcut"
        opener.trigger()
        dialog = settings_dialog(window)
        assert dialog.isVisible() and dialog.windowTitle() == "Settings"
        pages = page_list(dialog)
        names = [pages.item(i).text() for i in range(pages.count())]
        assert names == ["Tools", "Build", "Editors"], "not the original P5-T08 order"
        assert shown_page(dialog) == "Tools", "Settings… did not start at the first page"
        stacked = stack(dialog)
        left = pages.mapTo(dialog, pages.rect().topRight()).x()
        assert left < stacked.mapTo(dialog, stacked.rect().topLeft()).x(), "list not on the left"


def test_tools_and_editors_open_their_page_in_the_same_window(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        action(window, "editorsAction").trigger()
        dialog = settings_dialog(window)
        assert shown_page(dialog) == "Editors"
        assert window.editors_window.dialog is dialog, "Editors… made another window"
        dialog.close()
        action(window, "toolsAction").trigger()
        assert settings_dialog(window) is dialog and dialog.isVisible()
        assert shown_page(dialog) == "Tools"
        assert window.tools_window.dialog is dialog, "Tools… made another window"
        assert len(window.findChildren(QDialog, "settingsDialog")) == 1


def test_a_page_is_made_only_when_first_shown(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, preferences):
        action(window, "editorsAction").trigger()
        dialog = settings_dialog(window)
        assert settled(qtbot, lambda: preferences.loads == 1), "the Editors page did not read"
        assert window.tools_window.page is None, "the Tools page was made unasked"
        assert doctor.calls == [], "tools were checked before the Tools page was shown"
        go(dialog, "Tools")
        assert shown_page(dialog) == "Tools"
        tools = window.tools_window.page
        assert tools is not None, "showing Tools made no page"
        assert settled(qtbot, lambda: len(doctor.calls) == 1 and not tools.busy)
        assert preferences.loads == 1, "switching pages reread the Editors settings"
        go(dialog, "Editors")
        go(dialog, "Tools")
        assert shown_page(dialog) == "Tools"
        assert settled(qtbot, lambda: not tools.busy)
        assert len(doctor.calls) == 1, "switching back to Tools checked the tools again"
        assert preferences.loads == 1, "switching to Editors reread the settings file"


def test_opening_a_page_again_refreshes_it(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, preferences):
        action(window, "toolsAction").trigger()
        dialog = settings_dialog(window)
        tools = window.tools_window.page
        assert tools is not None
        assert settled(qtbot, lambda: len(doctor.calls) == 1 and not tools.busy)
        action(window, "editorsAction").trigger()
        assert settled(qtbot, lambda: preferences.loads == 1)
        editors = window.editors_window.page
        assert editors is not None and settled(qtbot, lambda: not editors.busy)
        dialog.close()
        action(window, "editorsAction").trigger()
        assert settled(qtbot, lambda: preferences.loads == 2), "Editors… did not reread"
        assert window.editors_window.page is editors, "the Editors page was made again"
        action(window, "toolsAction").trigger()
        assert settled(qtbot, lambda: len(doctor.calls) == 2), "Tools… did not check again"
        assert window.tools_window.page is tools, "the Tools page was made again"


def test_settings_reopens_at_the_last_page_shown(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        action(window, "editorsAction").trigger()
        dialog = settings_dialog(window)
        dialog.close()
        action(window, "settingsAction").trigger()
        assert dialog.isVisible() and shown_page(dialog) == "Editors"
        go(dialog, "Tools")  # a page picked in the list counts too
        dialog.close()
        action(window, "settingsAction").trigger()
        assert dialog.isVisible() and shown_page(dialog) == "Tools"


def test_the_page_list_follows_the_keyboard(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        action(window, "settingsAction").trigger()
        dialog = settings_dialog(window)
        pages = page_list(dialog)
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
        pages.setFocus()
        assert pages.hasFocus(), "the page list did not take focus"
        QTest.keyClick(pages, Qt.Key.Key_Down)
        assert shown_page(dialog) == "Build", "Down did not show the next page"
        QTest.keyClick(pages, Qt.Key.Key_Down)
        assert shown_page(dialog) == "Editors", "Down did not show the next page"
        QTest.keyClick(pages, Qt.Key.Key_Up)
        assert shown_page(dialog) == "Build", "Up did not show the previous page"
        QTest.keyClick(pages, Qt.Key.Key_Return)
        assert dialog.isVisible(), "Enter in the page list closed the window"
        assert pages.accessibleName() == "Settings pages"


def focused(dialog: QDialog) -> QWidget | None:
    widget: QWidget | None = QApplication.focusWidget()
    return widget if widget is not None and dialog.isAncestorOf(widget) else None


@pytest.mark.parametrize("first", ["toolsAction", "editorsAction"])
def test_tab_goes_from_the_list_into_the_page_and_ends_at_close(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, first: str
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        action(window, first).trigger()
        dialog = settings_dialog(window)
        pages = page_list(dialog)
        for name in ("Editors", "Tools") if first == "toolsAction" else ("Tools", "Editors"):
            go(dialog, name)  # both pages made, in either order (Build: test_build_window.py)
            dialog.activateWindow()
            qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
            pages.setFocus()
            assert pages.hasFocus(), "the page list did not take focus"
            closes = [b for b in dialog.findChildren(QPushButton) if b.text() == "Close"]
            assert closes and closes[0].isDefault(), "Close is not the default (list focused)"
            QTest.keyClick(pages, Qt.Key.Key_Tab)
            inside = focused(dialog)
            shown = stack(dialog).currentWidget()
            assert shown is not None, "the stack shows no page"
            assert inside is not None and shown.isAncestorOf(inside), (
                f"Tab from the list went to {inside!r}, not into the page"
            )
            buttons = [b for b in dialog.findChildren(QPushButton) if b.text() == "Close"]
            assert len(buttons) == 1, "no single Close button"
            buttons[0].setFocus()
            QTest.keyClick(buttons[0], Qt.Key.Key_Backtab)
            back = focused(dialog)
            assert back is not None and shown.isAncestorOf(back), (
                f"Shift+Tab from Close went to {back!r}, not back into the page"
            )


def test_the_page_list_widens_with_a_larger_font(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        action(window, "settingsAction").trigger()
        pages = page_list(settings_dialog(window))
        font = QFont(pages.font())
        font.setPointSizeF(font.pointSizeF() * 2)
        pages.setFont(font)
        needed = max(pages.fontMetrics().horizontalAdvance(name) for name in PAGES)
        assert pages.viewport().width() >= needed, "a page name is cut short after a font change"


def test_set_up_in_tools_selects_that_tool_on_the_tools_page(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        action(window, "editorsAction").trigger()
        dialog = settings_dialog(window)
        dialog.close()
        window.tools_window.open("blender")
        assert dialog.isVisible() and shown_page(dialog) == "Tools"
        tools = window.tools_window.page
        assert tools is not None
        assert settled(qtbot, lambda: not tools.busy and selected_tool(tools) == "blender"), (
            "the wanted tool was not selected"
        )
