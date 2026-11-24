"""P5-T08e2: Settings → Advanced → This computer, "Build logs kept per project", on the real
main window: offered 20 (the default), 5, 10, 50 and 100; a pick is saved at once and leaves
the tool commands choice alone; a saved number outside the list is offered in order; a
damaged file is explained once for both choices; the keyboard stays on the choice picked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from advanced_helpers import open_advanced, pick_logs
from editor_request_helpers import settled
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QWidget
from pytestqt.qtbot import QtBot
from settings_window_helpers import main_window, settings_dialog
from tools_fakes import FakeDoctor, doctor, settings_file

from ctstudio.core.project import settings
from ctstudio.core.project.settings import BUILD_LOGS_KEPT, MAX_BUILD_LOGS_KEPT

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
__all__ = ["doctor", "settings_file"]  # fixtures used by name
DAMAGED = '{"format": 1, "build_logs_kept": 0}\n'


def saved() -> dict[str, object]:
    return json.loads(settings.default_path().read_text(encoding="utf-8"))


def write(text: str) -> None:
    path = settings.default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def offered(combo: QComboBox) -> list[tuple[str, object]]:
    return [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]


def test_the_choice_offers_the_default_and_four_numbers(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        logs = page.computer.logs
        assert offered(logs) == [
            ("20 (default)", None),
            ("5", 5),
            ("10", 10),
            ("50", 50),
            ("100", 100),
        ]
        assert logs.currentData() is None and logs.isEnabled() and logs.isVisible()
        label = page.computer.rows[logs.objectName()][0]
        assert label.text() == "&Build logs kept per project" and label.buddy() is logs
        assert "ctstudio build" in logs.toolTip()


def test_a_pick_is_saved_at_once_and_leaves_tool_commands_alone(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    write('{"show_tool_commands": false, "future": [1]}')
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        assert page.computer.combo.currentData() is False, "the other choice was not read"
        pick_logs(page, 5)
        assert settled(qtbot, lambda: not page.busy and bool(page.computer.note.text()))
        assert saved() == {
            "format": 1,
            "show_tool_commands": False,
            "future": [1],
            BUILD_LOGS_KEPT: 5,
            "tools": {},
        }
        note = page.computer.note.text()
        assert (
            note == "Saved. After the next build each project keeps only its newest 5 build logs."
        )
        assert page.computer.combo.currentData() is False, "the other choice changed"
        pick_logs(page, None)
        assert settled(qtbot, lambda: not page.busy and "20" in page.computer.note.text())
        assert BUILD_LOGS_KEPT not in saved()
        assert page.computer.logs.currentData() is None


@pytest.mark.parametrize(("number", "at"), [(1, 1), (7, 2), (75, 4), (MAX_BUILD_LOGS_KEPT, 5)])
def test_a_saved_number_outside_the_list_is_offered_in_order(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, number: int, at: int
) -> None:
    write(json.dumps({BUILD_LOGS_KEPT: number}))
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        logs = page.computer.logs
        assert logs.currentData() == number, f"{number} was not shown as saved"
        assert logs.findData(number) == at, offered(logs)
        assert logs.count() == 6, offered(logs)
        page.computer.reload()  # a second read adds nothing more
        assert settled(qtbot, lambda: not page.busy)
        assert logs.count() == 6, offered(logs)
        pick_logs(page, number)  # picked again (the file already says so: nothing written)
        assert settled(qtbot, lambda: not page.busy and bool(page.computer.note.text()))
        kept = "build log" if number == 1 else f"{number} build logs"
        assert page.computer.note.text().endswith(f"keeps only its newest {kept}.")


def test_a_damaged_file_is_explained_once_for_both_choices(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    write(DAMAGED)
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        for label, combo in page.computer.rows.values():
            assert label.isHidden() and combo.isHidden(), f"{combo.objectName()} shows"
        dialog = settings_dialog(window)
        reasons = [
            label
            for label in dialog.findChildren(QLabel)
            if label.isVisible() and "cannot be used" in label.text()
        ]
        assert reasons == [page.computer.banner], [label.objectName() for label in reasons]
        assert BUILD_LOGS_KEPT in page.computer.banner.text().replace("\u200b", "")
        assert settings.default_path().read_text(encoding="utf-8") == DAMAGED


def focused(dialog: QWidget) -> QWidget | None:
    widget = QApplication.focusWidget()
    return widget if widget is not None and dialog.isAncestorOf(widget) else None


def test_the_keyboard_stays_on_the_choice_picked(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    with main_window(qtbot, doctor, settings_file) as (window, _preferences):
        page = open_advanced(qtbot, window)
        dialog = settings_dialog(window)
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
        logs = page.computer.logs
        logs.setFocus()
        assert logs.hasFocus(), "the choice could not take the focus"
        QTest.keyClick(logs, Qt.Key.Key_Down)
        assert settled(qtbot, lambda: not page.busy and bool(page.computer.note.text()))
        assert saved()[BUILD_LOGS_KEPT] == 5
        assert focused(dialog) is logs, f"the keyboard went to {focused(dialog)!r}"
        write(DAMAGED)
        QTest.keyClick(logs, Qt.Key.Key_Down)
        assert settled(qtbot, lambda: not page.busy and logs.isHidden())
        assert settings.default_path().read_text(encoding="utf-8") == DAMAGED
        where = focused(dialog)
        assert where is page.tabs.tabBar(), f"the keyboard went to {where!r}, not the tabs"
