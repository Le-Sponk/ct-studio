"""One background job at a time, its result handed back on the GUI thread (Deep Clean #1 f).

``start`` runs ``work`` on a named daemon thread. Its return value, or the exception it
raised, reaches ``deliver`` on the thread that made the worker, and only after the worker
thread has ended (joined): a window never deletes or waits on a thread still running. A
thread that cannot start delivers that failure at once, so its owner is never left busy.
Each start has a serial: ``shutdown`` drops a result still on its way, and the worker can
start again afterwards (a refused window close keeps using it).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import cast

from PySide6.QtCore import QObject, Signal


class _Relay(QObject):
    done = Signal(object)  # (serial, the result or the exception)


class JoinedWorker:
    def __init__(
        self,
        name: str,
        deliver: Callable[[object], None],
        *,
        logger: logging.Logger,
        failure: str,
        expected: tuple[type[Exception], ...] = (),
        parent: QObject | None = None,
    ) -> None:
        """``failure`` is logged with an unexpected exception's trace; ``expected`` ones (a
        message for the user) are delivered without one. Without ``parent`` the relay
        outlives its owner, so a result sent during shutdown has somewhere to go."""
        self.name = name
        self._deliver = deliver
        self._logger, self._failure, self._expected = logger, failure, expected
        self._thread: threading.Thread | None = None
        self._serial = 0  # of the latest start; a result with an older one is dropped
        self._relay = _Relay(parent)
        self._relay.done.connect(self._done)

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(self, work: Callable[[], object]) -> None:
        relay, logger, failure, expected = self._relay, self._logger, self._failure, self._expected
        self._serial += 1  # owners never start while busy; this only guards one that would
        serial = self._serial

        def job() -> None:
            result: object
            try:
                result = work()
            except expected as exc:
                result = exc
            except Exception as exc:  # any failure must reach the window, not end the thread
                logger.exception(failure)
                result = exc
            relay.done.emit((serial, result))

        thread = threading.Thread(target=job, name=self.name, daemon=True)
        self._thread = thread
        try:
            thread.start()
        except Exception as exc:  # no thread, so no result will come: deliver the failure now
            self._thread = None
            self._deliver(exc)

    def shutdown(self, timeout: float) -> bool:
        """Wait up to ``timeout`` s; True when no thread is left and its result is dropped."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                return False
        self._thread = None
        self._serial += 1
        return True

    def _done(self, payload: object) -> None:
        serial, result = cast("tuple[int, object]", payload)
        if serial != self._serial:
            return  # from before a shutdown: its thread is already joined
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join()  # it has sent its result: wait for its last step before going on
        self._deliver(result)
