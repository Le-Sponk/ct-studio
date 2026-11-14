"""P5-T07c2: per-editor Wine-prefix choices in the user's machine settings (no dispatch/UI)."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import NoReturn

import pytest

from ctstudio.core.project.settings import SettingsError, UserSettings, load, save

pytestmark = pytest.mark.timeout(30)

REASON = "Wine prefixes are invalid"


def _file(tmp_path: Path) -> Path:
    return tmp_path / "config é 目录" / "settings.json"


def _snapshot(folder: Path) -> dict[str, bytes]:
    if not folder.exists():
        return {}
    return {path.name: path.read_bytes() for path in folder.iterdir()}


def _load_outcome(path: Path) -> UserSettings | Exception:
    try:
        return load(path)
    except Exception as exc:  # typed outcome: a missing raise must fail an assertion
        return exc


def _save_outcome(value: UserSettings, path: Path) -> Exception | None:
    try:
        save(value, path)
    except Exception as exc:
        return exc
    return None


def _projection_outcome(value: UserSettings) -> object:
    try:
        return value.wine_prefixes()
    except Exception as exc:
        return exc


def _update_outcome(value: UserSettings, editor_id: str, prefix: Path | None) -> object:
    try:
        return value.with_wine_prefix(editor_id, prefix)
    except Exception as exc:
        return exc


DAMAGE: list[object] = [
    None,
    [],
    "text",
    5,
    True,
    {"blender": None},
    {"blender": "C:/prefix"},
    {"blender": 3},
    {"blender": False},
    {"blender": ["/p"]},
    {"blender": {}},
    {"blender": {"note": "no prefix"}},
    *({"blender": {"prefix": bad}} for bad in (None, 7, True, ["/p"], {"p": 1})),
    *({"blender": {"prefix": bad}} for bad in ("", " ", "\t\n", "/p\0x", "/p\ud800")),
    {"blender": {"prefix": "/ok"}, "brawlcrate": {"prefix": ""}},
    *({bad: {"prefix": "/p"}} for bad in ("Blender", "1x", "-x", "_x", "", "a b", "é")),
    *({bad: {"prefix": "/p"}} for bad in ("x\n", "x\0", "x\ud800", " blender")),
]


@pytest.mark.parametrize("table", DAMAGE)
def test_damaged_wine_prefixes_are_refused_on_load(table: object, tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"format": 1, "wine_prefixes": table}), encoding="utf-8")
    (path.parent / "settings.json.old.bak").write_bytes(b"older bytes\r\n")
    before = _snapshot(path.parent)
    outcome = _load_outcome(path)
    assert isinstance(outcome, SettingsError), f"not refused: {outcome!r}"
    assert outcome.path == path and REASON in str(outcome) and outcome.details
    assert outcome.hint and "will not overwrite" in outcome.hint
    assert _snapshot(path.parent) == before


@pytest.mark.parametrize("table", DAMAGE)
def test_damaged_wine_prefixes_are_refused_by_save(table: object, tmp_path: Path) -> None:
    damaged = UserSettings({"wszst": "/w"}, {"theme": "dark", "wine_prefixes": table})
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"format": 1}\r\n')
    (path.parent / "settings.json.old.bak").write_bytes(b"older bytes")
    before = _snapshot(path.parent)
    refused = _save_outcome(damaged, path)
    assert isinstance(refused, SettingsError), f"not refused: {refused!r}"
    assert refused.path == path and REASON in str(refused) and refused.details
    assert _snapshot(path.parent) == before
    missing = tmp_path / "new folder é" / "settings.json"
    outcome = _save_outcome(damaged, missing)
    assert isinstance(outcome, SettingsError), f"not refused: {outcome!r}"
    assert not missing.parent.exists()


@pytest.mark.parametrize("table", DAMAGE)
def test_refused_save_never_enters_replacement(
    table: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ctstudio.core.project import settings

    entered: list[Path] = []

    def replacement(path: Path, content: bytes) -> NoReturn:
        entered.append(path)
        raise OSError("replacement must not start")

    monkeypatch.setattr(settings, "replace_with_backup", replacement)
    target = tmp_path / "not-created" / "settings.json"
    outcome = _save_outcome(UserSettings(other={"wine_prefixes": table}), target)
    assert isinstance(outcome, SettingsError), f"not refused before replacement: {outcome!r}"
    assert REASON in str(outcome)
    assert entered == [] and not target.parent.exists()


@pytest.mark.parametrize("table", DAMAGE)
def test_damaged_wine_prefixes_refuse_projection_and_updates(table: object) -> None:
    other: dict[str, object] = {"theme": "dark", "wine_prefixes": table}
    damaged = UserSettings({"wszst": "/w"}, other)
    snapshot = copy.deepcopy(other)
    outcomes = [
        _projection_outcome(damaged),
        _update_outcome(damaged, "absent", None),
        _update_outcome(damaged, "blender", None),
        _update_outcome(damaged, "other", Path("/prefix")),
    ]
    for outcome in outcomes:
        assert isinstance(outcome, ValueError), f"damage not refused: {outcome!r}"
        assert "Wine" in str(outcome) or "wine_prefixes" in str(outcome)
    assert damaged.other == snapshot and damaged.tools == {"wszst": "/w"}


BAD_IDS = ["Blender", "1x", "_x", "-x", "", "a b", "é", "x\n", "x\0", "x\ud800", " blender"]


@pytest.mark.parametrize("editor_id", BAD_IDS)
def test_invalid_editor_ids_are_refused_without_normalization(editor_id: str) -> None:
    other: dict[str, object] = {"wine_prefixes": {"blender": {"prefix": "/p"}}}
    start = UserSettings(other=other)
    snapshot = copy.deepcopy(other)
    for prefix in (Path("/q"), None):
        outcome = _update_outcome(start, editor_id, prefix)
        assert isinstance(outcome, ValueError), f"not refused: {outcome!r}"
        assert "Wine-prefix editor id" in str(outcome) and repr(editor_id) in str(outcome)
    assert start.other == snapshot
    assert start.wine_prefixes() == {"blender": Path("/p")}


@pytest.mark.parametrize(
    ("prefix", "text"),
    [
        (Path(" "), "blank"),
        (Path("\t"), "blank"),
        (Path("/p\0x"), "NUL"),
        (Path("/p\ud800"), "Unicode"),
    ],
)
def test_unstorable_prefixes_are_refused(prefix: Path, text: str) -> None:
    other: dict[str, object] = {"wine_prefixes": {"blender": {"prefix": "/p", "x": [1]}}}
    start = UserSettings(other=other)
    snapshot = copy.deepcopy(other)
    outcome = _update_outcome(start, "blender", prefix)
    assert isinstance(outcome, ValueError), f"not refused: {outcome!r}"
    assert text in str(outcome) and "'blender'" in str(outcome)
    assert start.other == snapshot


def test_choices_are_independent_copies_and_reset_is_exact() -> None:
    extension = {"deep": [1]}
    sibling_extension = [2]
    sibling: dict[str, object] = {"prefix": "rel/zz", "later": sibling_extension}
    record: dict[str, object] = {"prefix": "/old", "later": extension}
    other: dict[str, object] = {
        "theme": "dark",
        "editor_preferences": {".szs": "brawlcrate"},
        "custom_tools": {"edit": {"name": "E", "exe": "e.exe", "args_template": []}},
        "wine_prefixes": {"zz": sibling, "brawlcrate": record},
    }
    start = UserSettings({"wine": "/usr/bin/wine"}, other)
    snapshot = copy.deepcopy(other)
    changed = start.with_wine_prefix("brawlcrate", Path("/home/u/前缀 é"))
    added = changed.with_wine_prefix("my-editor_2", Path("relative/目录"))
    extension["deep"].append(9)
    sibling_extension.append(9)
    record["later"] = "mutated after update"
    table = added.other["wine_prefixes"]
    assert table == {
        "zz": {"prefix": "rel/zz", "later": [2]},
        "brawlcrate": {"prefix": str(Path("/home/u/前缀 é")), "later": {"deep": [1]}},
        "my-editor_2": {"prefix": str(Path("relative/目录"))},
    }
    projection = added.wine_prefixes()
    assert list(projection) == ["zz", "brawlcrate", "my-editor_2"]
    projection.clear()
    assert added.wine_prefixes()["zz"] == Path("rel/zz")
    extension["deep"].pop()
    sibling_extension.pop()
    record["later"] = extension
    assert start.other == snapshot and start.tools == {"wine": "/usr/bin/wine"}
    for key in ("theme", "editor_preferences", "custom_tools"):
        assert added.other[key] == other[key]
    assert added.tools == {"wine": "/usr/bin/wine"}
    assert added.editor_order(".szs") == start.editor_order(".szs")
    removed = added.with_wine_prefix("brawlcrate", None)
    assert list(removed.wine_prefixes()) == ["zz", "my-editor_2"]
    assert removed.with_wine_prefix("brawlcrate", None) == removed
    assert added.wine_prefixes()["brawlcrate"] == Path("/home/u/前缀 é")


def test_absent_table_is_not_created_and_native_defaults_are_unchanged() -> None:
    empty = UserSettings({"blender": "/b"}, {"theme": "dark"})
    assert empty.wine_prefixes() == {}
    assert empty.with_wine_prefix("blender", None) == empty
    assert "wine_prefixes" not in empty.with_wine_prefix("blender", None).other
    chosen = empty.with_wine_prefix("blender", Path("."))
    assert chosen.wine_prefixes() == {"blender": Path(".")}
    assert chosen.other["wine_prefixes"] == {"blender": {"prefix": "."}}
    for kind in (".szs", ".blend", ".kmp", ".brres", ".unknown"):
        assert chosen.editor_order(kind) == UserSettings().editor_order(kind)
    assert chosen.tools == {"blender": "/b"} and chosen.configured() == empty.configured()
    emptied = chosen.with_wine_prefix("blender", None)
    assert emptied.other == {"theme": "dark", "wine_prefixes": {}}
    assert UserSettings({"a": "b"}, {"c": 1}) == UserSettings(tools={"a": "b"}, other={"c": 1})


def test_prefixes_round_trip_with_extensions_and_exact_backups(tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    old_backup = path.parent / "settings.json.20260101T000000000000Z.old.bak"
    old_backup.write_bytes(b'{"format": 1}\r\n')
    original: dict[str, object] = {
        "format": 1,
        "future": {"keep": [1, {"x": None}]},
        "editor_preferences": {".szs": "brawlcrate", "later": "x"},
        "custom_tools": {"edit": {"name": "E", "exe": "e.exe", "args_template": ["{file}"]}},
        "wine_prefixes": {
            "brawlcrate": {"note": "kept", "prefix": "/home/u/é", "later": {"deep": [1]}},
            "future-editor": {"prefix": "relative/文件", "arch": "win64"},
        },
        "tools": {"wine": "/usr/bin/wine", "later_tool": "/l"},
    }
    raw = (json.dumps(original, indent=2, ensure_ascii=False) + "\r\n").encode("utf-8")
    path.write_bytes(raw)
    loaded = load(path)
    assert loaded.wine_prefixes() == {
        "brawlcrate": Path("/home/u/é"),
        "future-editor": Path("relative/文件"),
    }
    prefix = Path("C:/Wine 目录 é/prefix")
    updated = loaded.with_wine_prefix("brawlcrate", prefix).with_tool("wszst", Path("/w é"))
    save(updated, path)
    backups = sorted(path.parent.glob("settings.json.*.bak"))
    assert len(backups) == 2 and old_backup in backups
    [new_backup] = [item for item in backups if item != old_backup]
    assert new_backup.read_bytes() == raw and old_backup.read_bytes() == b'{"format": 1}\r\n'
    data = json.loads(path.read_text(encoding="utf-8"))
    record = data["wine_prefixes"]["brawlcrate"]
    assert record == {"note": "kept", "prefix": str(prefix), "later": {"deep": [1]}}
    assert list(record) == ["note", "prefix", "later"]
    assert data["wine_prefixes"]["future-editor"] == {"prefix": "relative/文件", "arch": "win64"}
    for key in ("future", "editor_preferences", "custom_tools"):
        assert data[key] == original[key]
    assert data["tools"] == {
        "wine": "/usr/bin/wine",
        "later_tool": "/l",
        "wszst": str(Path("/w é")),
    }
    reloaded = load(path)
    assert reloaded.wine_prefixes()["brawlcrate"] == prefix
    assert reloaded.editor_order(".szs") == loaded.editor_order(".szs")
    assert reloaded.custom_tools() == loaded.custom_tools()


TOUCHED: list[str] = []


def _forbidden(*args: object, **kwargs: object) -> NoReturn:
    TOUCHED.append(repr(args))
    raise OSError("filesystem access is not allowed here")


def test_pure_apis_do_not_touch_the_filesystem(monkeypatch: pytest.MonkeyPatch) -> None:
    start = UserSettings(other={"wine_prefixes": {"blender": {"prefix": "~/missing é"}}})
    TOUCHED.clear()
    with monkeypatch.context() as patch:
        for name in ("stat", "exists", "is_dir", "is_file", "resolve", "absolute", "expanduser"):
            patch.setattr(Path, name, _forbidden)
        patch.setattr(os, "stat", _forbidden)
        patch.setattr(os, "listdir", _forbidden)
        try:
            changed = start.with_wine_prefix("blender", Path("missing/文件 目录"))
            added = changed.with_wine_prefix("other", Path("."))
            outcome: object = (added.wine_prefixes(), added.with_wine_prefix("blender", None))
        except Exception as exc:
            outcome = exc
    assert TOUCHED == []
    assert isinstance(outcome, tuple), f"pure APIs failed: {outcome!r}"
    projection, removed = outcome
    assert projection == {"blender": Path("missing/文件 目录"), "other": Path(".")}
    assert isinstance(removed, UserSettings)
    assert removed.wine_prefixes() == {"other": Path(".")}
    assert start.wine_prefixes() == {"blender": Path("~/missing é")}
