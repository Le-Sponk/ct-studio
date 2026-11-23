"""Run Python's cyclic garbage collector only on the GUI thread (TD-017).

Automatic collection runs on whichever thread happens to allocate. When that is a worker
(the file watcher), it can free Qt objects that belong to the GUI thread, with their signal
connections, while the GUI thread is connecting signals: a crash, or a deadlock where each
thread holds what the other needs (Python's GIL, the global interpreter lock, and a Qt
signal-connection lock). With automatic collection off, a GUI-thread timer collects by the
same generation thresholds Python itself uses (Python 3.12 semantics; the 3.14 incremental
collector changes what the counts mean). This does not cover a worker dropping the last
reference to a GUI-thread Qt object, which reaches the same cleanup without any collection.
"""

from __future__ import annotations

import gc
import threading

from PySide6.QtCore import QObject, QTimer

INTERVAL_MS = 200


def collect_if_due() -> int | None:
    """Collect the oldest due generation, on the GUI (main) thread only; None if nothing ran."""
    if threading.current_thread() is not threading.main_thread():
        return None
    counts = gc.get_count()
    limits = gc.get_threshold()
    if limits[0] == 0 or counts[0] <= limits[0]:  # 0 means "never" to Python too
        return None
    generation = max(g for g in range(3) if counts[g] > limits[g])
    gc.collect(generation)
    return generation


class GuiThreadCollector(QObject):
    """Turns automatic collection off while started; collects from a GUI-thread timer."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._was_enabled = gc.isenabled()
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._was_enabled = gc.isenabled()
        gc.disable()
        self._timer.start()

    def stop(self, *, restore: bool = True) -> None:
        """Stop the timer; turn automatic collection back on only if it was on and ``restore``."""
        self._timer.stop()
        if restore and self._was_enabled:
            gc.enable()

    def _tick(self) -> None:
        collect_if_due()
