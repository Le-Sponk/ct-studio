"""P2-T07b: the Tools page — status of every external tool, set paths, re-check.

The page drives a real ``ToolsService`` (settings file in tmp_path) whose ``diagnose`` is a
recording fake (``tools_fakes``), so no real tool is searched for or started. Every check
must run off the UI thread; tests wait on the page's ``checked`` signal, never sleep.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from tools_fakes import (
    WAIT,
    FakeDoctor,
    busy_bar,
    button,
    chosen,
    doctor,
    item,
    label,
    make_page,
    opened,
    rows,
    saved,
    select,
    settings_file,
    shot,
    tools_table,
)

from ctstudio.core.tools.registry import TOOL_BY_ID

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["chosen", "doctor", "opened", "settings_file"]  # fixtures used by name


# --- the list ----------------------------------------------------------------------------------


def test_the_first_check_lists_every_tool_off_the_ui_thread(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    assert rows(page) == [
        ("Wiimms SZS Tool", "missing", "-"),
        ("Blender", "found", "4.5.3"),
        ("Wine", "not needed", "-"),
    ]
    assert doctor.calls == [{"force": False, "configured": {}}]
    assert doctor.threads[0] is not threading.main_thread()
    assert not busy_bar(page).isVisible()
    assert not label(page, "settingsProblem").isVisible()
    assert not settings_file.exists()  # looking never writes the settings
    shot(page, "p2-t07b-tools-light.png")


def test_status_chips_say_how_urgent_each_row_is(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    chips = [item(page, r, 1).data(Qt.ItemDataRole.UserRole) for r in range(3)]
    assert chips == ["blocking", "ok", "ok"]  # a required tool missing blocks building
    assert item(page, 0, 1).foreground().color() != item(page, 1, 1).foreground().color()
    assert "required" in item(page, 0, 1).toolTip()


def test_selecting_a_row_shows_its_path_how_it_was_found_and_the_fix(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    select(page, "blender")
    details = label(page, "toolDetails").text()
    assert "Blender é" in details and "standard location" in details
    select(page, "wszst")
    details_label = label(page, "toolDetails")
    details = details_label.text()
    assert "Install Wiimms SZS Tool from https://szs.wiimm.de/download.html." in details
    assert details_label.height() >= 4 * details_label.fontMetrics().lineSpacing()
    select(page, "wine")
    assert "Only used on Linux." in label(page, "toolDetails").text()


# --- set path → re-check → status updates (the acceptance flow) -------------------------------


def test_browse_saves_the_path_and_the_recheck_shows_it_found(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
    tmp_path: Path,
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    exe = tmp_path / "Wiimm é" / "wszst.exe"
    chosen.append(exe)
    select(page, "wszst")
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        qtbot.mouseClick(button(page, "browseButton"), Qt.MouseButton.LeftButton)
    assert saved(settings_file) == {"wszst": str(exe)}
    assert doctor.calls[-1] == {"force": False, "configured": {"wszst": exe}}
    assert doctor.threads[-1] is not threading.main_thread()  # the save ran there too
    assert rows(page)[0] == ("Wiimms SZS Tool", "found", "2.42a")
    details = label(page, "toolDetails").text()
    assert str(exe) in details and "your setting" in details  # the selection is kept
    assert button(page, "clearButton").isEnabled()
    shot(page, "p2-t07b-tools-set-path.png")


def test_clear_forgets_the_path_and_checks_again(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
    tmp_path: Path,
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    chosen.append(tmp_path / "wszst.exe")
    select(page, "wszst")
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        button(page, "browseButton").click()
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        button(page, "clearButton").click()
    assert saved(settings_file) == {}
    assert doctor.calls[-1] == {"force": False, "configured": {}}
    assert rows(page)[0][1] == "missing"
    assert not button(page, "clearButton").isEnabled()  # nothing set for this tool now


def test_a_cancelled_browse_changes_nothing(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    chosen.append(None)
    select(page, "wszst")
    button(page, "browseButton").click()
    assert not page.busy and len(doctor.calls) == 1 and not settings_file.exists()


def test_recheck_probes_versions_again(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        button(page, "recheckButton").click()
    assert doctor.calls[-1] == {"force": True, "configured": {}}


def test_while_checking_a_busy_bar_shows_and_actions_wait(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    doctor.gate = threading.Event()
    button(page, "recheckButton").click()
    try:
        qtbot.waitUntil(lambda: len(doctor.calls) == 2, timeout=WAIT)
        assert page.busy and busy_bar(page).isVisible()
        for name in ("recheckButton", "browseButton", "clearButton"):
            assert not button(page, name).isEnabled()
        shot(page, "p2-t07b-tools-checking.png")
    finally:
        with qtbot.waitSignal(page.checked, timeout=WAIT):
            doctor.gate.set()
    assert not page.busy and button(page, "recheckButton").isEnabled()


def test_only_the_newest_check_is_shown(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
    tmp_path: Path,
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    first = threading.Event()
    doctor.gate = first
    page.recheck(force=True)
    qtbot.waitUntil(lambda: len(doctor.calls) == 2, timeout=WAIT)
    doctor.gate = None
    service = page.service
    service.save_path("wszst", tmp_path / "newer.exe")  # what the newer check will read
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        page.recheck(force=False)
    assert rows(page)[0][1] == "found"
    first.set()  # the older check finishes last and must not replace the newer result
    qtbot.waitUntil(lambda: page.pool.activeThreadCount() == 0, timeout=WAIT)
    QApplication.processEvents()
    assert rows(page)[0][1] == "found"


# --- download page ------------------------------------------------------------------------------


def test_open_download_page_opens_the_selected_tools_official_page(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    select(page, "blender")
    button(page, "downloadButton").click()
    select(page, "wszst")
    button(page, "downloadButton").click()
    assert opened == [TOOL_BY_ID["blender"].download_page, TOOL_BY_ID["wszst"].download_page]


def test_without_a_selection_the_row_actions_are_off(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    tools_table(page).clearSelection()
    for name in ("browseButton", "clearButton", "downloadButton"):
        assert not button(page, name).isEnabled()
    assert button(page, "recheckButton").isEnabled()
