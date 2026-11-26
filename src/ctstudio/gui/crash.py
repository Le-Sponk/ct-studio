"""Errors nothing handled: logged, shown once, and CT Studio keeps running (P5-T10f, D4).

Qt reports an exception raised in a slot or an event handler to ``sys.excepthook`` and
carries on; one escaping a thread-pool job or a ``QThread`` reaches the same hook on that
worker thread, and one escaping a Python thread reaches ``threading.excepthook``. ``install``
makes both hooks report to a ``CrashReporter``: the traceback goes to the log every time, on
any thread, and a dialog with Copy details shows on the GUI thread (a worker's report is
queued there) unless one is already open (an error while it is up is logged only). Without a
QApplication nothing is shown. Expected problems are never reported this way: they are
``CTStudioError``s caught where they happen and shown inline.
"""

from __future__ import annotations

import logging
import sys
import threading
import traceback
from collections.abc import Callable
from types import TracebackType

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QApplication

from ctstudio.gui.views.crash_dialog import CrashDialog

_LOG = logging.getLogger(__name__)
MESSAGE = (
    "CT Studio hit an unexpected error. It has been written to the log and you can keep "
    "working; if anything looks wrong, save your work and restart CT Studio."
)
Show = Callable[[str, str], None]


def _dialog(message: str, details: str) -> None:
    dialog = CrashDialog(message, details, QApplication.activeWindow())
    dialog.exec()
    dialog.deleteLater()


class _Relay(QObject):
    """Lives on the GUI thread: a report emitted on a worker is delivered there, queued."""

    report = Signal(str)

    def __init__(self, present: Callable[[str], None]) -> None:
        super().__init__()
        self._present = present
        self.report.connect(self._deliver)

    @Slot(str)
    def _deliver(self, details: str) -> None:
        self._present(details)


class CrashReporter:
    """Create it on the GUI thread, after the QApplication."""

    def __init__(self, show: Show = _dialog) -> None:
        self._show = show
        self._open = False
        self._relay = _Relay(self._present)

    def __call__(
        self, kind: type[BaseException], value: BaseException, tb: TracebackType | None
    ) -> None:
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, value, tb)
            return
        details = "".join(traceback.format_exception(kind, value, tb))
        _LOG.error("Unexpected error:\n%s", details)
        if QApplication.instance() is not None:
            self._relay.report.emit(details)  # direct on the GUI thread, else queued there

    def thread_hook(self, args: threading.ExceptHookArgs) -> None:
        """``threading.excepthook``: a Python thread's error, reported the same way."""
        if args.exc_value is not None and not issubclass(args.exc_type, SystemExit):
            self(args.exc_type, args.exc_value, args.exc_traceback)

    def _present(self, details: str) -> None:
        if self._open:
            return  # one dialog at a time; this one is in the log
        self._open = True
        try:
            self._show(MESSAGE, details)
        except Exception:  # never back into the hook: that would report itself forever
            _LOG.exception("The unexpected-error window itself failed")
        finally:
            self._open = False


def install() -> CrashReporter:
    """Report errors nothing handled for the rest of this run (call on the GUI thread)."""
    reporter = CrashReporter()
    sys.excepthook = reporter
    threading.excepthook = reporter.thread_hook
    return reporter
