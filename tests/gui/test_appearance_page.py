"""P5-T08d: Settings → Appearance on the real main window.

One choice, Follow system / Light / Dark, read from ``settings.json`` on the page's worker
and saved at once through a fresh read; a saved choice is applied straight away, and the
note says so, or that the system does not let CT Studio change it. A damaged or newer file
is shown and never overwritten; the choice is hidden until a reread finds the file usable.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import ClassVar

import pytest
from appearance_helpers import install_hints, open_appearance, pick
from editor_request_helpers import settled
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot
from settings_window_helpers import go, main_window, settings_dialog
from tools_fakes import FakeDoctor, doctor, settings_file

from ctstudio.core.project import settings
from ctstudio.core.project.settings import COLOUR_SCHEME
from ctstudio.gui import settings_window
from ctstudio.gui.appearance import AppearanceService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
__all__ = ["doctor", "settings_file"]  # fixtures used by name
DAMAGED = '{"format": 1, "colour_scheme": 7}\n'


class Recorded(AppearanceService):
    """The real service; records the thread of every call."""

    threads: ClassVar[list[threading.Thread]] = []

    def load(self) -> str | None:
        Recorded.threads.append(threading.current_thread())
        return super().load()

    def save(self, scheme: str | None) -> str | None:
        Recorded.threads.append(threading.current_thread())
        return super().save(scheme)


def saved() -> dict[str, object]:
    return json.loads(settings.default_path().read_text(encoding="utf-8"))


def write(text: str) -> None:
    path = settings.default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def focused(dialog: QWidget) -> QWidget | None:
    widget = QApplication.focusWidget()
    return widget if widget is not None and dialog.isAncestorOf(widget) else None


def test_the_page_offers_the_three_schemes_and_starts_at_the_saved_one(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    write('{"colour_scheme": "dark"}')
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_appearance(qtbot, window)
        offered = [(page.combo.itemText(i), page.combo.itemData(i)) for i in range(3)]
        assert page.combo.count() == 3
        assert offered == [("Follow system", None), ("Light", "light"), ("Dark", "dark")]
        assert page.combo.currentData() == "dark", "the saved scheme is not shown"
        assert page.combo.isEnabled() and page.combo.isVisible()
        assert page.label.text() == "Colour &scheme" and page.label.buddy() is page.combo
        assert page.intro.isVisible() and page.banner.isHidden()


def test_a_pick_is_saved_on_a_worker_and_applied_at_once(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hints = install_hints(monkeypatch)
    Recorded.threads = []
    monkeypatch.setattr(settings_window, "AppearanceService", Recorded)
    write('{"future": [1]}')
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_appearance(qtbot, window)
        assert page.combo.currentData() is None, "no saved scheme must mean Follow system"
        pick(page, "dark")
        assert settled(qtbot, lambda: not page.busy and bool(page.note.text()))
        assert saved() == {"format": 1, "future": [1], COLOUR_SCHEME: "dark", "tools": {}}
        assert hints.asked == [Qt.ColorScheme.Dark], "the saved scheme was not applied"
        assert page.note.text() == "Saved. CT Studio uses the dark colour scheme."
        pick(page, None)
        assert settled(qtbot, lambda: not page.busy and "follows" in page.note.text())
        assert COLOUR_SCHEME not in saved(), "Follow system left the key behind"
        assert hints.asked == [Qt.ColorScheme.Dark, Qt.ColorScheme.Unknown]
        assert page.note.text() == "Saved. CT Studio follows the system's colour scheme."
        assert Recorded.threads, "the real service was not used"
        assert threading.main_thread() not in Recorded.threads, "the file was used on the UI"


def test_a_system_that_ignores_the_scheme_is_told(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hints = install_hints(monkeypatch, honours=False)
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_appearance(qtbot, window)
        pick(page, "light")
        assert settled(qtbot, lambda: not page.busy and bool(page.note.text()))
        assert saved()[COLOUR_SCHEME] == "light", "the choice must be saved all the same"
        assert hints.asked == [Qt.ColorScheme.Light]
        assert page.note.text() == (
            "Saved, but this system does not let CT Studio change its colour scheme."
        )


def test_a_file_damaged_after_reading_is_refused_and_the_keyboard_kept_near(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hints = install_hints(monkeypatch)
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_appearance(qtbot, window)
        dialog = settings_dialog(window)
        write(DAMAGED)
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
        page.combo.setFocus()
        assert page.combo.hasFocus(), "the choice could not take the focus"
        QTest.keyClick(page.combo, Qt.Key.Key_Down)
        assert settled(qtbot, lambda: not page.busy and page.combo.isHidden())
        assert settings.default_path().read_text(encoding="utf-8") == DAMAGED
        assert len(list(settings.default_path().parent.iterdir())) == 1, "a backup was made"
        assert hints.asked == [], "a refused save applied the scheme"
        assert page.label.isHidden() and page.intro.isHidden()
        assert "cannot be used" in page.banner.text() and page.banner.isVisible()
        pages = window.settings_window.pages
        where = focused(dialog)
        assert where is pages, f"the keyboard went to {where!r}, not the page list"


def test_a_keyboard_pick_gives_the_keyboard_back_to_the_choice(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_hints(monkeypatch)
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_appearance(qtbot, window)
        dialog = settings_dialog(window)
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
        page.combo.setFocus()
        QTest.keyClick(page.combo, Qt.Key.Key_Down)
        assert settled(qtbot, lambda: not page.busy and bool(page.note.text()))
        assert saved()[COLOUR_SCHEME] == "light"
        assert focused(dialog) is page.combo, "the keyboard did not come back to the choice"


def test_a_damaged_file_is_shown_until_a_reopening_finds_it_fixed(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    write(DAMAGED)
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_appearance(qtbot, window)
        assert page.combo.isHidden() and page.banner.isVisible()
        path = str(settings.default_path())
        assert path in page.banner.text().replace("\u200b", ""), "the banner does not name it"
        write('{"colour_scheme": "light"}')
        dialog = settings_dialog(window)
        dialog.close()
        window.settings_window.open()  # at the last page shown: Appearance
        assert settled(qtbot, lambda: not page.busy and page.combo.isVisible())
        assert page.combo.currentData() == "light" and page.banner.isHidden()


def test_every_opening_rereads_the_scheme_and_drops_the_old_note(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_hints(monkeypatch)
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_appearance(qtbot, window)
        pick(page, "light")
        assert settled(qtbot, lambda: not page.busy and bool(page.note.text()))
        dialog = settings_dialog(window)
        go(dialog, "Tools")
        write('{"colour_scheme": "dark"}')
        dialog.close()
        window.settings_window.open("Appearance")
        assert settled(qtbot, lambda: not page.busy and page.combo.currentData() == "dark")
        assert page.note.text() == "", "the note about an earlier pick stayed"


class Failing(AppearanceService):
    def load(self) -> str | None:
        raise RuntimeError("disk gone")


def test_a_failed_read_names_the_setting(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings_window, "AppearanceService", Failing)
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_appearance(qtbot, window)
        text = page.banner.text()
        assert text == "Could not read the colour scheme setting. disk gone", text
        assert not page.combo.isEnabled(), "a choice was offered before a good read"


def test_tab_goes_from_the_list_to_the_choice_then_close(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_appearance(qtbot, window)
        dialog = settings_dialog(window)
        pages, close = window.settings_window.pages, window.settings_window.close
        assert pages is not None and close is not None
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
        pages.setFocus()
        assert pages.hasFocus()
        QTest.keyClick(pages, Qt.Key.Key_Tab)
        assert focused(dialog) is page.combo, f"Tab went to {focused(dialog)!r}"
        QTest.keyClick(page.combo, Qt.Key.Key_Tab)
        assert focused(dialog) is close, f"Tab went to {focused(dialog)!r}, not Close"
