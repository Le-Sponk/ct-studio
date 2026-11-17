"""Typed preparation failures, identity checks and fresh settings refusal."""

import json
from dataclasses import replace
from os import stat_result
from pathlib import Path
from typing import NoReturn

import pytest
from editor_preparation_helpers import Finder, file_at, no_side_effects, project_at

from ctstudio.core.errors import CTStudioError, ProjectError
from ctstudio.core.project import settings
from ctstudio.gui.editor_launch import EditorLaunchService

__all__ = ["no_side_effects"]


@pytest.mark.parametrize(
    "stage", ["discovery", "settings", "document", "collision", "sibling_stat"]
)
@pytest.mark.parametrize(
    "error",
    [
        PermissionError("denied"),
        ValueError("bad path"),
        RuntimeError("busy"),
        ProjectError("typed", hint="repair"),
        KeyboardInterrupt(),
        SystemExit(7),
    ],
)
def test_inspection_failures_keep_exact_causes_or_interrupts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, error: BaseException
) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "course.kmp")
    sibling = file_at(project.root, "course.kcl")
    cause = OSError("previous cause")
    error.__cause__ = cause
    original_stat = Path.stat

    def fail(*_args: object, **_kwargs: object) -> NoReturn:
        raise error

    def faulty_stat(path: Path, *, follow_symlinks: bool = True) -> stat_result:
        if path == (sibling if stage == "sibling_stat" else doc):
            raise error
        return original_stat(path, follow_symlinks=follow_symlinks)

    result: object = None
    with monkeypatch.context() as patcher:
        finder = Finder(tmp_path)
        if stage == "settings":
            patcher.setattr(settings, "load", fail)
        elif stage == "collision":
            patcher.setattr(Path, "iterdir", fail)
        elif stage in ("document", "sibling_stat"):
            patcher.setattr(Path, "stat", faulty_stat)
        else:
            patcher.setattr(Finder, "__call__", fail)
        try:
            result = EditorLaunchService(tmp_path / "settings.json", discover_tool=finder).prepare(
                project, doc
            )
        except BaseException as caught:
            result = caught
    if isinstance(error, (OSError, ValueError, RuntimeError)):
        assert isinstance(result, CTStudioError) and result.hint
        assert result.__cause__ is error
    else:
        assert result is error
        assert isinstance(result, BaseException) and result.__cause__ is cause


@pytest.mark.parametrize("change", ["root", "manifest"])
def test_mutated_project_identity_is_not_returned_as_prepared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "course.brres")
    original_root, original_manifest = project.root, project.manifest
    real_load = settings.load

    def changing_load(path: Path | None = None) -> settings.UserSettings:
        result = real_load(path)
        if change == "root":
            project.root = original_root / "different"
        else:
            project.manifest = replace(original_manifest)
        return result

    monkeypatch.setattr(settings, "load", changing_load)
    result: object = None
    try:
        result = EditorLaunchService(
            tmp_path / "settings.json", discover_tool=Finder(tmp_path)
        ).prepare(project, doc)
    except BaseException as error:
        result = error
    assert isinstance(result, ProjectError) and "changed" in str(result) and result.hint


@pytest.mark.parametrize("damage", ["json", "preferences", "custom", "prefix"])
def test_fresh_damaged_settings_never_fall_back_or_return_partial_choices(
    tmp_path: Path, damage: str
) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "course.brres")
    path = tmp_path / "settings.json"
    finder = Finder(tmp_path)
    service = EditorLaunchService(path, discover_tool=finder)
    assert len(service.prepare(project, doc).options) == 2
    data: dict[str, dict[str, object]] = {
        "preferences": {"editor_preferences": {".brres": "wrong"}},
        "custom": {"custom_tools": []},
        "prefix": {"wine_prefixes": []},
    }
    path.write_text(
        "{" if damage == "json" else json.dumps({"format": 1, **data[damage]}), encoding="utf8"
    )
    finder.calls.clear()
    before = path.read_bytes()
    result: object = None
    try:
        result = service.prepare(project, doc)
    except BaseException as error:
        result = error
    assert isinstance(result, settings.SettingsError) and result.hint
    assert finder.calls == [] and path.read_bytes() == before


@pytest.mark.parametrize(
    "error", [PermissionError("denied"), ValueError("invalid"), RuntimeError("busy")]
)
def test_configured_builtin_stat_fault_keeps_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "course.brres")
    exe = file_at(tmp_path, "program")
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"format": 1, "tools": {"brawlcrate": str(exe)}}), encoding="utf8")
    real_stat = Path.stat

    def faulty_stat(path: Path, *, follow_symlinks: bool = True) -> stat_result:
        if path == exe:
            raise error
        return real_stat(path, follow_symlinks=follow_symlinks)

    result: object = None
    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "stat", faulty_stat)
        try:
            result = EditorLaunchService(path, discover_tool=Finder(tmp_path)).prepare(project, doc)
        except BaseException as caught:
            result = caught
    assert isinstance(result, CTStudioError) and result.__cause__ is error and result.hint


def test_lexical_unicode_document_becomes_canonical_with_unknown_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = project_at(tmp_path / "project café 空")
    doc = file_at(project.root, "pièce.ODD")
    monkeypatch.chdir(tmp_path)
    lexical = Path(project.root.name) / ".." / project.root.name / doc.name
    prepared = EditorLaunchService(
        tmp_path / "settings.json", discover_tool=Finder(tmp_path)
    ).prepare(project, lexical)
    assert prepared.document == doc.resolve() and prepared.kind == ".odd"
    assert prepared.options == ()
