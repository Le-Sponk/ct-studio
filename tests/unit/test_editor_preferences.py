"""P5-T07a: pure built-ins and safe machine-level editor preferences."""

from __future__ import annotations

import json
from collections.abc import Callable, MutableMapping
from copy import deepcopy
from operator import setitem
from pathlib import Path
from typing import cast

import pytest

from ctstudio.core.project import settings
from ctstudio.core.project.editor_preferences import DEFAULT_EDITORS
from ctstudio.core.project.settings import SettingsError, UserSettings, load, save

pytestmark = pytest.mark.timeout(30)


def _outcome[T](action: Callable[[], T]) -> T | Exception:
    try:
        return action()
    except Exception as exc:
        return exc


def test_exact_immutable_catalogue() -> None:
    assert dict(DEFAULT_EDITORS) == {
        ".brres": ("brawlcrate", "riistudio"),
        ".szs": ("brawlcrate", "riistudio"),
        ".kmp": ("kmp_editor_lorenzi", "kmp_cloud"),
        ".blend": ("blender",),
        "folder": ("system",),
    }
    assert isinstance(DEFAULT_EDITORS[".brres"], tuple)

    mutable = cast("MutableMapping[str, tuple[str, ...]]", DEFAULT_EDITORS)
    assert isinstance(_outcome(lambda: setitem(mutable, ".brres", ("blender",))), TypeError)


@pytest.mark.parametrize(
    "kind", [".brres", ".szs", ".kmp", ".blend", "folder", ".unknown", ".BRRES"]
)
def test_default_projection(kind: str) -> None:
    assert _outcome(lambda: UserSettings().editor_order(kind)) == DEFAULT_EDITORS.get(kind, ())


def test_override_reset_and_nonmutation() -> None:
    other: dict[str, object] = {
        "theme": ["é"],
        "editor_preferences": {".kmp": "kmp_cloud", ".future": {"schema": [None, 3]}},
    }
    tools = {"later": "未 installed"}
    before = deepcopy(other)
    original = UserSettings(tools, other)
    chosen = original.with_editor(".brres", "riistudio")
    assert chosen is not original
    assert chosen.editor_order(".brres") == ("riistudio", "brawlcrate")
    assert chosen.editor_order(".kmp") == ("kmp_cloud", "kmp_editor_lorenzi")
    assert chosen.with_editor("folder", "system").editor_order("folder") == ("system",)
    reset = chosen.with_editor(".brres", None)
    assert reset.other == before and reset.tools == tools
    assert original.other == before and other == before and original.tools == tools
    assert reset.editor_order(".brres") == ("brawlcrate", "riistudio")
    assert reset.with_editor(".brres", None) == reset
    assert chosen.with_editor(".brres", "brawlcrate").editor_order(".brres") == (
        "brawlcrate",
        "riistudio",
    )


@pytest.mark.parametrize(
    "kind, tool",
    [
        (".unknown", "blender"),
        (".BRRES", None),
        ("folder", "blender"),
        (".brres", "Riistudio"),
        (".kmp", "riistudio"),
        (".blend", " blender"),
    ],
)
def test_invalid_updates_are_value_errors(kind: str, tool: str | None) -> None:
    result = _outcome(lambda: UserSettings().with_editor(kind, tool))
    assert isinstance(result, ValueError)
    assert kind in str(result)


BAD_PREFERENCES: list[object] = [
    None,
    [],
    "riistudio",
    {".brres": None},
    {".brres": []},
    {".brres": 1},
    {".brres": ""},
    {".brres": "Riistudio"},
    {".brres": "riistudio "},
    {".kmp": "blender"},
    {"folder": "riistudio"},
    {".blend": "system"},
]


@pytest.mark.parametrize("value", BAD_PREFERENCES)
def test_direct_projection_refuses_malformed_known_preferences(value: object) -> None:
    subject = UserSettings(other={"editor_preferences": value})
    assert isinstance(_outcome(lambda: subject.editor_order(".brres")), ValueError)
    assert isinstance(_outcome(lambda: subject.with_editor(".brres", None)), ValueError)


@pytest.mark.parametrize("value", BAD_PREFERENCES)
@pytest.mark.parametrize("operation", ["load", "save"])
def test_invalid_persistence_leaves_file_and_backups_untouched(
    value: object, operation: str, tmp_path: Path
) -> None:
    path = tmp_path / "settings é.json"
    saved = {"editor_preferences": value} if operation == "load" else {"theme": "user é"}
    raw = json.dumps(saved, ensure_ascii=False).encode("utf-8")
    path.write_bytes(raw)
    backup = tmp_path / "settings é.json.previous.bak"
    backup.write_bytes(b"previous user bytes")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    subject = UserSettings(other={"editor_preferences": value})
    result = _outcome(lambda: load(path) if operation == "load" else save(subject, path))
    assert isinstance(result, SettingsError)
    assert result.path == path and result.details
    assert "editor" in str(result).lower() and "Next:" in str(result)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_unicode_roundtrip_backups_and_future_fields(tmp_path: Path) -> None:
    path = tmp_path / "config é" / "settings.json"
    prefs: dict[str, object] = {
        ".brres": "riistudio",
        ".kmp": "kmp_cloud",
        ".blend": "blender",
        ".szs": "brawlcrate",
        "folder": "system",
        ".future": [None, {"新": True}],
        "schema": None,
    }
    original = UserSettings({"later": "工具 é"}, {"theme": {"新": 1}, "editor_preferences": prefs})
    save(original, path)
    previous = path.read_bytes()
    assert b"\\u" not in previous
    loaded = load(path)
    assert loaded == original
    assert loaded.editor_order(".brres") == ("riistudio", "brawlcrate")
    changed = loaded.with_tool("blender", tmp_path / "not installed é").with_editor(".brres", None)
    save(changed, path)
    [backup] = path.parent.glob("*.bak")
    assert backup.read_bytes() == previous
    assert load(path) == changed and changed.tools["later"] == "工具 é"
    assert changed.other == {
        "theme": {"新": 1},
        "editor_preferences": {key: value for key, value in prefs.items() if key != ".brres"},
    }
    assert original.other["editor_preferences"] == prefs and ".brres" in prefs


def test_empty_reset_and_pure_projection_do_not_touch_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("editor projection must not inspect the filesystem")

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "stat", forbidden)
        scoped.setattr(settings, "default_path", forbidden)
        cleared = _outcome(lambda: UserSettings().with_editor(".brres", None))
        order = _outcome(
            lambda: UserSettings().with_editor(".szs", "riistudio").editor_order(".szs")
        )
    assert cleared == UserSettings()
    assert order == ("riistudio", "brawlcrate")
