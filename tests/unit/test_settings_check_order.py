"""Deep Clean #1: the settings checks run as one ordered table on load and on save.

The first invalid entry, in this order, is the reason the user reads; every reason is pinned.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from ctstudio.core.project import settings
from ctstudio.core.project.settings import SettingsError, UserSettings

# (key, an invalid value, the reason it gives), in the order the checks run.
INVALID: list[tuple[str, object, str]] = [
    ("editor_preferences", "not a table", "editor preferences are invalid"),
    ("custom_tools", "not a table", "custom tools are invalid"),
    ("wine_prefixes", "not a table", "Wine prefixes are invalid"),
    ("build_jobs", 0, '"build_jobs" is not a whole number from 1 to 64'),
    ("colour_scheme", "blue", '"colour_scheme" is not "light" or "dark"'),
    ("show_tool_commands", "yes", '"show_tool_commands" is not true or false'),
    ("build_logs_kept", 0, '"build_logs_kept" is not a whole number from 1 to 1000'),
    ("developer_mode", "on", '"developer_mode" is not true or false'),
]


def refusal(call: Callable[[], object]) -> str:
    """The SettingsError's message (asserted, so a missing refusal fails an assertion)."""
    try:
        call()
    except SettingsError as exc:
        return exc.user_message
    raise AssertionError("the invalid settings were accepted")


def loaded_reason(tmp_path: Path, entries: dict[str, object]) -> str:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"format": 1, **entries}), encoding="utf-8")
    return refusal(lambda: settings.load(path))


def saved_reason(tmp_path: Path, entries: dict[str, object]) -> str:
    path = tmp_path / "saved.json"
    reason = refusal(lambda: settings.save(UserSettings(other=entries), path))
    assert not path.exists(), "an invalid settings file was written"
    return reason


@pytest.mark.parametrize(("key", "value", "reason"), INVALID, ids=[i[0] for i in INVALID])
def test_each_invalid_entry_names_its_own_reason(
    tmp_path: Path, key: str, value: object, reason: str
) -> None:
    assert loaded_reason(tmp_path, {key: value}).endswith(f": {reason}.")
    assert saved_reason(tmp_path, {key: value}).endswith(f": {reason}.")


@pytest.mark.parametrize("later", range(1, len(INVALID)))
def test_the_earlier_check_is_the_reason_given(tmp_path: Path, later: int) -> None:
    """With two invalid entries, the one checked first is reported, on load and on save."""
    first, second = INVALID[later - 1], INVALID[later]
    entries = {second[0]: second[1], first[0]: first[1]}  # file order must not matter
    assert loaded_reason(tmp_path, entries).endswith(f": {first[2]}.")
    assert saved_reason(tmp_path, entries).endswith(f": {first[2]}.")


def test_setting_none_removes_the_entry_and_keeps_the_rest() -> None:
    start = UserSettings(other={"build_jobs": 4, "colour_scheme": "dark", "other_key": 1})
    cleared = start.with_build_jobs(None)
    assert cleared.other == {"colour_scheme": "dark", "other_key": 1}
    assert cleared.with_colour_scheme("light").other == {"colour_scheme": "light", "other_key": 1}
    assert start.other == {"build_jobs": 4, "colour_scheme": "dark", "other_key": 1}  # unchanged


def test_setters_check_their_value() -> None:
    try:
        UserSettings().with_show_tool_commands("yes")  # type: ignore[arg-type]
        refused = ""
    except ValueError as exc:
        refused = str(exc)
    assert "show_tool_commands" in refused, "an invalid flag was accepted"
    library = UserSettings().with_auto_add_library(Path("C:/lib"))
    assert library.other == {"auto_add_library": str(Path("C:/lib"))}
    assert isinstance(library.other["auto_add_library"], str)
