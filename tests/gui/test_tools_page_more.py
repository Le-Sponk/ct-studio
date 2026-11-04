"""P2-T07b: the Tools page when things go wrong, in the main window, and in a dark palette."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot
from tools_fakes import (
    WAIT,
    FakeDoctor,
    button,
    chosen,
    doctor,
    label,
    make_page,
    opened,
    rows,
    select,
    settings_file,
    shot,
)

from ctstudio.gui.views.tools_page import ToolsPage

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["chosen", "doctor", "opened", "settings_file"]  # fixtures used by name

from ctstudio.core.errors import CTStudioError
from ctstudio.gui.services import ToolsService

# --- problems -----------------------------------------------------------------------------------


def test_a_damaged_settings_file_is_shown_and_never_overwritten(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text("{not json", encoding="utf-8")
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    banner = label(page, "settingsProblem")
    assert banner.isVisible() and str(settings_file) in banner.text()
    assert "Fix or delete that file" in banner.text()
    assert len(rows(page)) == 3 and doctor.calls == [{"force": False, "configured": {}}]
    select(page, "wszst")
    assert not button(page, "browseButton").isEnabled()
    assert not button(page, "clearButton").isEnabled()
    assert button(page, "downloadButton").isEnabled()
    assert settings_file.read_text(encoding="utf-8") == "{not json"
    shot(page, "p2-t07b-tools-damaged-settings.png")


def test_a_failed_check_is_shown_and_the_page_recovers(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    doctor.error = CTStudioError("The tool check stopped.", hint="Try Re-check again.")
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        button(page, "recheckButton").click()
    banner = label(page, "settingsProblem")
    assert banner.isVisible() and "The tool check stopped." in banner.text()
    assert "Try Re-check again." in banner.text()
    assert len(rows(page)) == 3  # the last good list stays
    doctor.error = None
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        button(page, "recheckButton").click()
    assert not banner.isVisible()


def test_a_check_that_fails_after_a_new_path_still_lets_the_user_clear_it(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    """P2-GATE Must fix 1: a saved path that breaks the check must stay undoable on the page."""
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    select(page, "wszst")
    assert not button(page, "clearButton").isEnabled()
    doctor.error = CTStudioError("The tool check stopped.", hint="Try Re-check again.")
    chosen.append(Path("C:/Users/me/notes é.txt"))
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        button(page, "browseButton").click()
    assert "The tool check stopped." in label(page, "settingsProblem").text()
    assert button(page, "clearButton").isEnabled()  # the path was saved, so it can be cleared
    doctor.error = None
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        button(page, "clearButton").click()
    assert doctor.calls[-1]["configured"] == {}
    assert not button(page, "clearButton").isEnabled()


def test_the_service_reports_saved_paths_or_none_for_a_damaged_file(settings_file: Path) -> None:
    service = ToolsService(settings_path=settings_file, diagnose=FakeDoctor())
    assert service.configured() == {}
    service.save_path("wszst", Path("C:/Tools é/wszst.exe"))
    assert service.configured() == {"wszst": Path("C:/Tools é/wszst.exe")}
    settings_file.write_text("{not json", encoding="utf-8")
    assert service.configured() is None


def test_an_unexpected_error_is_shown_too(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    page = make_page(qtbot, doctor, settings_file, opened, chosen)
    doctor.error = RuntimeError("boom")
    with qtbot.waitSignal(page.checked, timeout=WAIT):
        page.recheck(force=True)
    assert "could not check the tools" in label(page, "settingsProblem").text().lower()
    assert button(page, "recheckButton").isEnabled()


# --- in the main window -------------------------------------------------------------------------


def test_settings_tools_opens_the_page(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path
) -> None:
    from ctstudio.gui.main_window import MainWindow
    from ctstudio.gui.services import AppServices

    window = MainWindow(
        AppServices(tools=ToolsService(settings_path=settings_file, diagnose=doctor))
    )
    qtbot.addWidget(window)
    window.show()
    action = window.findChild(QAction, "toolsAction")
    assert action is not None and action.text() == "Tools…"
    assert doctor.calls == []  # nothing is checked until the page is opened
    action.trigger()
    dialog = window.findChild(QDialog, "toolsDialog")
    assert dialog is not None and dialog.isVisible()
    page = dialog.findChild(ToolsPage)
    assert page is not None
    qtbot.waitUntil(lambda: not page.busy, timeout=WAIT)
    assert len(rows(page)) == 3
    dialog.close()
    action.trigger()  # the same page again, checked once more
    assert window.findChild(QDialog, "toolsDialog") is dialog
    qtbot.waitUntil(lambda: len(doctor.calls) == 2 and not page.busy, timeout=WAIT)


def test_dark_palette_screenshot(
    qtbot: QtBot,
    doctor: FakeDoctor,
    settings_file: Path,
    opened: list[str],
    chosen: list[Path | None],
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    original = app.palette()
    palette = QPalette(original)
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(role, QColor("#f3f5f8"))
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
        palette.setColor(role, QColor("#202530"))
    app.setPalette(palette)
    try:
        page = make_page(qtbot, doctor, settings_file, opened, chosen)
        select(page, "wszst")
        shot(page, "p2-t07b-tools-dark.png")
    finally:
        app.setPalette(original)
