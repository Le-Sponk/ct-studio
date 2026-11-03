"""Dev mode: log the UI thread's stack when it stalls (P5-T01b, ARCHITECTURE §10).

``StallWatchdog`` keeps a heartbeat on the UI thread (a timer) and a named watcher thread
(``ctstudio-watchdog``). When the heartbeat is older than ``threshold`` (100 ms), the watcher
logs where the UI thread is stuck, once per stall. ``dev_watchdog(window)`` starts one only
when ``CTSTUDIO_DEV=1`` and stops it when the window goes.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, QTimer

_LOG = logging.getLogger(__name__)
WATCHDOG_THREAD = "ctstudio-watchdog"
DEV_FLAG = "CTSTUDIO_DEV"


class StallWatchdog:
    """Create and start on the UI thread; ``stop`` there too."""

    def __init__(
        self, *, threshold: float = 0.1, report: Callable[[str], None] | None = None
    ) -> None:
        self.threshold = threshold
        self._report = report if report is not None else _log
        self._timer = QTimer()
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(1, int(threshold * 1000 / 4)))
        self._timer.timeout.connect(self._beat)
        self._last = time.monotonic()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._ui = threading.get_ident()

    @property
    def watching(self) -> bool:
        """The heartbeat or the watcher thread is still going."""
        return self._timer.isActive() or self._thread is not None

    def start(self) -> None:
        self._last = time.monotonic()
        self._timer.start()
        self._thread = threading.Thread(target=self._watch, name=WATCHDOG_THREAD, daemon=True)
        self._thread.start()

    def stop(self, timeout: float) -> bool:
        """Stop watching; True when the watcher thread has ended."""
        self._timer.stop()
        self._stopping.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                return False
        self._thread = None
        return True

    def _beat(self) -> None:
        self._last = time.monotonic()

    def _watch(self) -> None:
        told: float | None = None  # the heartbeat of the stall already logged
        while not self._stopping.wait(self.threshold / 4):
            last = self._last
            if time.monotonic() - last > self.threshold and told != last:
                told = last
                self._report(self._where())

    def _where(self) -> str:
        frame = sys._current_frames().get(self._ui)  # the documented way to see it
        stack = "".join(traceback.format_stack(frame)) if frame is not None else "(unknown)\n"
        limit = f"{self.threshold * 1000:.0f} ms"
        return f"The UI thread has not responded for over {limit}. It was here:\n{stack}"


def _log(text: str) -> None:
    _LOG.warning(text)


def dev_watchdog(window: QObject) -> StallWatchdog | None:
    """A started watchdog in dev mode (``CTSTUDIO_DEV=1``), stopped with ``window``."""
    if os.environ.get(DEV_FLAG) != "1":
        return None
    made = StallWatchdog()
    made.start()
    window.destroyed.connect(lambda: made.stop(1.0))
    return made
