"""One bounded wait for GUI tests (P5-GATE review: three copies had 5 s and 10 s limits).

``settled`` never raises: it returns the condition's final value so the test asserts it, and a
slow machine is a wrong answer only after a generous limit. A full-suite run once took over
5 s for a reconcile step that passes alone in well under one (TD-018's whole-process stall).
The limit is elapsed time, so it stays inside a module's pytest-timeout; a file that uses the
default must allow at least ``LIMIT_MS`` plus its own setup (30 s or more).
"""

from __future__ import annotations

import time

from pytestqt.qtbot import QtBot

LIMIT_MS = 20_000
QT_DEFAULT_MS = 5_000  # pytest-qt's own waitUntil default
SPARE_S = 10  # left of a test's time limit for its setup and teardown


def wait_limit_ms(budget_s: float | None) -> int:
    """Default ``qtbot.waitUntil`` limit for a test allowed ``budget_s`` seconds (None: no limit).

    Up to ``LIMIT_MS``, but never so long that pytest-timeout ends the whole run first (a
    timeout stops the session, not just the test); never below pytest-qt's 5 s.
    """
    if budget_s is None:
        return LIMIT_MS
    return int(max(QT_DEFAULT_MS, min(LIMIT_MS, (budget_s - SPARE_S) * 1000)))


def settled(qtbot: QtBot, cond: object, timeout_ms: int = LIMIT_MS) -> bool:
    """Bounded wait that never raises, so a broken condition fails an assertion."""
    assert callable(cond)
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if cond():
            return True
        qtbot.wait(10)
    return bool(cond())
