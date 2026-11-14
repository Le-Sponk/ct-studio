"""P5-T07c1: validated custom-tool records in the user's machine settings (no UI/launch)."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import NoReturn, cast

import pytest

from ctstudio.core.project.settings import SettingsError, UserSettings, load, save
from ctstudio.core.tools.spec import CustomTool

pytestmark = pytest.mark.timeout(30)

FIELDS = {"name": "Editor", "exe": "tools/edit.exe", "args_template": ["{file}"]}


def _file(tmp_path: Path) -> Path:
    return tmp_path / "config é" / "settings.json"


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


def _pure_outcome(value: UserSettings, tool_id: str, tool: CustomTool | None) -> object:
    try:
        return value.with_custom_tool(tool_id, tool)
    except Exception as exc:
        return exc


def _projection_outcome(value: UserSettings) -> object:
    try:
        return value.custom_tools()
    except Exception as exc:
        return exc


def _with(**changes: object) -> dict[str, object]:
    return {**FIELDS, **changes}


def _without(name: str) -> dict[str, object]:
    return {key: value for key, value in FIELDS.items() if key != name}


DAMAGE: list[object] = [
    None,
    [],
    "text",
    {"edit": None},
    {"edit": ["Editor", "x", []]},
    {"edit": _without("name")},
    {"edit": _without("exe")},
    {"edit": _without("args_template")},
    {"edit": _with(name=5)},
    {"edit": _with(exe=None)},
    {"edit": _with(args_template="{file}")},
    {"edit": _with(args_template=["{file}", 3])},
    {"edit": _with(args_template={"0": "{file}"})},
    {"edit": _with(name="  ")},
    {"edit": _with(exe="")},
    {"edit": _with(exe="   ")},
    {"edit": _with(exe=".")},
    *({"edit": _with(args_template=["ok", bad])} for bad in ("{other}", "{file[0]}")),
    *({"edit": _with(args_template=[bad])} for bad in ("{file!r}", "{file:>5}", "{}")),
    *({"edit": _with(args_template=[bad])} for bad in ("{file", "file}", "{{file}")),
    {"edit": _with(name="Ed\0")},
    {"edit": _with(exe="ed\0.exe")},
    {"edit": _with(args_template=["{file}\0"])},
    {"edit": _with(name="Ed\ud800")},
    {"edit": _with(exe="ed\udfff.exe")},
    {"edit": _with(args_template=["\ud800"])},
    *({bad: dict(FIELDS)} for bad in ("Edit", "1x", "-x", "", "a b", "é", "x\n", "x\0")),
    {"x\ud800": dict(FIELDS)},
]


@pytest.mark.parametrize("table", DAMAGE)
def test_damaged_custom_tools_are_refused_on_load(table: object, tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"format": 1, "custom_tools": table}), encoding="utf-8")
    (path.parent / "settings.json.old.bak").write_bytes(b"older bytes\r\n")
    before = _snapshot(path.parent)
    outcome = _load_outcome(path)
    assert isinstance(outcome, SettingsError), f"not refused: {outcome!r}"
    assert outcome.path == path and "custom tools are invalid" in str(outcome)
    assert _snapshot(path.parent) == before


@pytest.mark.parametrize("table", DAMAGE)
def test_damaged_custom_tools_are_refused_by_save_and_pure_apis(
    table: object, tmp_path: Path
) -> None:
    damaged = UserSettings({"wszst": "/w"}, {"theme": "dark", "custom_tools": table})
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"format": 1}\r\n')
    (path.parent / "settings.json.old.bak").write_bytes(b"older bytes")
    before = _snapshot(path.parent)
    refused = _save_outcome(damaged, path)
    assert isinstance(refused, SettingsError) and refused.path == path
    assert "custom tools are invalid" in str(refused) and refused.details
    assert _snapshot(path.parent) == before
    missing = tmp_path / "new folder" / "settings.json"
    assert isinstance(_save_outcome(damaged, missing), SettingsError)
    assert not missing.parent.exists()
    tool = CustomTool("Other", Path("o.exe"), ["{dir}"])
    for outcome in (
        _projection_outcome(damaged),
        _pure_outcome(damaged, "absent", None),
        _pure_outcome(damaged, "other", tool),
    ):
        assert isinstance(outcome, ValueError), f"not refused: {outcome!r}"


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
    outcome = _save_outcome(UserSettings(other={"custom_tools": table}), target)
    assert isinstance(outcome, SettingsError), f"not refused before replacement: {outcome!r}"
    assert entered == [] and not target.parent.exists()


@pytest.mark.parametrize("tool_id", ["Edit", "1x", "_x", "", "a b", "é", "x\n", "x\0", "x\ud800"])
def test_invalid_ids_are_refused_without_normalization(tool_id: str) -> None:
    start = UserSettings(other={"custom_tools": {"edit": dict(FIELDS)}})
    for value in (CustomTool("Other", Path("o.exe"), []), None):
        outcome = _pure_outcome(start, tool_id, value)
        assert isinstance(outcome, ValueError) and "custom tool id" in str(outcome)
    assert start.custom_tools() == {
        "edit": CustomTool("Editor", Path("tools/edit.exe"), ["{file}"])
    }


@pytest.mark.parametrize(
    "tool",
    [
        CustomTool("Ed\0", Path("e.exe"), []),
        CustomTool("Ed", Path("e\ud800.exe"), []),
        CustomTool("Ed", Path("e.exe"), ["{file}", "a\0"]),
        CustomTool("Ed", Path("e.exe"), ["\udc80"]),
        CustomTool("Ed", Path("   "), []),
    ],
)
def test_unstorable_tools_are_refused(tool: CustomTool) -> None:
    start = UserSettings(other={"custom_tools": {}})
    outcome = _pure_outcome(start, "edit", tool)
    assert isinstance(outcome, ValueError), f"not refused: {outcome!r}"
    assert start.other == {"custom_tools": {}}


def test_records_round_trip_with_extras_and_exact_backup(tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    blender: dict[str, object] = {"name": "My Blender", "exe": "/opt/b", "args_template": []}
    original: dict[str, object] = {
        "format": 1,
        "future": {"keep": [1, 2]},
        "editor_preferences": {".blend": "blender", "later": "x"},
        "auto_add_library": "C:/auto é",
        "custom_tools": {
            "edit": {"note": "kept", **FIELDS, "later": {"deep": [1]}},
            "blender": blender,
        },
        "tools": {"wszst": "/w", "later_tool": "/l"},
    }
    raw = (json.dumps(original, indent=2) + "\r\n").encode("utf-8")
    path.write_bytes(raw)
    loaded = load(path)
    assert loaded.custom_tools() == {
        "edit": CustomTool("Editor", Path("tools/edit.exe"), ("{file}",)),
        "blender": CustomTool("My Blender", Path("/opt/b"), ()),
    }
    args = ["--open", "{file}", "{{literal}}", "", "a b é 工具 {dir}", "{project}"]
    tool = CustomTool("Édit 工具", Path("C:/Tools é/ed.exe"), args)
    updated = loaded.with_custom_tool("edit", tool)
    args.append("{other}")
    save(updated, path)
    [backup] = path.parent.glob("settings.json.*.bak")
    assert backup.read_bytes() == raw
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["custom_tools"]["edit"] == {
        "note": "kept",
        "name": "Édit 工具",
        "exe": str(Path("C:/Tools é/ed.exe")),
        "args_template": args[:-1],
        "later": {"deep": [1]},
    }
    assert list(data["custom_tools"]["edit"]) == ["note", "name", "exe", "args_template", "later"]
    assert data["custom_tools"]["blender"] == blender
    for key in ("future", "editor_preferences", "auto_add_library", "tools"):
        assert data[key] == original[key]
    reloaded = load(path)
    assert reloaded.custom_tools()["edit"] == tool
    assert reloaded.editor_order(".blend") == ("blender",)
    assert reloaded.custom_tools()["edit"].argv(
        file=Path("文件 é"), dir=Path("目录"), project=Path("工程")
    ) == (str(tool.exe), "--open", "文件 é", "{literal}", "", "a b é 工具 目录", "工程")


def test_updates_copy_values_and_removal_is_idempotent() -> None:
    record = {"extra": [1], **FIELDS}
    other: dict[str, object] = {
        "theme": "dark",
        "custom_tools": {"edit": record, "z": dict(FIELDS)},
    }
    start = UserSettings({"blender": "/b"}, other)
    snapshot = copy.deepcopy(other)
    added = start.with_custom_tool("new-tool_2", CustomTool("New", Path("n"), ["{dir}"]))
    projection = added.custom_tools()
    projection.clear()
    record["args_template"] = ["changed"]
    assert added.custom_tools()["new-tool_2"] == CustomTool("New", Path("n"), ("{dir}",))
    assert added.custom_tools()["edit"].args_template == ("{file}",)
    removed = added.with_custom_tool("edit", None)
    assert list(removed.custom_tools()) == ["z", "new-tool_2"]
    assert removed.tools == {"blender": "/b"} and removed.other["theme"] == "dark"
    assert removed.with_custom_tool("edit", None) == removed
    record["args_template"] = ["{file}"]
    assert start.other == snapshot
    empty = UserSettings(other={"theme": "dark"})
    assert empty.with_custom_tool("absent", None) == empty
    assert empty.custom_tools() == {}


@pytest.mark.parametrize("field", ["file", "dir", "project"])
def test_existing_empty_format_specs_are_plain_substitutions(field: str) -> None:
    token = "{" + field + ":}"
    value = UserSettings(other={"custom_tools": {"edit": _with(args_template=[token])}})
    outcome = _projection_outcome(value)
    assert isinstance(outcome, dict), f"existing safe spelling was refused: {outcome!r}"
    tool = cast("dict[str, CustomTool]", outcome)["edit"]
    assert tool.args_template == (token,)
    paths = {"file": "文件 é", "dir": "目录", "project": "工程"}
    assert tool.argv(
        file=Path(paths["file"]), dir=Path(paths["dir"]), project=Path(paths["project"])
    ) == (str(Path("tools/edit.exe")), paths[field])


TOUCHED: list[str] = []


def _forbidden(*args: object, **kwargs: object) -> NoReturn:
    TOUCHED.append(repr(args))
    raise OSError("filesystem access is not allowed here")


def test_pure_apis_do_not_touch_the_filesystem(monkeypatch: pytest.MonkeyPatch) -> None:
    start = UserSettings(other={"custom_tools": {"edit": dict(FIELDS)}})
    TOUCHED.clear()
    with monkeypatch.context() as patch:
        for name in ("stat", "exists", "is_file", "resolve", "absolute"):
            patch.setattr(Path, name, _forbidden)
        patch.setattr(os, "stat", _forbidden)
        try:
            changed = start.with_custom_tool("edit", CustomTool("E", Path("missing/e.exe"), []))
            outcome: object = (changed.custom_tools(), changed.with_custom_tool("edit", None))
        except Exception as exc:
            outcome = exc
    assert TOUCHED == []
    assert isinstance(outcome, tuple), f"pure APIs failed: {outcome!r}"
    projection, removed = outcome
    assert projection == {"edit": CustomTool("E", Path("missing/e.exe"), ())}
    assert isinstance(removed, UserSettings) and removed.custom_tools() == {}
