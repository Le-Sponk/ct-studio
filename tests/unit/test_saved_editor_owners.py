"""Representative real owners, with only discovery/process boundaries replaced."""

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import pytest
from pytest import MonkeyPatch
from saved_editor_helpers import forbidden, outcome, write_settings

from ctstudio.core.errors import ToolNotFound
from ctstudio.core.tools import custom_editors, editors, wine
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.saved_editors import EditorChoice, open_saved
from ctstudio.core.tools.spec import ToolSpec


def windows() -> Literal["windows"]:
    return "windows"


def linux() -> Literal["linux"]:
    return "linux"


def inputs(root: Path) -> tuple[Path, Path, Path, Path]:
    document, executable = root / "日本 document.brres", root / "native editor"
    project, path = root / "separate project", root / "settings.json"
    document.write_bytes(b"synthetic document")
    executable.write_bytes(b"synthetic editor; never executed")
    project.mkdir()
    return document, executable, project, path


@pytest.mark.parametrize("tool_id", ["brawlcrate", "riistudio"])
@pytest.mark.parametrize("configured", [True, False])
def test_real_builtin_defaults_options_warnings_and_unused_metadata(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    tool_id: str,
    configured: bool,
) -> None:
    document, executable, project, path = inputs(tmp_path)
    before = write_settings(
        path,
        {
            "tools": {**({tool_id: str(executable)} if configured else {}), "wine": "unused Wine"},
            "wine_prefixes": {tool_id: {"prefix": "unused prefix"}},
            "custom_tools": {tool_id: {"name": "shadow", "exe": "wrong", "args_template": []}},
            "editor_preferences": {".brres": "riistudio"},
        },
    )
    calls: list[tuple[list[str | Path], Path]] = []
    discovery: list[str] = []

    def discover(spec: ToolSpec, *, include_dev: bool = False) -> ToolLocation:
        assert include_dev
        discovery.append(spec.id)
        return ToolLocation(executable.resolve(), None, "path", "direct")

    def launch(argv: Sequence[str | Path], *, cwd: Path) -> int:
        calls.append((list(argv), cwd))
        return 61

    monkeypatch.setattr(editors, "current_os", windows)
    monkeypatch.setattr(editors, "discover", discover)
    monkeypatch.setattr(editors, "launch_detached", launch)
    monkeypatch.setattr(custom_editors, "open_custom", forbidden)
    monkeypatch.setattr(wine, "launch", forbidden)
    receipt = open_saved(
        EditorChoice("builtin", tool_id), document, project=project, settings_path=path
    )
    options = ["/audio:none"] if tool_id == "brawlcrate" else []
    assert calls == [([executable.resolve(), document.resolve(), *options], document.parent)]
    assert discovery == ([] if configured else [tool_id])
    assert receipt.pid == 61 and receipt.tool_id == tool_id
    assert receipt.document == document.resolve()
    assert bool(receipt.warnings) == (tool_id == "riistudio")
    if receipt.warnings:
        assert "empty editor" in receipt.warnings[0]
    assert path.read_bytes() == before
    assert document.read_bytes() == b"synthetic document"


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_real_custom_literal_argv_ignores_valid_unused_wine_metadata(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    platform: str,
) -> None:
    document, executable, project, path = inputs(tmp_path)
    args = ["--literal", "a b; &|$()", "", "{{braces}}", "{project}", "{file}", "{dir}"]
    before = write_settings(
        path,
        {
            "tools": {"wine": "unused Wine", "brawlcrate": "unused builtin"},
            "wine_prefixes": {"brawlcrate": {"prefix": "unused prefix"}},
            "custom_tools": {
                "brawlcrate": {"name": "Custom", "exe": str(executable), "args_template": args}
            },
        },
    )
    calls: list[tuple[list[str | Path], Path]] = []

    def launch(argv: Sequence[str | Path], *, cwd: Path) -> int:
        calls.append((list(argv), cwd))
        return 62

    monkeypatch.setattr(custom_editors, "current_os", windows if platform == "windows" else linux)
    monkeypatch.setattr(custom_editors, "launch_detached", launch)
    monkeypatch.setattr(editors, "open_in", forbidden)
    monkeypatch.setattr(wine, "validate_runtime", forbidden)
    receipt = open_saved(
        EditorChoice("custom", "brawlcrate"), document, project=project, settings_path=path
    )
    assert calls == [
        (
            [
                str(executable.resolve()),
                "--literal",
                "a b; &|$()",
                "",
                "{braces}",
                str(project.resolve()),
                str(document.resolve()),
                str(document.parent),
            ],
            document.parent,
        )
    ]
    assert receipt == editors.Launched("brawlcrate", 62, document.resolve(), ())
    assert path.read_bytes() == before
    assert document.read_bytes() == b"synthetic document"


