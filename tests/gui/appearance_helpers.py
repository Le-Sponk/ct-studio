"""Settings → Appearance (P5-T08d) in tests: a recording stand-in for Qt's style hints and a
finder that opens the page on the real main window."""

from __future__ import annotations

import pytest
from editor_request_helpers import settled
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot
from settings_window_helpers import action, go, settings_dialog

from ctstudio.gui import appearance
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.views.appearance_section import AppearanceSection


class FakeHints:
    """Records each requested scheme. The scheme shown starts as the ``system``'s; asking for
    Unknown goes back to it, as on Windows. ``honours=False`` is a platform that ignores the
    requests (as the offscreen one does): the system's scheme stays."""

    def __init__(
        self, *, honours: bool = True, system: Qt.ColorScheme = Qt.ColorScheme.Unknown
    ) -> None:
        self.honours = honours
        self.system = system
        self.asked: list[Qt.ColorScheme] = []
        self._scheme = system

    def colorScheme(self, /) -> Qt.ColorScheme:
        return self._scheme

    def setColorScheme(self, scheme: Qt.ColorScheme, /) -> None:
        self.asked.append(scheme)
        if self.honours:
            self._scheme = self.system if scheme == Qt.ColorScheme.Unknown else scheme


def install_hints(
    monkeypatch: pytest.MonkeyPatch,
    *,
    honours: bool = True,
    system: Qt.ColorScheme = Qt.ColorScheme.Unknown,
) -> FakeHints:
    fake = FakeHints(honours=honours, system=system)

    def hints() -> FakeHints:
        return fake

    monkeypatch.setattr(appearance, "style_hints", hints)
    return fake


def open_appearance(qtbot: QtBot, window: MainWindow) -> AppearanceSection:
    action(window, "settingsAction").trigger()
    go(settings_dialog(window), "Appearance")
    page = window.settings_window.appearance_page
    assert page is not None, "the Appearance page was not made"
    assert settled(qtbot, lambda: not page.busy), "the Appearance page never finished reading"
    return page


def pick(page: AppearanceSection, scheme: str | None) -> None:
    """Choose ``scheme`` as a user would (Qt emits ``activated`` for user picks only)."""
    index = page.combo.findData(scheme)
    assert index >= 0, f"{scheme!r} is not offered"
    page.combo.setCurrentIndex(index)
    page.combo.activated.emit(index)
