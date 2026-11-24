"""P5-T08d: the colour scheme chosen on this computer (``colour_scheme``).

A machine setting in ``settings.json``: absent means CT Studio follows the system's colour
scheme, otherwise ``"light"`` or ``"dark"``. Anything else makes the file damaged: it is
refused by load and by save and never overwritten.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from ctstudio.core.project.settings import (
    COLOUR_SCHEME,
    COLOUR_SCHEMES,
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


def test_the_schemes_on_offer() -> None:
    assert COLOUR_SCHEME == "colour_scheme"
    assert COLOUR_SCHEMES == ("light", "dark")


def test_no_choice_means_follow_the_system() -> None:
    assert UserSettings().colour_scheme() is None
    assert UserSettings(other={"future": 1}).colour_scheme() is None


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_chosen_scheme_is_saved_read_back_and_cleared(tmp_path: Path, scheme: str) -> None:
    path = _file(tmp_path)
    save(UserSettings(other={"future": [1]}).with_colour_scheme(scheme), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[COLOUR_SCHEME] == scheme
    assert data["future"] == [1], "a key this version does not know was lost"
    assert load(path).colour_scheme() == scheme
    save(load(path).with_colour_scheme(None), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert COLOUR_SCHEME not in data, "following the system again left the key behind"
    assert load(path).colour_scheme() is None
    assert data["future"] == [1]


def test_with_colour_scheme_keeps_everything_else() -> None:
    before = UserSettings(tools={"wszst": "C:/w.exe"}, other={"build_jobs": 3})
    after = before.with_colour_scheme("dark")
    assert after.tools == before.tools
    assert after.other == {"build_jobs": 3, COLOUR_SCHEME: "dark"}
    assert before.colour_scheme() is None, "the original settings changed"


BAD = ["Dark", "system", "", 1, True, None, ["dark"], {"scheme": "dark"}]


@pytest.mark.parametrize("value", BAD, ids=repr)
def test_any_other_value_makes_the_file_damaged(tmp_path: Path, value: object) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    text = json.dumps({"format": 1, COLOUR_SCHEME: value}) + "\n"
    path.write_text(text, encoding="utf-8")
    error = outcome(lambda: load(path))
    assert isinstance(error, SettingsError), f"{value!r} was accepted: {error!r}"
    assert f'"{COLOUR_SCHEME}" is not "light" or "dark"' in str(error)
    assert error.path == path
    assert path.read_text(encoding="utf-8") == text, "loading changed the file"


@pytest.mark.parametrize("value", BAD, ids=repr)
def test_a_bad_value_is_never_saved(tmp_path: Path, value: object) -> None:
    path = _file(tmp_path)
    save(UserSettings(), path)
    before = path.read_bytes()
    error = outcome(lambda: save(UserSettings(other={COLOUR_SCHEME: value}), path))
    assert isinstance(error, SettingsError), f"{value!r} was saved"
    assert path.read_bytes() == before, "a refused save changed the file"
    assert not list(path.parent.glob("*.bak*")), "a refused save made a backup"


@pytest.mark.parametrize("value", [bad for bad in BAD if bad is not None], ids=repr)
def test_with_colour_scheme_refuses_a_bad_value(value: object) -> None:
    error = outcome(lambda: UserSettings().with_colour_scheme(cast("str", value)))
    assert isinstance(error, ValueError), f"{value!r} was taken: {error!r}"


def test_reading_a_bad_value_through_the_object_raises() -> None:
    error = outcome(lambda: UserSettings(other={COLOUR_SCHEME: "blue"}).colour_scheme())
    assert isinstance(error, ValueError), f"a bad value was read: {error!r}"
