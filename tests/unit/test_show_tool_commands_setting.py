"""P5-T08e1: whether the dashboard's build log shows tool commands (``show_tool_commands``).

A machine setting in ``settings.json``: absent means shown (as before the setting existed),
otherwise ``true`` or ``false``. Anything else makes the file damaged: it is refused by load
and by save and never overwritten.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from ctstudio.core.project.settings import (
    SHOW_TOOL_COMMANDS,
    SettingsError,
    UserSettings,
    load,
    save,
)

pytestmark = pytest.mark.timeout(60)


def _file(tmp_path: Path) -> Path:
    return tmp_path / "config é" / "settings.json"


def outcome(call: Callable[[], object]) -> object:
    """What ``call`` returned, or the exception it raised."""
    try:
        return call()
    except Exception as exc:
        return exc


def test_the_key() -> None:
    assert SHOW_TOOL_COMMANDS == "show_tool_commands"


def test_no_choice_means_shown() -> None:
    assert UserSettings().show_tool_commands() is True
    assert UserSettings(other={"future": 1}).show_tool_commands() is True


@pytest.mark.parametrize("shown", [False, True])
def test_a_choice_is_saved_read_back_and_cleared(tmp_path: Path, shown: bool) -> None:
    path = _file(tmp_path)
    save(UserSettings(other={"future": [1]}).with_show_tool_commands(shown), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[SHOW_TOOL_COMMANDS] is shown
    assert data["future"] == [1], "a key this version does not know was lost"
    assert load(path).show_tool_commands() is shown
    save(load(path).with_show_tool_commands(None), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert SHOW_TOOL_COMMANDS not in data, "going back to the default left the key behind"
    assert load(path).show_tool_commands() is True
    assert data["future"] == [1]


def test_with_show_tool_commands_keeps_everything_else() -> None:
    before = UserSettings(tools={"wszst": "C:/w.exe"}, other={"build_jobs": 3})
    after = before.with_show_tool_commands(False)
    assert after.tools == before.tools
    assert after.other == {"build_jobs": 3, SHOW_TOOL_COMMANDS: False}
    assert before.show_tool_commands() is True, "the original settings changed"


BAD: list[object] = ["false", "yes", 0, 1, None, [], {"shown": True}]


@pytest.mark.parametrize("value", BAD, ids=repr)
def test_any_other_value_makes_the_file_damaged(tmp_path: Path, value: object) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    text = json.dumps({"format": 1, SHOW_TOOL_COMMANDS: value}) + "\n"
    path.write_text(text, encoding="utf-8")
    error = outcome(lambda: load(path))
    assert isinstance(error, SettingsError), f"{value!r} was accepted: {error!r}"
    assert f'"{SHOW_TOOL_COMMANDS}" is not true or false' in str(error)
    assert error.path == path
    assert path.read_text(encoding="utf-8") == text, "loading changed the file"


@pytest.mark.parametrize("value", BAD, ids=repr)
def test_a_bad_value_is_never_saved(tmp_path: Path, value: object) -> None:
    path = _file(tmp_path)
    save(UserSettings(), path)
    before = path.read_bytes()
    error = outcome(lambda: save(UserSettings(other={SHOW_TOOL_COMMANDS: value}), path))
    assert isinstance(error, SettingsError), f"{value!r} was saved"
    assert path.read_bytes() == before, "a refused save changed the file"
    assert not list(path.parent.glob("*.bak*")), "a refused save made a backup"


@pytest.mark.parametrize("value", [bad for bad in BAD if bad is not None], ids=repr)
def test_with_show_tool_commands_refuses_a_bad_value(value: object) -> None:
    error = outcome(lambda: UserSettings().with_show_tool_commands(cast("bool", value)))
    assert isinstance(error, ValueError), f"{value!r} was taken: {error!r}"


def test_reading_a_bad_value_through_the_object_raises() -> None:
    error = outcome(lambda: UserSettings(other={SHOW_TOOL_COMMANDS: "no"}).show_tool_commands())
    assert isinstance(error, ValueError), f"a bad value was read: {error!r}"
