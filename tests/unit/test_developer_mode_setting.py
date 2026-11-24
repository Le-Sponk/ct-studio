"""P5-T08e3: developer mode on this computer (``developer_mode``).

A machine setting in ``settings.json``: true or false, absent means off. Anything else makes
the file damaged: it is refused by load and by save and never overwritten. The GUI reads it
once at start (``gui.watchdog.dev_watchdog``); ``CTSTUDIO_DEV=1`` still turns developer mode
on whatever the file says.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from ctstudio.core.project.settings import (
    DEVELOPER_MODE,
    SettingsError,
    UserSettings,
    load,
    save,
)

pytestmark = pytest.mark.timeout(30)
BAD: list[object] = ["true", "on", 0, 1, None, [], {"on": True}]


def outcome(call: Callable[[], object]) -> object:
    try:
        return call()
    except Exception as exc:  # the error is the result looked at
        return exc


def test_absent_means_off_and_a_saved_choice_reads_back(tmp_path: Path) -> None:
    path = tmp_path / "settings é.json"
    assert UserSettings().developer_mode() is False
    save(UserSettings().with_developer_mode(True), path)
    assert json.loads(path.read_text(encoding="utf-8"))[DEVELOPER_MODE] is True
    assert load(path).developer_mode() is True
    save(load(path).with_developer_mode(False), path)
    assert load(path).developer_mode() is False
    assert json.loads(path.read_text(encoding="utf-8"))[DEVELOPER_MODE] is False
    save(load(path).with_developer_mode(None), path)
    assert DEVELOPER_MODE not in json.loads(path.read_text(encoding="utf-8"))


def test_other_keys_survive(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"format": 1, "future": [1], "show_tool_commands": false}', encoding="utf-8")
    save(load(path).with_developer_mode(True), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {
        "format": 1,
        "future": [1],
        "show_tool_commands": False,
        DEVELOPER_MODE: True,
        "tools": {},
    }


@pytest.mark.parametrize("bad", BAD, ids=[repr(b) for b in BAD])
def test_a_bad_value_makes_the_file_damaged_and_it_is_never_overwritten(
    tmp_path: Path, bad: object
) -> None:
    path = tmp_path / "settings.json"
    text = json.dumps({"format": 1, DEVELOPER_MODE: bad}) + "\n"
    path.write_text(text, encoding="utf-8")
    error = outcome(lambda: load(path))
    assert isinstance(error, SettingsError), f"{bad!r} was accepted: {error!r}"
    assert f'"{DEVELOPER_MODE}" is not true or false' in str(error)
    refused = outcome(lambda: save(UserSettings(other={DEVELOPER_MODE: bad}), path))
    assert isinstance(refused, SettingsError), f"{bad!r} was saved: {refused!r}"
    assert path.read_text(encoding="utf-8") == text
    assert list(tmp_path.iterdir()) == [path], "a backup was made"
    if bad is not None:  # None asks for the default
        copied = outcome(lambda: UserSettings().with_developer_mode(bad))  # type: ignore[arg-type]
        assert isinstance(copied, ValueError), f"{bad!r} was copied in: {copied!r}"
        assert f'"{DEVELOPER_MODE}" must be true or false' in str(copied), copied
