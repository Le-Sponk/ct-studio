"""Loader and owner contracts remain visible through explicit saved choices."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Literal, cast

import pytest
from pytest import MonkeyPatch
from saved_editor_helpers import choice, forbidden, outcome, write_settings

from ctstudio.core.errors import ToolNotFound
from ctstudio.core.project import settings
from ctstudio.core.tools import custom_editors, editors
from ctstudio.core.tools.saved_editors import EditorChoice, open_saved


@pytest.mark.parametrize("namespace", ["builtin", "custom"])
@pytest.mark.parametrize(
    "damage",
    [
        b"{",
        b"\xff",
        b"[]",
        b'{"format":999}',
        b'{"tools":[]}',
        b'{"tools":{"wine":false}}',
        b'{"custom_tools":[]}',
        b'{"custom_tools":{"x":{"name":"x","exe":"x","args_template":["{bad}"]}}}',
        b'{"wine_prefixes":{"x":{"prefix":""}}}',
        b'{"editor_preferences":{".brres":"unknown"}}',
    ],
)
def test_corruption_after_success_refuses_without_writes(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    namespace: Literal["builtin", "custom"],
    damage: bytes,
) -> None:
    path = tmp_path / "settings.json"
    write_settings(
        path,
        {"custom_tools": {"brawlcrate": {"name": "Custom", "exe": "custom", "args_template": []}}},
    )
    receipt = editors.Launched("brawlcrate", 51, tmp_path / "日本.brres", ())
    calls: list[int] = []

    def owner(*args: object, **kwargs: object) -> editors.Launched:
        calls.append(1)
        return receipt

    monkeypatch.setattr(editors, "open_in", owner)
    monkeypatch.setattr(custom_editors, "open_custom", owner)
    assert outcome(choice(namespace), path) is receipt
    path.write_bytes(damage)
    error = outcome(choice(namespace), path)
    assert isinstance(error, settings.SettingsError)
    assert calls == [1]
    assert path.read_bytes() == damage
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]


@pytest.mark.parametrize("namespace", ["builtin", "custom"])
@pytest.mark.parametrize("boundary", ["loader", "owner"])
@pytest.mark.parametrize("kind", ["editor", "tool", "os", "runtime", "interrupt", "exit"])
def test_error_cause_and_interrupt_identity(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    namespace: Literal["builtin", "custom"],
    boundary: str,
    kind: str,
) -> None:
    path = tmp_path / "settings.json"
    before = write_settings(
        path,
        {"custom_tools": {"brawlcrate": {"name": "Custom", "exe": "custom", "args_template": []}}},
    )
    errors: dict[str, BaseException] = {
        "editor": editors.EditorError("brawlcrate", path, "owner refusal"),
        "tool": ToolNotFound("editor", hint="Choose another editor."),
        "os": PermissionError("owner denied"),
        "runtime": RuntimeError("owner failed"),
        "interrupt": KeyboardInterrupt(),
        "exit": SystemExit(23),
    }
    error = errors[kind]
    cause = ValueError("original cause")
    error.__cause__ = cause

    def fail(*args: object, **kwargs: object) -> editors.Launched:
        raise error

    if boundary == "loader":
        monkeypatch.setattr(settings, "load", fail)
        monkeypatch.setattr(editors, "open_in", forbidden)
        monkeypatch.setattr(custom_editors, "open_custom", forbidden)
    else:
        owner = editors if namespace == "builtin" else custom_editors
        monkeypatch.setattr(owner, "open_in" if namespace == "builtin" else "open_custom", fail)
    assert outcome(choice(namespace), path) is error
    assert error.__cause__ is cause
    assert path.read_bytes() == before


def test_default_path_resolved_for_each_request(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    paths = [tmp_path / f"settings{i}.json" for i in (1, 2)]
    originals = [
        write_settings(p, {"tools": {"brawlcrate": f"editor{i}"}}) for i, p in enumerate(paths, 1)
    ]
    destinations = iter(paths)
    default_calls: list[int] = []
    executables: list[object] = []
    receipt = editors.Launched("brawlcrate", 52, tmp_path / "doc", ())

    def default_path() -> Path:
        default_calls.append(1)
        return next(destinations)

    def owner(*args: object, **kwargs: object) -> editors.Launched:
        executables.append(kwargs["executable"])
        return receipt

    monkeypatch.setattr(settings, "default_path", default_path)
    monkeypatch.setattr(editors, "open_in", owner)
    for _ in paths:
        assert open_saved(choice("builtin"), tmp_path / "doc", project=tmp_path) is receipt
    assert default_calls == [1, 1]
    assert executables == [Path("editor1"), Path("editor2")]
    assert [p.read_bytes() for p in paths] == originals


def test_choice_is_immutable_and_has_no_implicit_selection() -> None:
    selected = EditorChoice("custom", "brawlcrate")
    error: Exception | None = None
    try:
        selected.__setattr__("namespace", "builtin")
    except Exception as exc:
        error = exc
    assert isinstance(error, FrozenInstanceError)
    assert selected == EditorChoice("custom", "brawlcrate")
    assert selected != EditorChoice("builtin", "brawlcrate")
    with pytest.raises(TypeError):
        cast("Callable[..., EditorChoice]", EditorChoice)()


@pytest.mark.parametrize("namespace", ["builtin", "custom"])
@pytest.mark.parametrize("tool_id", ["unknown", "BrawlCrate", "brawlcrate ", ""])
def test_unknown_exact_id_never_selects_preference(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    namespace: Literal["builtin", "custom"],
    tool_id: str,
) -> None:
    path = tmp_path / "settings.json"
    before = write_settings(path, {"editor_preferences": {".brres": "riistudio"}})
    monkeypatch.setattr(editors, "discover", forbidden)
    monkeypatch.setattr(editors, "launch_detached", forbidden)
    monkeypatch.setattr(custom_editors, "open_custom", forbidden)
    error = outcome(EditorChoice(namespace, tool_id), path)
    assert isinstance(error, editors.EditorError)
    assert error.tool_id == tool_id
    assert path.read_bytes() == before


def test_missing_settings_custom_is_actionable_without_creating_file(tmp_path: Path) -> None:
    path = tmp_path / "absent.json"
    error = outcome(choice(), path)
    assert isinstance(error, editors.EditorError)
    assert error.hint and "custom" in error.hint
    assert list(tmp_path.iterdir()) == []
