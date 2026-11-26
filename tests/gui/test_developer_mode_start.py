"""P5-T08e3 acceptance: with developer mode saved on, the next start of CT Studio runs the
stall watchdog; saved off (or absent, or a damaged settings file), it does not, unless
``CTSTUDIO_DEV=1`` asks for it as before.

The start is the real ``python -m ctstudio --offscreen-smoke`` in a new process, with its
own user folders (settings and the app log); developer mode says so in the app log when the
watchdog starts. ``dev_watchdog`` is also checked in this process for the watching thread.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from ctstudio.core.project import settings
from ctstudio.core.project.settings import DEVELOPER_MODE
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.watchdog import DEV_FLAG, WATCHDOG_ON, WATCHDOG_THREAD, dev_watchdog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(90)]
WAIT = 5000


def watching() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == WATCHDOG_THREAD and t.is_alive()]


def write(text: str) -> None:
    path = settings.default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("saved", "flag", "on"),
    [
        (None, None, False),
        ('{"developer_mode": false}', None, False),
        ('{"developer_mode": true}', None, True),
        ('{"developer_mode": "yes"}', None, False),  # damaged: off
        ('{"developer_mode": false}', "1", True),  # the variable still turns it on
        (None, "0", False),
        ('{"developer_mode": true}', "0", True),  # the variable only adds
    ],
    ids=["absent", "off", "on", "damaged", "off-but-CTSTUDIO_DEV", "CTSTUDIO_DEV-0", "on-dev-0"],
)
def test_the_window_is_watched_only_in_developer_mode(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    saved: str | None,
    flag: str | None,
    on: bool,
) -> None:
    if flag is None:
        monkeypatch.delenv(DEV_FLAG, raising=False)
    else:
        monkeypatch.setenv(DEV_FLAG, flag)
    if saved is not None:
        write(saved)
    window = MainWindow()  # not given to qtbot: this test deletes it
    caplog.set_level("INFO", logger="ctstudio.gui.watchdog")
    made = dev_watchdog(window)
    try:
        assert (made is not None) is on, f"developer mode was {'off' if on else 'on'}"
        assert len(watching()) == (1 if on else 0)
        assert (WATCHDOG_ON in caplog.text) is on, caplog.text
        if saved == '{"developer_mode": "yes"}':
            assert "Developer mode is off" in caplog.text, caplog.text
    finally:
        window.deleteLater()
        qtbot.waitUntil(lambda: watching() == [], timeout=WAIT)
    if saved is not None:
        assert settings.default_path().read_text(encoding="utf-8") == saved


def start(tmp_path: Path, saved: object) -> str:
    """Start CT Studio once in a new process; its app log."""
    users = tmp_path / "users é"
    env = {key: value for key, value in os.environ.items() if key != DEV_FLAG}
    for name in ("WIN_PD_OVERRIDE_LOCAL_APPDATA", "WIN_PD_OVERRIDE_APPDATA"):
        env[name] = str(users / name)
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        env[name] = str(users / name)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"  # the folder name is not ASCII
    find = "import ctstudio.core.project.settings as s; print(s.default_path())"
    found = subprocess.run(  # noqa: S603 - argv uses our Python, no shell
        [sys.executable, "-c", find],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=True,
    )
    path = Path(found.stdout.strip())
    assert users in path.parents, f"the settings file {path} is outside the test's folders"
    if saved is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({DEVELOPER_MODE: saved}), encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - argv uses our Python module, no shell
        [sys.executable, "-m", "ctstudio", "--offscreen-smoke", str(tmp_path / "shot.png")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr  # an error the smoke run hid
    logs = list(users.rglob("ctstudio.log"))
    assert len(logs) == 1, f"the start wrote {len(logs)} app logs"
    return logs[0].read_text(encoding="utf-8")


@pytest.mark.parametrize(("saved", "on"), [(True, True), (False, False), (None, False)])
def test_the_next_start_runs_the_watchdog_only_when_developer_mode_is_saved_on(
    tmp_path: Path, saved: bool | None, on: bool
) -> None:
    log = start(tmp_path, saved)
    assert (WATCHDOG_ON in log) is on, log[-2000:]
