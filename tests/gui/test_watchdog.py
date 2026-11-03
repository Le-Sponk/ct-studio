"""P5-T01b: in dev mode a UI-thread stall over 100 ms is logged with the UI thread's stack."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QObject
from pytestqt.qtbot import QtBot

from ctstudio.gui import watchdog
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.watchdog import WATCHDOG_THREAD, StallWatchdog, dev_watchdog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
WAIT = 10_000


@pytest.fixture
def reports() -> list[str]:
    return []


_MADE: list[StallWatchdog] = []


@pytest.fixture(autouse=True)
def _stop_all() -> Iterator[None]:
    yield
    while _MADE:
        assert _MADE.pop().stop(WAIT / 1000)


def started(reports: list[str], threshold: float = 0.1) -> StallWatchdog:
    made = StallWatchdog(threshold=threshold, report=reports.append)
    _MADE.append(made)
    made.start()
    return made


def watchdog_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == WATCHDOG_THREAD]


def _block_the_ui_thread(seconds: float) -> None:
    time.sleep(seconds)  # what a view must never do: wait on the UI thread


def test_an_injected_sleep_on_the_ui_thread_is_logged_with_its_stack(
    qtbot: QtBot, reports: list[str]
) -> None:
    started(reports)
    qtbot.wait(50)  # the heartbeat is running
    _block_the_ui_thread(0.2)
    qtbot.wait(50)
    assert len(reports) == 1
    assert "UI thread" in reports[0]
    assert "100 ms" in reports[0]
    assert "_block_the_ui_thread" in reports[0]  # the stack shows where it was stuck
    assert "time.sleep(seconds)" in reports[0]


def test_each_stall_is_logged_once_and_a_second_one_again(qtbot: QtBot, reports: list[str]) -> None:
    started(reports)
    qtbot.wait(50)
    _block_the_ui_thread(0.35)  # long enough to be seen many times over
    qtbot.wait(50)
    assert len(reports) == 1
    _block_the_ui_thread(0.2)
    qtbot.wait(50)
    assert len(reports) == 2


def test_an_idle_ui_is_not_logged(qtbot: QtBot, reports: list[str]) -> None:
    # Busy CI runners can pause a whole process now and then, so idle is held to 250 ms here.
    started(reports, threshold=0.25)
    qtbot.wait(600)
    assert reports == []


def test_a_short_wait_is_not_a_stall(qtbot: QtBot, reports: list[str]) -> None:
    started(reports, threshold=0.25)
    qtbot.wait(50)
    _block_the_ui_thread(0.1)
    qtbot.wait(300)
    assert reports == []


def test_by_default_a_stall_goes_to_the_log(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    logged: list[str] = []

    class Log:
        def warning(self, text: str) -> None:
            logged.append(text)

    monkeypatch.setattr(watchdog, "_LOG", Log())
    made = StallWatchdog()
    _MADE.append(made)
    made.start()
    qtbot.wait(50)
    _block_the_ui_thread(0.2)
    qtbot.wait(50)
    assert len(logged) == 1
    assert "_block_the_ui_thread" in logged[0]


def test_stop_ends_the_watching_thread(qtbot: QtBot, reports: list[str]) -> None:
    made = started(reports)
    assert made.watching
    assert len(watchdog_threads()) == 1
    assert made.stop(WAIT / 1000)
    assert not made.watching
    assert watchdog_threads() == []
    _block_the_ui_thread(0.2)  # nobody is watching any more
    qtbot.wait(50)
    assert reports == []
    assert made.stop(1)  # twice is harmless


def test_the_app_watches_its_window_in_dev_mode_and_stops_when_it_ends(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from PySide6.QtWidgets import QApplication

    from ctstudio.gui import app

    calls: list[str] = []

    class Watching:
        def stop(self, timeout: float) -> bool:
            calls.append(f"stop {timeout}")
            return True

    def fake_watchdog(window: QObject) -> Watching:
        calls.append(type(window).__name__)
        return Watching()

    monkeypatch.setattr(app, "QApplication", lambda _argv: QApplication.instance())
    monkeypatch.setattr(app, "dev_watchdog", fake_watchdog)
    assert app.run_gui(tmp_path / "écran.png") == 0
    assert calls == ["MainWindow", "stop 1.0"]


# --- dev mode only ------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "0", "yes"])
def test_without_dev_mode_nothing_watches(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("CTSTUDIO_DEV", raising=False)
    else:
        monkeypatch.setenv("CTSTUDIO_DEV", value)
    window = MainWindow()
    qtbot.addWidget(window)
    assert dev_watchdog(window) is None
    assert watchdog_threads() == []


def test_in_dev_mode_the_window_is_watched_until_it_goes(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CTSTUDIO_DEV", "1")
    window = MainWindow()  # not given to qtbot: this test deletes it
    made = dev_watchdog(window)
    assert made is not None
    assert len(watchdog_threads()) == 1
    window.deleteLater()  # the window going away stops the watching
    qtbot.waitUntil(lambda: watchdog_threads() == [], timeout=WAIT)
