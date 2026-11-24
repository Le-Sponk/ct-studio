"""P5-T08e3: Settings → Advanced → This computer, "Developer mode", on the real main window:
Off (the default) or On, saved at once leaving the other choices alone, the note saying it
takes effect from the next start; a damaged file hides it with the others.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from advanced_helpers import open_advanced
from editor_request_helpers import settled
from pytestqt.qtbot import QtBot
from settings_window_helpers import main_window
from tools_fakes import FakeDoctor, doctor, settings_file

from ctstudio.core.project import settings
from ctstudio.core.project.settings import DEVELOPER_MODE
from ctstudio.gui.views.advanced_page import AdvancedPage

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
__all__ = ["doctor", "settings_file"]  # fixtures used by name


def saved() -> dict[str, object]:
    return json.loads(settings.default_path().read_text(encoding="utf-8"))


def write(text: str) -> None:
    path = settings.default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def pick(page: AdvancedPage, on: bool) -> None:
    combo = page.computer.developer
    index = combo.findData(on)
    assert index >= 0, f"{on!r} is not offered"
    combo.setCurrentIndex(index)
    combo.activated.emit(index)


def test_the_choice_offers_off_and_on_and_starts_off(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        combo = page.computer.developer
        offered = [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]
        assert offered == [("Off", False), ("On", True)]
        assert combo.currentData() is False and combo.isEnabled() and combo.isVisible()
        label = page.computer.rows[combo.objectName()][0]
        assert label.text() == "&Developer mode" and label.buddy() is combo
        tip = combo.toolTip()
        assert "From the next start" in tip and "ctstudio.log" in tip and "CTSTUDIO_DEV=1" in tip


def test_a_pick_is_saved_at_once_and_takes_effect_from_the_next_start(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    write('{"build_logs_kept": 50, "future": [1]}')
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        assert page.computer.logs.currentData() == 50, "the other choice was not read"
        pick(page, True)
        assert settled(qtbot, lambda: not page.busy and bool(page.computer.note.text()))
        assert saved() == {
            "format": 1,
            "build_logs_kept": 50,
            "future": [1],
            DEVELOPER_MODE: True,
            "tools": {},
        }
        note = page.computer.note.text()
        assert note == "Saved. From the next start CT Studio logs where its window gets stuck."
        pick(page, False)
        assert settled(qtbot, lambda: not page.busy and "off" in page.computer.note.text())
        assert saved()[DEVELOPER_MODE] is False
        assert page.computer.note.text() == (
            "Saved. From the next start developer mode is off (unless CTSTUDIO_DEV=1)."
        )
        assert page.computer.logs.currentData() == 50, "the other choice changed"


def test_a_damaged_file_hides_it_with_the_other_choices(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    text = '{"format": 1, "developer_mode": "on"}\n'
    write(text)
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        assert page.computer.developer.isHidden() and page.computer.combo.isHidden()
        reason = page.computer.banner.text().replace("\u200b", "")
        assert f'"{DEVELOPER_MODE}" is not true or false' in reason, reason
        assert settings.default_path().read_text(encoding="utf-8") == text
