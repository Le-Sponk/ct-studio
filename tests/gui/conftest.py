"""Initialize the headless Qt platform before pytest-qt creates QApplication."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ctstudio.core.project import settings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_gui_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GUI startup now reads recent projects; never read or change the developer's settings."""
    monkeypatch.setattr(settings, "default_path", lambda: tmp_path / "user é" / "settings.json")
