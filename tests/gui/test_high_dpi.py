"""P5-T10h: the populated dashboard and Settings at 1.5x and 2x (high-DPI evidence).

Each scale runs hidpi_checks.py in its own pytest process, because QT_SCALE_FACTOR only
takes effect before the QApplication exists. The child gets a realistic offscreen screen
(1280x720 logical at its scale: 1920x1080 pixels at 1.5x, 2560x1440 at 2x) instead of Qt's
800x800 pixel default. Pictures: tests/artifacts/screens/p5-t10h-*.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from wizard_fakes import SCREENS

pytestmark = [pytest.mark.gui, pytest.mark.timeout(300)]
CHECKS = Path(__file__).with_name("hidpi_checks.py").resolve()
LOGICAL = (1280, 720)
DROPPED = ("QT_", "PYTEST_", "COV_CORE_")  # the parent's own Qt, pytest and coverage set-up


def child_env(factor: float) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith(DROPPED)}
    env["QT_SCALE_FACTOR"] = str(factor)
    # Qt splits platform options at ":", so the screen file is named relative to the cwd.
    env["QT_QPA_PLATFORM"] = "offscreen:configfile=screen.json"
    return env


def screen_file(folder: Path, factor: float) -> None:
    width, height = (round(side * factor) for side in LOGICAL)
    screen = {"name": "hidpi", "x": 0, "y": 0, "width": width, "height": height}
    screen |= {"logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}
    (folder / "screen.json").write_text(json.dumps({"screens": [screen]}), encoding="utf-8")


@pytest.mark.parametrize("factor", [1.5, 2.0], ids=["150pct", "200pct"])
def test_dashboard_and_settings_hold_up_at_high_dpi(tmp_path: Path, factor: float) -> None:
    screen_file(tmp_path, factor)
    argv = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q"]
    argv += [f"--basetemp={(tmp_path / 'child').as_posix()}", f"--rootdir={CHECKS.parents[2]}"]
    result = subprocess.run(  # noqa: S603 - argv is our own Python and test file, no shell
        [*argv, str(CHECKS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
        check=False,
        env=child_env(factor),
        cwd=tmp_path,
    )
    tail = result.stdout[-3000:] + result.stderr[-1500:]
    assert result.returncode == 0, tail
    assert re.search(r"\b3 passed\b", result.stdout), tail
    percent = f"{round(factor * 100)}pct"
    picture = QImage(str(SCREENS / f"p5-t10h-dashboard-{percent}.png"))
    assert picture.width() >= LOGICAL[0] * factor, "the dashboard picture is not at the scale"
    for page in ("tools", "editors"):
        assert (SCREENS / f"p5-t10h-settings-{page}-{percent}.png").stat().st_size > 0
