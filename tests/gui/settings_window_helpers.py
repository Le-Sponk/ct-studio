"""The Settings window on the real main window (P5-T08a): a held editor-settings service,
the fake tools doctor, and finders for the window, its page list and stack."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from editor_owner_helpers import outcome
from editor_request_helpers import settled
from editor_settings_helpers import HeldPreferences
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QListWidget, QStackedWidget
from pytestqt.qtbot import QtBot
from tools_fakes import FakeDoctor

from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices, ToolsService
from ctstudio.gui.views.editors_page import EditorsPage
from ctstudio.gui.views.tools_page import ToolsPage


@contextmanager
def main_window(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> Generator[tuple[MainWindow, HeldPreferences]]:
    preferences = HeldPreferences()
    services = AppServices(
        tools=ToolsService(settings_path=settings_file, diagnose=doctor),
        editor_settings=preferences,
    )
    window = MainWindow(services)
    qtbot.addWidget(window)
    window.show()
    try:
        assert settled(qtbot, lambda: not window.welcome.busy), "the welcome check hung"
        yield window, preferences
    finally:
        preferences.gate.set()
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def action(window: MainWindow, name: str) -> QAction:
    found = window.findChild(QAction, name)
    assert found is not None, f"no {name}"
    return found


def settings_dialog(window: MainWindow) -> QDialog:
    dialog = window.findChild(QDialog, "settingsDialog")
    assert dialog is not None, "no Settings window"
    return dialog


def page_list(dialog: QDialog) -> QListWidget:
    found = dialog.findChild(QListWidget, "settingsPages")
    assert found is not None, "no page list"
    return found


def stack(dialog: QDialog) -> QStackedWidget:
    found = dialog.findChild(QStackedWidget, "settingsStack")
    assert found is not None, "no page stack"
    return found


def shown_page(dialog: QDialog) -> str:
    """The highlighted list entry, after checking the stack shows the same page."""
    pages = page_list(dialog)
    current = pages.currentItem()
    assert current is not None and current.isSelected(), "no page is highlighted"
    widget = stack(dialog).currentWidget()
    expected = {"Tools": ToolsPage, "Editors": EditorsPage}[current.text()]
    assert isinstance(widget, expected), f"{current.text()} highlighted but {widget!r} shown"
    return current.text()
