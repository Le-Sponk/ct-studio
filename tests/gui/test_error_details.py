"""P5-T10f: inline errors offer Copy details; an unexpected error shows one dialog, logged."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from dashboard_helpers import overview
from editor_request_helpers import settled
from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ctstudio.core.build.events import BuildStarted, NodeFailed
from ctstudio.core.errors import CTStudioError, ToolFailed
from ctstudio.gui.crash import CrashReporter, install
from ctstudio.gui.status_service import StatusResult
from ctstudio.gui.views.build_controls import BuildControls
from ctstudio.gui.views.crash_dialog import CrashDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(20)]


@pytest.fixture
def clipboard() -> Iterator[QApplication]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    previous = app.clipboard().text()
    app.clipboard().setText("untouched")
    yield app
    app.clipboard().setText(previous)


@pytest.fixture
def controls(qtbot: QtBot) -> BuildControls:
    widget = BuildControls()
    qtbot.addWidget(widget)
    widget.show()
    return widget


def test_a_failing_tool_offers_its_details(
    controls: BuildControls, clipboard: QApplication, tmp_path: Path
) -> None:
    error = ToolFailed(["wszst", "create"], 3, "bad magic in course.kcl", tmp_path / "w.log")
    controls.show_error(error)
    button = controls.copy_details
    assert not button.isHidden() and button.text() == "Copy details"
    assert button.accessibleName() == "Copy details of the build error"
    assert "bad magic" not in controls.notice.text()  # the details stay out of the message
    button.click()
    copied = clipboard.clipboard().text()
    assert copied.startswith(controls.notice.text()) and str(error.details) in copied
    controls.clear()
    assert button.isHidden(), "the previous project's details are still offered"


def test_an_error_without_details_offers_none(controls: BuildControls) -> None:
    controls.show_error(CTStudioError("Nothing to build.", hint="Add a part."))
    assert controls.copy_details.isHidden()


def test_an_unexpected_build_error_offers_its_traceback(
    controls: BuildControls, clipboard: QApplication
) -> None:
    try:
        raise RuntimeError("boom in the planner")
    except RuntimeError as exc:
        controls.show_error(exc)
    controls.copy_details.click()
    copied = clipboard.clipboard().text()
    assert "Traceback" in copied and "RuntimeError: boom in the planner" in copied


def test_a_failed_step_offers_the_tool_output_without_showing_it(
    controls: BuildControls, clipboard: QApplication
) -> None:
    controls.begin(release=False)
    controls.show_event(BuildStarted(("archive",)))
    controls.show_event(NodeFailed("archive", "Bad source", "Fix it", False, details="stderr X"))
    assert "stderr X" not in controls.notice.text()
    controls.copy_details.click()
    assert "stderr X" in clipboard.clipboard().text()
    controls.begin(release=False)  # a new run starts clean
    assert controls.copy_details.isHidden()


def test_an_unreadable_settings_file_offers_its_details(
    qtbot: QtBot, tmp_path: Path, clipboard: QApplication
) -> None:
    with overview(qtbot, tmp_path) as (page, services, project):
        problem = "CT Studio's settings file cannot be used: it is not valid JSON."
        result = StatusResult(project.root, {}, problem, settings_details="Expecting value: 1:1")
        services.status.updated.emit(result)
        assert page.notice.text() == problem
        assert not page.notice_details.isHidden()
        assert page.notice_details.accessibleName() == "Copy details of the dashboard message"
        page.notice_details.click()
        assert clipboard.clipboard().text() == f"{problem}\n\nExpecting value: 1:1"
        services.status.updated.emit(StatusResult(project.root, {}))
        assert page.notice_details.isHidden(), "details offered after the problem went"


class _Source(QObject):
    fired = Signal()


@pytest.mark.qt_no_exception_capture
def test_an_unexpected_error_in_a_slot_shows_one_dialog_and_is_logged(
    qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    shown: list[tuple[str, str]] = []
    source = _Source()

    def show(message: str, details: str) -> None:
        shown.append((message, details))
        if len(shown) == 1:
            source.fired.emit()  # a second error while the first dialog is open

    reporter = CrashReporter(show)

    def broken() -> None:
        raise ValueError("a slot broke")

    source.fired.connect(broken)
    previous = sys.excepthook
    sys.excepthook = reporter
    try:
        with caplog.at_level(logging.ERROR, logger="ctstudio.gui.crash"):
            source.fired.emit()
            QApplication.processEvents()
    finally:
        sys.excepthook = previous
    assert len(shown) == 1, "one dialog, not one per error"
    message, details = shown[0]
    assert "unexpected" in message.lower() and "ValueError: a slot broke" in details
    logged = [r for r in caplog.records if r.name == "ctstudio.gui.crash"]
    assert len(logged) == 2 and all("a slot broke" in r.getMessage() for r in logged)
    calm = CrashReporter(lambda message, details: shown.append((message, details)))
    sys.excepthook = calm
    try:
        source.fired.emit()  # a later, separate error shows its own dialog
        source.fired.emit()
    finally:
        sys.excepthook = previous
    assert len(shown) == 3, "after the first dialog closed, errors are shown again"
    later: list[str] = []
    source.fired.disconnect(broken)
    source.fired.connect(lambda: later.append("still running"))
    source.fired.emit()
    assert later == ["still running"]


def test_the_crash_dialog_copies_its_details(qtbot: QtBot, clipboard: QApplication) -> None:
    dialog = CrashDialog("CT Studio hit an unexpected error.", "Traceback: X")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.copy_button.click()
    assert clipboard.clipboard().text() == "Traceback: X"
    assert dialog.isVisible(), "copying closed the dialog"
    assert dialog.details.toPlainText() == "Traceback: X" and dialog.details.isReadOnly()


def test_install_reports_errors_for_the_rest_of_the_run() -> None:
    previous, previous_thread = sys.excepthook, threading.excepthook
    try:
        reporter = install()
        assert sys.excepthook is reporter and isinstance(reporter, CrashReporter)
        assert threading.excepthook == reporter.thread_hook
    finally:
        sys.excepthook, threading.excepthook = previous, previous_thread


def _on_gui_thread() -> bool:
    """Compared here, never stored: a pool thread's QThread wrapper dies with the thread."""
    app = QApplication.instance()
    return app is not None and QThread.currentThread() is app.thread()


