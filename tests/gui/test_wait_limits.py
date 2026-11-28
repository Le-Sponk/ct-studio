"""The suite's default qtbot wait stays inside each test's own time limit (Deep Clean #1)."""

from __future__ import annotations

import inspect
import time

import pytest
from pytestqt.exceptions import TimeoutError as QtTimeout
from pytestqt.qtbot import QtBot
from waits import LIMIT_MS, wait_limit_ms

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize(
    ("budget_s", "expected_ms"),
    [(None, LIMIT_MS), (300, LIMIT_MS), (30, 20_000), (20, 10_000), (15, 5_000), (10, 5_000)],
)
def test_the_default_limit_fits_the_test_budget(budget_s: float | None, expected_ms: int) -> None:
    assert wait_limit_ms(budget_s) == expected_ms


@pytest.mark.timeout(17)
def test_a_waituntil_without_timeout_gets_the_budgeted_limit() -> None:
    default = inspect.signature(QtBot.waitUntil).parameters["timeout"].default
    assert default == 7_000, "17 s budget less 10 s spare"


def test_the_module_limit_applies_without_a_test_marker() -> None:
    default = inspect.signature(QtBot.waitUntil).parameters["timeout"].default
    assert default == 20_000, "this module allows 30 s"


def test_an_explicit_timeout_is_kept(qtbot: QtBot) -> None:
    started = time.monotonic()
    timed_out = False
    try:
        qtbot.waitUntil(lambda: False, timeout=200)
    except QtTimeout:
        timed_out = True
    assert timed_out and time.monotonic() - started < 3
