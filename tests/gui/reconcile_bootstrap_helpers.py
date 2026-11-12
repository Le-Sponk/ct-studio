"""Pause CPython native bootstrap without using private APIs in production."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# Test-only ownership observation and dynamic CPython bootstrap hooks.
import threading
from collections.abc import Callable
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication

from ctstudio.gui.launch_controller import THREAD_NAME, LaunchController


class BootstrapPause:
    def __init__(self, owner: LaunchController, error: BaseException, hook: str) -> None:
        self.owner, self.error, self.hook = owner, error, hook
        self.reached, self.release = threading.Event(), threading.Event()
        self.workers: list[threading.Thread] = []
        self.original_hook = cast(Callable[[threading.Thread], None], vars(threading.Thread)[hook])
        self.original_wait = threading.Event.wait

    def bootstrap(self, thread: threading.Thread) -> None:
        if thread.name == THREAD_NAME:
            self.workers.append(thread)
            self.reached.set()
            assert self.original_wait(self.release, 10), "bootstrap was not released"
        self.original_hook(thread)

    def wait(self, event: threading.Event, timeout: float | None = None) -> bool:
        worker = self.owner._thread
        if worker is not None and event is vars(worker)["_started"]:
            assert self.original_wait(self.reached, 10), "native worker did not enter bootstrap"
            raise self.error
        return self.original_wait(event, timeout)

    def install(self, patch: pytest.MonkeyPatch) -> None:
        def bootstrap(thread: threading.Thread) -> None:
            self.bootstrap(thread)

        def wait(event: threading.Event, timeout: float | None = None) -> bool:
            return self.wait(event, timeout)

        patch.setattr(threading.Thread, self.hook, bootstrap)
        patch.setattr(threading.Event, "wait", wait)

    def finish(self, gate: threading.Event) -> None:
        self.release.set()
        gate.set()
        assert self.workers, "bootstrap probe did not create its native thread"
        worker = self.workers[0]
        started = cast(threading.Event, vars(worker)["_started"])
        assert started.wait(10), "bootstrap acknowledgement never arrived"
        worker.join(10)
        assert not worker.is_alive(), "bootstrap probe leaked its native thread"
        QCoreApplication.sendPostedEvents()
