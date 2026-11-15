"""Fresh saved choices select one existing dispatch owner."""

import json
from pathlib import Path

from pytest import MonkeyPatch
from saved_editor_helpers import forbidden

from ctstudio.core.tools import custom_editors, editors
from ctstudio.core.tools.saved_editors import EditorChoice, open_saved
from ctstudio.core.tools.spec import CustomTool


def test_builtin_routes_fresh_settings(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    path = tmp_path / "settings.json"
    document = tmp_path / "日本.brres"
    project = tmp_path / "project"
    receipt = editors.Launched("brawlcrate", 37, document, ("owner warning",))
    calls: list[tuple[str, Path, Path | None, Path | None, Path | None]] = []

    def owner(
        tool_id: str,
        document: Path,
        *,
        executable: Path | None = None,
        wine_prefix: Path | None = None,
        wine_executable: Path | None = None,
    ) -> editors.Launched:
        calls.append((tool_id, document, executable, wine_prefix, wine_executable))
        return receipt

    monkeypatch.setattr(editors, "open_in", owner)
    for index in (1, 2):
        path.write_text(
            json.dumps(
                {
                    "tools": {"brawlcrate": f"editor{index}", "wine": f"wine{index}"},
                    "wine_prefixes": {"brawlcrate": {"prefix": f"prefix{index}"}},
                    "editor_preferences": {".brres": "riistudio"},
                    "custom_tools": {
                        "brawlcrate": {"name": "shadow", "exe": "wrong", "args_template": []}
                    },
                }
            ),
            encoding="utf-8",
        )
        before = path.read_bytes()
        result = open_saved(
            EditorChoice("builtin", "brawlcrate"), document, project=project, settings_path=path
        )
        assert result is receipt
        assert result.warnings is receipt.warnings
        assert path.read_bytes() == before
    assert calls == [
        ("brawlcrate", document, Path(f"editor{i}"), Path(f"prefix{i}"), Path(f"wine{i}"))
        for i in (1, 2)
    ]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]


def test_custom_collision_routes_fresh_record_only(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    path = tmp_path / "settings.json"
    document, project = tmp_path / "日本.brres", tmp_path / "separate project"
    receipt = editors.Launched("brawlcrate", 38, document, ("opaque warning",))
    calls: list[tuple[str, CustomTool, Path, Path, Path | None, Path | None]] = []

    def owner(
        tool_id: str,
        tool: CustomTool,
        document: Path,
        *,
        project: Path,
        wine_prefix: Path | None = None,
        wine_executable: Path | None = None,
    ) -> editors.Launched:
        calls.append((tool_id, tool, document, project, wine_prefix, wine_executable))
        return receipt

    monkeypatch.setattr(custom_editors, "open_custom", owner)
    monkeypatch.setattr(editors, "open_in", forbidden)
    for i in (1, 2):
        path.write_text(
            json.dumps(
                {
                    "tools": {"brawlcrate": "builtin", "wine": f"wine{i}"},
                    "custom_tools": {
                        "brawlcrate": {
                            "name": f"Custom {i}",
                            "exe": f"custom{i}",
                            "args_template": ["{project}", f"literal{i}", "{file}"],
                        }
                    },
                    "wine_prefixes": {"brawlcrate": {"prefix": f"prefix{i}"}},
                }
            ),
            encoding="utf-8",
        )
        before = path.read_bytes()
        assert (
            open_saved(
                EditorChoice("custom", "brawlcrate"), document, project=project, settings_path=path
            )
            is receipt
        )
        assert path.read_bytes() == before
    assert calls == [
        (
            "brawlcrate",
            CustomTool(f"Custom {i}", Path(f"custom{i}"), ("{project}", f"literal{i}", "{file}")),
            document,
            project,
            Path(f"prefix{i}"),
            Path(f"wine{i}"),
        )
        for i in (1, 2)
    ]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]
