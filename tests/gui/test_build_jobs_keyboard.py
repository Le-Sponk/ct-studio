"""P5-T08c: where the keyboard goes after a pick on Settings → Build → This computer.

Turning the choice off while it saves moves the keyboard on (to Close, the default button).
When the save is refused because the settings file became unusable, the choice is hidden, so
the keyboard goes to the page's tabs instead of staying on Close. When the user has left the
tab or the page meanwhile, the keyboard stays where the user put it.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from editor_request_helpers import settled
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from pytestqt.qtbot import QtBot
from settings_window_helpers import go, settings_dialog
from test_build_window import focused, open_build, window_with_project

from ctstudio.core.project import settings
from ctstudio.gui.build_settings import BuildJobsService

pytestmark = [pytest.mark.gui]


class HeldSave(BuildJobsService):
    """The real service whose saves wait for ``release``."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    def save(self, jobs: int | None) -> int | None:
        assert self.release.wait(10)
        return super().save(jobs)


def damage() -> None:
    path = settings.default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"format": 1, "build_jobs": 0}', encoding="utf-8")


def test_a_refused_keyboard_pick_leaves_the_keyboard_off_close(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with window_with_project(qtbot, tmp_path) as (window, _services, _checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        page.tabs.setCurrentWidget(page.jobs)
        assert settled(qtbot, lambda: not page.jobs.busy and page.jobs.combo.isEnabled())
        damage()  # after reading
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
        page.jobs.combo.setFocus()
        assert page.jobs.combo.hasFocus(), "the choice could not take the focus"
        QTest.keyClick(page.jobs.combo, Qt.Key.Key_Down)
        assert settled(qtbot, lambda: not page.jobs.busy and page.jobs.combo.isHidden())
        where = focused(dialog)
        assert where is page.tabs.tabBar(), f"the keyboard went to {where!r}, not the tabs"


def test_leaving_the_page_during_a_refused_save_keeps_the_keyboard_there(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with window_with_project(qtbot, tmp_path) as (window, _services, _checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        page.tabs.setCurrentWidget(page.jobs)
        assert settled(qtbot, lambda: not page.jobs.busy and page.jobs.combo.isEnabled())
        held = HeldSave()
        page.jobs.service = held
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
        page.jobs.combo.setFocus()
        QTest.keyClick(page.jobs.combo, Qt.Key.Key_Down)
        assert page.jobs.busy, "the save did not start"
        go(dialog, "Tools")  # the user moves on while it saves
        pages = window.settings_window.pages
        assert pages is not None
        pages.setFocus()
        damage()
        held.release.set()
        assert settled(qtbot, lambda: not page.jobs.busy and page.jobs.combo.isHidden())
        where = focused(dialog)
        assert where is pages, f"the keyboard was taken to {where!r}"
