"""No fallback, repair, or launch after a saved-choice refusal."""

from pathlib import Path
from typing import Literal, cast

import pytest
from pytest import MonkeyPatch
from saved_editor_helpers import choice, forbidden, outcome, write_settings

from ctstudio.core.project import settings
from ctstudio.core.tools import custom_editors, editors
from ctstudio.core.tools.saved_editors import EditorChoice


def test_removed_custom_never_falls_back(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    path = tmp_path / "settings.json"
    receipt = editors.Launched("brawlcrate", 42, tmp_path / "日本.brres", ())
    calls: list[str] = []

    def owner(*args: object, **kwargs: object) -> editors.Launched:
        calls.append("custom")
        return receipt

    monkeypatch.setattr(custom_editors, "open_custom", owner)
    monkeypatch.setattr(editors, "open_in", forbidden)
    write_settings(
        path,
        {
            "custom_tools": {
                "brawlcrate": {"name": "Custom", "exe": "custom", "args_template": ["{file}"]}
            }
        },
    )
    assert outcome(choice(), path) is receipt
    before = write_settings(path, {"tools": {"brawlcrate": "builtin"}})
    error = outcome(choice(), path)
    assert isinstance(error, editors.EditorError)
    assert error.tool_id == "brawlcrate"
    assert error.hint and "custom" in error.hint.lower()
    assert calls == ["custom"]
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]


@pytest.mark.parametrize(
    "namespace", ["Builtin", "CUSTOM", "", " builtin", "builtin ", "future", None, True, 1]
)
def test_invalid_namespace_refuses_before_read(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    namespace: object,
) -> None:
    path = tmp_path / "settings.json"
    before = write_settings(path, {})
    monkeypatch.setattr(settings, "load", forbidden)
    monkeypatch.setattr(editors, "open_in", forbidden)
    monkeypatch.setattr(custom_editors, "open_custom", forbidden)
    selected = EditorChoice(cast('Literal["builtin", "custom"]', namespace), "brawlcrate")
    error = outcome(selected, path)
    assert isinstance(error, editors.EditorError)
    assert error.hint
    assert "namespace" in str(error).lower()
    assert path.read_bytes() == before


@pytest.mark.parametrize("unsafe", ["bad\0path", "bad\ud800path", "bad\udfffpath"])
@pytest.mark.parametrize("key", ["brawlcrate"])
def test_unsafe_builtin_configured_text_refuses_with_cause(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    unsafe: str,
    key: str,
) -> None:
    path = tmp_path / "settings.json"
    before = write_settings(path, {"tools": {key: unsafe}})
    monkeypatch.setattr(editors, "open_in", forbidden)
    monkeypatch.setattr(custom_editors, "open_custom", forbidden)
    error = outcome(choice("builtin"), path)
    assert isinstance(error, editors.EditorError)
    assert isinstance(error.__cause__, ValueError)
    assert error.__cause__ is not error
    assert error.hint
    assert path.read_bytes() == before
