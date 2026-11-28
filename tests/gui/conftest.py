"""Initialize the headless Qt platform before pytest-qt creates QApplication."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from waits import wait_limit_ms

from ctstudio.core.project import settings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_gui_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GUI startup now reads recent projects; never read or change the developer's settings."""
    monkeypatch.setattr(settings, "default_path", lambda: tmp_path / "user é" / "settings.json")


@pytest.fixture(autouse=True)
def patient_waits(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """``qtbot.waitUntil`` without a timeout waits up to 20 s, within the test's time limit.

    Full local gates twice failed on a 5 s default while the dashboard's status check ran
    slower under load (Deep Clean #1); a call that passes its own timeout keeps it.
    """
    node: pytest.Item = getattr(request, "node")  # noqa: B009 - FixtureRequest.node is untyped
    marker = node.get_closest_marker("timeout")
    budget = float(marker.args[0]) if marker is not None and marker.args else None
    limit = wait_limit_ms(budget)
    original = QtBot.waitUntil

    def wait_until(
        self: QtBot, callback: Callable[[], bool | None], *, timeout: int = limit
    ) -> None:
        original(self, callback, timeout=timeout)

    monkeypatch.setattr(QtBot, "waitUntil", wait_until)
