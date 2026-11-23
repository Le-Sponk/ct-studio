"""P5-T08b: the Build page inside the Settings window on the real main window.

It sits between Tools and Editors. A save there refreshes the dashboard the way a Project
details save does (statuses checked again). Every opening rereads the page, whichever page
the window opens at, because the open project may have changed. Closing the window with
unsaved changes asks Save / Discard / Cancel, and closing while a save runs waits for it.
"""

from __future__ import annotations

import threading
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest
from build_fakes import FakeBuilds
from editor_owner_helpers import outcome
from editor_request_helpers import settled
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFormLayout, QMessageBox, QPushButton, QWidget
from pytestqt.qtbot import QtBot
from settings_window_helpers import action, go, settings_dialog, shown_page
from test_build_page import HeldSettings

from ctstudio.core.components.status import ComponentStatus
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.build_page import BuildPage

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


class Checks:
    """Counts status checks (the dashboard's refresh after a save)."""

    def __init__(self) -> None:
        self.count = 0
        self.builds = FakeBuilds()  # the window's build stand-in, for tests that hold one

    def evaluate(self, _project: object, _tools: object) -> Mapping[str, ComponentStatus]:
        self.count += 1
        return {}


def no_tools(**_kwargs: object) -> tuple[()]:
    return ()


@contextmanager
def window_with_project(
    qtbot: QtBot, folder: Path
) -> Generator[tuple[MainWindow, AppServices, Checks]]:
    checks = Checks()
    builds = checks.builds
    services = AppServices(
        status=StatusService(evaluate=checks.evaluate, find_tools=no_tools),
        build=BuildController(plan=builds.plan, build=builds.run),
    )
    window = MainWindow(services)
    qtbot.addWidget(window)
    window.show()
    try:
        assert settled(qtbot, lambda: not window.welcome.busy), "the welcome check hung"
        window._opened(Project.create(folder / "Window é", "Window é"))  # pyright: ignore[reportPrivateUsage]
        assert settled(qtbot, lambda: not window.dashboard.busy), "the dashboard check hung"
        yield window, services, checks
    finally:
        page = window.settings_window.build_page
        assert page is None or settled(qtbot, lambda: not page.busy), "the page never finished"
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def build_page(window: MainWindow) -> BuildPage:
    page = window.settings_window.build_page
    assert page is not None, "no Build page"
    return page


def open_build(qtbot: QtBot, window: MainWindow) -> BuildPage:
    action(window, "settingsAction").trigger()
    go(settings_dialog(window), "Build")
    page = build_page(window)
    assert settled(qtbot, lambda: not page.busy), "the Build page never read the project"
    return page


def question(qtbot: QtBot, window: MainWindow) -> QMessageBox:
    def asked() -> bool:
        return window.settings_window.question is not None

    assert settled(qtbot, asked), "closing with unsaved changes did not ask"
    found = window.settings_window.question
    assert found is not None and found.isVisible()
    return found


