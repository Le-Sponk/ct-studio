"""Nonspawning Wine and unavailable-route advisory readiness."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from editor_preparation_helpers import (
    Finder,
    file_at,
    linux,
    no_side_effects,
    pe_at,
    project_at,
    tree,
)

from ctstudio.core.project import settings
from ctstudio.core.tools import discovery, wine
from ctstudio.core.tools.spec import CustomTool, ToolSpec
from ctstudio.gui.editor_launch import EditorLaunchService

__all__ = ["no_side_effects"]


@pytest.mark.parametrize("namespace", ["builtin", "custom"])
@pytest.mark.parametrize(
    "fault", ["none", "no_prefix", "bad_arch", "bad_pe", "no_wine", "discover_only"]
)
def test_wine_readiness_inspects_pe_prefix_without_processes(
    tmp_path: Path, namespace: str, fault: str
) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "course.brres")
    exe = pe_at(tmp_path, "program.EXE")
    assert wine.exe_arch(exe) == "win64"
    launcher = file_at(tmp_path, "wine")
    if fault == "discover_only":
        (tmp_path / "bin").mkdir()
        launcher.rename(tmp_path / "bin" / "wine")
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    (prefix / "system.reg").write_text(
        "#arch=" + ("win32" if fault == "bad_arch" else "win64"), encoding="utf8"
    )
    if fault == "bad_pe":
        exe.write_bytes(b"not PE")
    loaded = settings.UserSettings(
        {"wine": str(launcher)} if fault not in ("no_wine", "discover_only") else {}
    )
    if namespace == "builtin":
        loaded = loaded.with_tool("brawlcrate", exe)
    else:
        loaded = loaded.with_custom_tool("brawlcrate", CustomTool("Custom", exe, ["{file}"]))
    if fault != "no_prefix":
        loaded = loaded.with_wine_prefix("brawlcrate", prefix)
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"format": 1, "tools": dict(loaded.tools), **loaded.other}), encoding="utf8"
    )
    finder = Finder(tmp_path)
    finder.environment = replace(finder.environment, platform="linux")
    before = tree(tmp_path)
    result = EditorLaunchService(path, discover_tool=finder, current_platform=linux).prepare(
        project, doc
    )
    matches = [
        o
        for o in result.options
        if o.choice.namespace == namespace and o.choice.tool_id == "brawlcrate"
    ]
    assert len(matches) == 1, "The exact saved editor choice must remain present"
    option = matches[0]
    assert option.state == (
        "available"
        if fault == "none" or (fault == "discover_only" and namespace == "builtin")
        else "missing"
    )
    assert option.explanation and (option.state == "available" or option.hint)
    assert tree(tmp_path) == before


@pytest.mark.parametrize("namespace", ["builtin", "custom"])
def test_native_readiness_ignores_unused_unsafe_wine_metadata(
    tmp_path: Path, namespace: str
) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "course.brres")
    exe = file_at(tmp_path, "native program")
    loaded = settings.UserSettings({"wine": "unsafe\0unused"})
    if namespace == "builtin":
        loaded = loaded.with_tool("brawlcrate", exe)
    else:
        loaded = loaded.with_custom_tool("brawlcrate", CustomTool("Custom", exe, []))
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"format": 1, "tools": dict(loaded.tools), **loaded.other}), encoding="utf8"
    )
    result = EditorLaunchService(
        path, discover_tool=Finder(tmp_path), current_platform=linux
    ).prepare(project, doc)
    matches = [
        o
        for o in result.options
        if o.choice.namespace == namespace and o.choice.tool_id == "brawlcrate"
    ]
    assert len(matches) == 1, "The exact saved editor choice must remain present"
    option = matches[0]
    assert option.state == "available"


def test_custom_wine_route_uses_canonical_not_lexical_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "course.odd")
    exe = pe_at(tmp_path, "canonical café 空.EXE")
    alias = file_at(tmp_path, "lexical program")
    loaded = settings.UserSettings().with_custom_tool("zz", CustomTool("Custom", alias, []))
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"format": 1, **loaded.other}), encoding="utf8")
    real_resolve = Path.resolve

    def resolve(candidate: Path, strict: bool = False) -> Path:
        return exe if candidate == alias else real_resolve(candidate, strict=strict)

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "resolve", resolve)
        result = EditorLaunchService(
            path, discover_tool=Finder(tmp_path), current_platform=linux
        ).prepare(project, doc)
    assert len(result.options) >= 1, "Preparation must retain the expected choice"
    assert result.options[0].state == "missing"
    assert "Wine executable and prefix" in result.options[0].hint


class FlatpakFinder(Finder):
    def __call__(
        self, spec: ToolSpec, *, configured: Path | None = None, include_dev: bool = False
    ) -> discovery.ToolLocation | None:
        return discovery.ToolLocation(self.environment.root / "flatpak", None, "flatpak", "flatpak")


@pytest.mark.parametrize("route", ["flatpak", "wine"])
def test_blender_unsupported_routes_are_missing_not_available(tmp_path: Path, route: str) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "course.blend")
    exe = pe_at(tmp_path, "blender.exe")
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"format": 1, "tools": {"blender": str(exe)}}), encoding="utf8")
    finder = FlatpakFinder(tmp_path) if route == "flatpak" else Finder(tmp_path)
    finder.environment = replace(finder.environment, platform="linux")
    result = EditorLaunchService(path, discover_tool=finder, current_platform=linux).prepare(
        project, doc
    )
    assert len(result.options) >= 1, "Preparation must retain the expected choice"
    assert result.options[0].state == "missing"
    assert ("Flatpak" if route == "flatpak" else "Linux build") in result.options[0].hint