class _Job(QRunnable):
    def __init__(self, reporter: CrashReporter, threads: list[bool]) -> None:
        super().__init__()
        self._reporter, self._threads = reporter, threads

    def run(self) -> None:
        self._threads.append(_on_gui_thread())
        try:
            raise ValueError("a pool job broke")
        except ValueError as exc:  # what Qt hands to sys.excepthook on the worker
            self._reporter(type(exc), exc, exc.__traceback__)


def test_a_worker_thread_error_is_shown_on_the_gui_thread(
    qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    shown: list[bool] = []
    reporter = CrashReporter(lambda message, details: shown.append(_on_gui_thread()))
    threads: list[bool] = []
    pool = QThreadPool()
    with caplog.at_level(logging.ERROR, logger="ctstudio.gui.crash"):
        pool.start(_Job(reporter, threads))
        assert pool.waitForDone(5000), "the worker waited on a dialog"
        assert shown == [], "the dialog ran on the worker thread"
        assert settled(qtbot, lambda: len(shown) == 1), "the report never reached the GUI thread"
    assert threads == [False] and shown == [True]
    assert any("a pool job broke" in r.getMessage() for r in caplog.records)


def test_a_python_thread_error_is_reported(qtbot: QtBot) -> None:
    shown: list[str] = []
    reporter = CrashReporter(lambda message, details: shown.append(details))
    previous = threading.excepthook
    threading.excepthook = reporter.thread_hook
    try:
        worker = threading.Thread(target=lambda: 1 / 0)
        worker.start()
        worker.join(5)
        stop = threading.Thread(target=lambda: sys.exit(0))  # SystemExit: a thread's own end
        stop.start()
        stop.join(5)
    finally:
        threading.excepthook = previous
    assert settled(qtbot, lambda: len(shown) == 1), "the thread error was not reported"
    assert "ZeroDivisionError" in shown[0]
    qtbot.wait(50)
    assert len(shown) == 1, "a thread ending with SystemExit was reported"


@pytest.mark.qt_no_exception_capture
def test_a_failing_error_window_is_logged_once_and_never_reports_itself(
    qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[str] = []

    def show(message: str, details: str) -> None:
        calls.append(details)
        if len(calls) == 1:
            raise RuntimeError("the window could not be built")

    reporter = CrashReporter(show)
    source = _Source()

    def broken() -> None:
        raise ValueError("first")

    source.fired.connect(broken)
    previous = sys.excepthook
    sys.excepthook = reporter
    try:
        with caplog.at_level(logging.ERROR, logger="ctstudio.gui.crash"):
            source.fired.emit()
            QApplication.processEvents()
    finally:
        sys.excepthook = previous
    assert len(calls) == 1, "the window's own failure was reported as another error"
    messages = [r.getMessage() for r in caplog.records if r.name == "ctstudio.gui.crash"]
    assert len(messages) == 2 and "itself failed" in messages[1]
    source.fired.disconnect(broken)
    calls.clear()
    sys.excepthook = reporter
    try:
        source.fired.connect(broken)
        source.fired.emit()  # the next error shows its window again
    finally:
        sys.excepthook = previous
    assert len(calls) == 1
