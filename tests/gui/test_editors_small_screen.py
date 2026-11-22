"""P5-T07f2: the Editors window pictures again on a real 800x600 screen.

The shared offscreen test screen is 800x800, which hides height problems. Qt picks its
screen when the application starts, so this runs both picture files in a fresh process
whose offscreen screen is 800x600 (described in a small JSON file), with a temporary path
longer than a CI runner's.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.gui, pytest.mark.timeout(240)]
ROOT = Path(__file__).resolve().parents[2]
PICTURES = ["tests/gui/test_editor_settings_visual.py", "tests/gui/test_custom_editors_visual.py"]
SCREEN = {
    "synchronousWindowSystemEvents": False,
    "windowFrameMargins": False,
    "screens": [
        {
            "name": "small",
            "x": 0,
            "y": 0,
            "width": 800,
            "height": 600,
            "logicalDpi": 96,
            "logicalBaseDpi": 96,
            "dpr": 1,
        }
    ],
}
SHOW = (
    "from PySide6.QtWidgets import QApplication as A; a = A([]); "
    "g = a.primaryScreen().availableGeometry(); print(g.width(), g.height())"
)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    # A relative file name: Qt splits platform options at ":", so "C:\..." cannot be used.
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen:configfile=screen.json")
    env["PYTHONIOENCODING"] = "utf-8"  # read back as UTF-8 whatever the system code page
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    return subprocess.run(  # noqa: S603 - argv uses our own interpreter, no shell
        [sys.executable, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=200,
    )


def test_editors_window_pictures_fit_an_800x600_screen(tmp_path: Path) -> None:
    (tmp_path / "screen.json").write_text(json.dumps(SCREEN), encoding="utf-8")
    shown = _run(["-c", SHOW], tmp_path)
    assert shown.stdout.split() == ["800", "600"], shown.stdout + shown.stderr
    # Deeper than a CI runner's temporary folder, so the banner has room to spare there.
    folder = tmp_path / "second-level-folder" / "third-level-folder-abc"
    while len(str(folder)) < 90:  # also with a short --basetemp: add ordinary folders
        folder = folder / "more-folder-depth"
    basetemp = folder / "basetemp"
    basetemp.parent.mkdir(parents=True)  # pytest makes only the last folder
    pictures = [str(ROOT / name) for name in PICTURES]
    args = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(ROOT)]
    result = _run([*args, "--basetemp", str(basetemp), *pictures], tmp_path)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
    assert " passed" in result.stdout and "failed" not in result.stdout, result.stdout[-2000:]