def test_saving_rechecks_the_dashboard(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with window_with_project(qtbot, tmp_path) as (window, services, checks):
        page = open_build(qtbot, window)
        assert shown_page(settings_dialog(window)) == "Build"
        before = checks.count
        cleared: list[bool] = []
        status_clear = services.status.clear

        def clear() -> None:
            cleared.append(True)
            status_clear()

        monkeypatch.setattr(services.status, "clear", clear)
        rechecking: list[bool] = []
        page.saved.connect(lambda: rechecking.append(services.status.busy))  # after the window's
        page.auto_add.setChecked(False)
        page.save_button.click()
        assert settled(qtbot, lambda: not page.busy)
        project = services.project
        assert project is not None and project.manifest.build.auto_add is False
        assert cleared and rechecking == [True], "the save did not make the dashboard recheck"
        assert settled(qtbot, lambda: checks.count > before), "the dashboard was not refreshed"


def test_closing_with_unsaved_changes_and_cancel_keeps_them(qtbot: QtBot, tmp_path: Path) -> None:
    with window_with_project(qtbot, tmp_path) as (window, services, _checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        page.d_copy.setChecked(False)
        dialog.close()
        asked = question(qtbot, window)
        assert asked.defaultButton() is asked.button(QMessageBox.StandardButton.Save)
        asked.button(QMessageBox.StandardButton.Cancel).click()
        assert settled(qtbot, lambda: window.settings_window.question is None)
        assert dialog.isVisible(), "Cancel closed the window"
        assert page.changed and not page.d_copy.isChecked(), "Cancel lost the change"
        project = services.project
        assert project is not None and project.manifest.build.make_d_variant is True


def test_closing_with_unsaved_changes_and_discard_drops_them(qtbot: QtBot, tmp_path: Path) -> None:
    with window_with_project(qtbot, tmp_path) as (window, services, _checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        project = services.project
        assert project is not None
        before = project.manifest_path.read_bytes()
        page.d_copy.setChecked(False)
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        question(qtbot, window).button(QMessageBox.StandardButton.Discard).click()
        assert settled(qtbot, lambda: not dialog.isVisible()), "Discard did not close the window"
        assert project.manifest_path.read_bytes() == before, "Discard wrote the file"
        action(window, "settingsAction").trigger()
        assert shown_page(dialog) == "Build" and settled(qtbot, lambda: not page.busy)
        assert page.d_copy.isChecked() and not page.changed, "the dropped change came back"


def test_closing_with_unsaved_changes_and_save_closes_once_saved(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with window_with_project(qtbot, tmp_path) as (window, services, _checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        page.d_copy.setChecked(False)
        dialog.close()
        question(qtbot, window).button(QMessageBox.StandardButton.Save).click()
        assert settled(qtbot, lambda: not dialog.isVisible()), "the window stayed open"
        project = services.project
        assert project is not None and project.manifest.build.make_d_variant is False
        assert manifest_io.load(project.manifest_path).build.make_d_variant is False


def test_a_failed_save_from_the_question_keeps_the_window_open(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with window_with_project(qtbot, tmp_path) as (window, services, _checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        project = services.project
        assert project is not None
        page.d_copy.setChecked(False)
        outside = project.manifest_path.read_bytes() + b"\n# changed outside\n"
        project.manifest_path.write_bytes(outside)
        dialog.close()
        question(qtbot, window).button(QMessageBox.StandardButton.Save).click()
        assert settled(qtbot, lambda: not page.busy and "Could not save" in page.problem.text())
        QApplication.processEvents()
        assert dialog.isVisible(), "the window closed though nothing was saved"
        assert page.changed and project.manifest_path.read_bytes() == outside
        page.undo()
        dialog.close()
        assert settled(qtbot, lambda: not dialog.isVisible()), "a later close was refused"


def test_closing_while_a_save_runs_waits_for_it(qtbot: QtBot, tmp_path: Path) -> None:
    with window_with_project(qtbot, tmp_path) as (window, services, _checks):
        page = open_build(qtbot, window)
        held = HeldSettings()
        held.save_gate = threading.Event()
        page.service = held
        dialog = settings_dialog(window)
        page.auto_add.setChecked(False)
        page.save_button.click()
        assert settled(qtbot, lambda: page.busy and services.editing)
        dialog.close()
        assert dialog.isVisible() and "Wait" in page.problem.text(), "closed under a save"
        assert window.settings_window.question is None, "asked while saving"
        held.save_gate.set()
        assert settled(qtbot, lambda: not page.busy)
        dialog.close()
        assert settled(qtbot, lambda: not dialog.isVisible()), "the saved window did not close"


def test_every_opening_rereads_the_build_page(qtbot: QtBot, tmp_path: Path) -> None:
    with window_with_project(qtbot, tmp_path) as (window, services, _checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        assert "Window é" in page.note.text()
        dialog.close()
        project = services.project
        assert project is not None
        text = project.manifest_path.read_text(encoding="utf-8")
        assert "auto_add = true" in text, "the file does not say auto_add as expected"
        project.manifest_path.write_text(text.replace("auto_add = true", "auto_add = false"))
        project.manifest = manifest_io.load(project.manifest_path)  # as a reload would
        action(window, "toolsAction").trigger()
        assert shown_page(dialog) == "Tools"
        assert settled(qtbot, lambda: not page.busy and not page.auto_add.isChecked()), (
            "opening at Tools left the Build page showing old settings"
        )


def focused(dialog: QWidget) -> QWidget | None:
    widget = QApplication.focusWidget()
    return widget if widget is not None and dialog.isAncestorOf(widget) else None


def test_tab_goes_from_the_list_into_the_build_page_and_ends_at_close(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with window_with_project(qtbot, tmp_path) as (window, _services, _checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        page.d_copy.setChecked(False)  # Undo and Save on: the whole page takes part
        pages = window.settings_window.pages
        assert pages is not None
        dialog.activateWindow()
        qtbot.waitUntil(dialog.isActiveWindow, timeout=5000)
        pages.setFocus()
        QTest.keyClick(pages, Qt.Key.Key_Tab)
        inside = focused(dialog)
        assert inside is page.test_compression, f"Tab from the list went to {inside!r}"
        closes = [b for b in dialog.findChildren(QPushButton) if b.text() == "Close"]
        assert len(closes) == 1 and closes[0].isDefault(), "Close is not the default"
        page.save_button.setFocus()
        QTest.keyClick(page.save_button, Qt.Key.Key_Tab)
        assert focused(dialog) is closes[0], "Tab from Save did not go to Close"
        page.undo()  # nothing unsaved left for the teardown


def test_closing_during_a_build_offers_only_discard_or_cancel(qtbot: QtBot, tmp_path: Path) -> None:
    with window_with_project(qtbot, tmp_path) as (window, services, checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        page.auto_add.setChecked(False)
        builds = services.build
        assert settled(qtbot, lambda: not services.status.busy), "the status check hung"
        gate = threading.Event()
        checks.builds.gate = gate
        assert services.start_build() is True and settled(qtbot, lambda: builds.running)
        dialog.close()
        asked = question(qtbot, window)
        assert asked.button(QMessageBox.StandardButton.Save) is None, "Save offered in vain"
        assert asked.defaultButton() is asked.button(QMessageBox.StandardButton.Cancel)
        asked.button(QMessageBox.StandardButton.Cancel).click()
        assert settled(qtbot, lambda: window.settings_window.question is None)
        assert dialog.isVisible() and page.changed, "Cancel lost the window or the change"
        gate.set()
        assert settled(qtbot, lambda: not builds.running)
        page.undo()


def test_a_save_whose_thread_cannot_start_does_not_close_later(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with window_with_project(qtbot, tmp_path) as (window, _services, _checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        page.d_copy.setChecked(False)
        dialog.close()
        asked = question(qtbot, window)

        def refuse(_thread: threading.Thread) -> None:
            raise RuntimeError("synthetic: can't start new thread")

        with monkeypatch.context() as patched:
            patched.setattr(threading.Thread, "start", refuse)
            asked.button(QMessageBox.StandardButton.Save).click()
            assert settled(qtbot, lambda: window.settings_window.question is None)
        assert dialog.isVisible() and "can't start new thread" in page.problem.text()
        assert not page.busy and page.changed
        page.save_button.click()  # an ordinary Save afterwards
        assert settled(qtbot, lambda: not page.busy and "Saved" in page.problem.text())
        QApplication.processEvents()
        assert dialog.isVisible(), "an ordinary Save closed the window"


def test_the_build_page_needs_no_more_width_than_the_tools_page(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Font-independent: Tools fits Ubuntu's wider fonts on 800 px; Build must not be wider."""
    with window_with_project(qtbot, tmp_path) as (window, _services, _checks):
        page = open_build(qtbot, window)
        go(settings_dialog(window), "Tools")
        tools = window.settings_window.tools_page
        assert tools is not None and settled(qtbot, lambda: not tools.busy)
        needed, tools_needs = page.minimumSizeHint().width(), tools.minimumSizeHint().width()
        assert needed <= tools_needs, f"Build needs {needed} px, Tools {tools_needs} px"
        form = page.fields.layout()
        assert isinstance(form, QFormLayout)
        for combo in (page.test_compression, page.release_compression):
            label = form.labelForField(combo)
            assert label is not None, "a compression choice has no label"
            above = label.geometry().bottom() <= combo.geometry().top()
            assert above, "a label sits beside its choice: wider fonts then overflow 800 px"


def test_a_long_path_in_an_error_wraps_inside_the_screen(qtbot: QtBot, tmp_path: Path) -> None:
    with window_with_project(qtbot, tmp_path) as (window, _services, _checks):
        page = open_build(qtbot, window)
        dialog = settings_dialog(window)
        held = HeldSettings()
        long_path = str(tmp_path / ("onefoldernamewithnobreaks" * 4) / "ctstudio.toml")
        held.load_error = PermissionError(13, "Access is denied", long_path)
        page.service = held
        page.reload()
        assert settled(qtbot, lambda: not page.busy)
        shown_text = page.problem.text().replace("\u200b", "")
        assert f"Access is denied: {long_path}" in shown_text, shown_text
        QApplication.processEvents()
        screen = dialog.screen().availableGeometry()
        assert dialog.width() <= screen.width(), f"{dialog.width()} > {screen.width()}"
