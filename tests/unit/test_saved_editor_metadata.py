"""Unused Wine paths must not alter native launches; selected Wine still refuses damage."""

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import pytest
from pytest import MonkeyPatch
from saved_editor_helpers import forbidden, write_settings

from ctstudio.core.errors import ToolNotFound
from ctstudio.core.tools import custom_editors, editors, wine
from ctstudio.core.tools.saved_editors import EditorChoice, open_saved


def windows() -> Literal["windows"]:
    return "windows"


def linux() -> Literal["linux"]:
    return "linux"


@pytest.mark.parametrize("unsafe", ["bad\0wine", "bad\ud800wine", "bad\udfffwine"])
@pytest.mark.parametrize("platform", ["windows", "linux"])
@pytest.mark.parametrize("namespace", ["builtin", "custom"])
def test_native_ignores_unsafe_unused_wine(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    unsafe: str,
    platform: str,
    namespace: Literal["builtin", "custom"],
) -> None:
    document, executable = tmp_path / "日本.brres", tmp_path / "native editor"
    project = tmp_path / "separate project"
    document.write_bytes(b"synthetic document")
    executable.write_bytes(b"synthetic executable; never executed")
    project.mkdir()
    path = tmp_path / "settings.json"
    before = write_settings(
        path,
        {
            "tools": {"brawlcrate": str(executable), "wine": unsafe},
            "custom_tools": {
                "brawlcrate": {
                    "name": "Custom",
                    "exe": str(executable),
                    "args_template": ["{file}"],
                }
            },
            "wine_prefixes": {"brawlcrate": {"prefix": "unused missing prefix"}},
        },
    )
    calls: list[tuple[list[str], Path]] = []

    def launch(argv: Sequence[str | Path], *, cwd: Path) -> int:
        calls.append(([str(p) for p in argv], cwd))
        return 71

    os_name = windows if platform == "windows" else linux
    monkeypatch.setattr(editors, "current_os", os_name)
    monkeypatch.setattr(custom_editors, "current_os", os_name)
    monkeypatch.setattr(editors, "discover", forbidden)
    monkeypatch.setattr(editors, "launch_detached", launch)
    monkeypatch.setattr(custom_editors, "launch_detached", launch)
    monkeypatch.setattr(wine, "launch", forbidden)
    monkeypatch.setattr(wine, "launch_argv", forbidden)
    result: editors.Launched | BaseException
    try:
        result = open_saved(
            EditorChoice(namespace, "brawlcrate"), document, project=project, settings_path=path
        )
    except BaseException as exc:
        result = exc
    assert isinstance(result, editors.Launched)
    assert result.pid == 71 and not result.warnings
    options = ["/audio:none"] if namespace == "builtin" else []
    assert calls == [
        ([str(executable.resolve()), str(document.resolve()), *options], document.parent.resolve())
    ]
    assert path.read_bytes() == before
    assert document.read_bytes() == b"synthetic document"


@pytest.mark.parametrize("unsafe", ["bad\0wine", "bad\ud800wine", "bad\udfffwine"])
def test_selected_builtin_wine_refuses_unsafe_executable(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    unsafe: str,
) -> None:
    document, executable = tmp_path / "日本.brres", tmp_path / "editor.exe"
    document.write_bytes(b"synthetic document")
    executable.write_bytes(b"not executed")
    path = tmp_path / "settings.json"
    before = write_settings(
        path,
        {
            "tools": {"brawlcrate": str(executable), "wine": unsafe},
            "wine_prefixes": {"brawlcrate": {"prefix": "prefix"}},
        },
    )
    monkeypatch.setattr(editors, "current_os", linux)
    monkeypatch.setattr(editors, "discover", forbidden)
    monkeypatch.setattr(editors, "launch_detached", forbidden)
    monkeypatch.setattr(wine, "launch", forbidden)
    result: editors.Launched | BaseException
    try:
        result = open_saved(
            EditorChoice("builtin", "brawlcrate"), document, project=tmp_path, settings_path=path
        )
    except BaseException as exc:
        result = exc
    assert isinstance(result, ToolNotFound)
    assert "Configured Wine" in str(result) and result.hint
    assert path.read_bytes() == before