@pytest.mark.parametrize("namespace", ["builtin", "custom"])
def test_removed_configured_executable_never_discovers_fallback(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    namespace: Literal["builtin", "custom"],
) -> None:
    document, executable, project, path = inputs(tmp_path)
    before = write_settings(
        path,
        {
            "tools": {"brawlcrate": str(executable)},
            "custom_tools": {
                "brawlcrate": {
                    "name": "Custom",
                    "exe": str(executable),
                    "args_template": ["{file}"],
                }
            },
        },
    )
    calls: list[int] = []

    def launch(*args: object, **kwargs: object) -> int:
        calls.append(1)
        return 63

    monkeypatch.setattr(editors, "current_os", windows)
    monkeypatch.setattr(custom_editors, "current_os", windows)
    monkeypatch.setattr(editors, "discover", forbidden)
    monkeypatch.setattr(editors, "launch_detached", launch)
    monkeypatch.setattr(custom_editors, "launch_detached", launch)
    assert (
        open_saved(
            EditorChoice(namespace, "brawlcrate"), document, project=project, settings_path=path
        ).pid
        == 63
    )
    executable.unlink()
    document.rename(tmp_path / "日本.brres")
    error = outcome(EditorChoice(namespace, "brawlcrate"), path)
    assert isinstance(error, ToolNotFound)
    assert calls == [1]
    assert path.read_bytes() == before


def test_real_builtin_wine_route_keeps_owner_options(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    document, executable, project, path = inputs(tmp_path)
    executable = executable.rename(tmp_path / "editor.exe")
    launcher, prefix = tmp_path / "wine", tmp_path / "prefix"
    launcher.write_bytes(b"never executed")
    before = write_settings(
        path,
        {
            "tools": {"brawlcrate": str(executable), "wine": str(launcher)},
            "wine_prefixes": {"brawlcrate": {"prefix": str(prefix)}},
        },
    )
    calls: list[tuple[Path, Path, tuple[str, ...], Path, Path]] = []

    def launch(exe: Path, doc: Path, options: Sequence[str], *, wine: Path, prefix: Path) -> int:
        calls.append((exe, doc, tuple(options), wine, prefix))
        return 64

    monkeypatch.setattr(editors, "current_os", linux)
    monkeypatch.setattr(editors, "discover", forbidden)
    monkeypatch.setattr(editors, "launch_detached", forbidden)
    monkeypatch.setattr(wine, "launch", launch)
    receipt = open_saved(
        EditorChoice("builtin", "brawlcrate"), document, project=project, settings_path=path
    )
    assert calls == [
        (executable.resolve(), document.resolve(), ("/audio:none",), launcher.resolve(), prefix)
    ]
    assert receipt == editors.Launched("brawlcrate", 64, document.resolve(), ())
    assert path.read_bytes() == before


@pytest.mark.parametrize("missing", ["wine", "prefix"])
@pytest.mark.parametrize("namespace", ["builtin", "custom"])
def test_real_wine_owner_refuses_missing_selected_metadata(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    namespace: Literal["builtin", "custom"],
    missing: str,
) -> None:
    document, executable, _, path = inputs(tmp_path)
    document.rename(tmp_path / "日本.brres")
    executable = executable.rename(tmp_path / "editor.exe")
    fields: dict[str, object] = {
        "tools": {"brawlcrate": str(executable), "wine": str(tmp_path / "missing wine")},
        "custom_tools": {
            "brawlcrate": {"name": "Custom", "exe": str(executable), "args_template": ["{file}"]}
        },
    }
    if missing == "wine":
        fields["wine_prefixes"] = {"brawlcrate": {"prefix": str(tmp_path / "prefix")}}
        if namespace == "custom":
            fields["tools"] = {"brawlcrate": str(executable)}
    before = write_settings(path, fields)
    monkeypatch.setattr(editors, "current_os", linux)
    monkeypatch.setattr(custom_editors, "current_os", linux)
    monkeypatch.setattr(editors, "discover", forbidden)
    monkeypatch.setattr(editors, "launch_detached", forbidden)
    monkeypatch.setattr(custom_editors, "launch_detached", forbidden)
    monkeypatch.setattr(wine, "launch", forbidden)
    monkeypatch.setattr(wine, "launch_argv", forbidden)
    error = outcome(EditorChoice(namespace, "brawlcrate"), path)
    assert isinstance(error, (ToolNotFound, wine.WineError))
    assert error.hint
    assert path.read_bytes() == before
