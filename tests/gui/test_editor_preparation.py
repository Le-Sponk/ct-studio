"""Immutable advisory choices, not launch authority or UI-thread evidence."""

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
from editor_preparation_helpers import (
    Finder,
    assignment_error,
    file_at,
    no_side_effects,
    project_at,
    tree,
)

from ctstudio.core.errors import CTStudioError
from ctstudio.core.project import settings
from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.core.tools.spec import CustomTool
from ctstudio.gui.editor_launch import EditorLaunchService

__all__ = ["no_side_effects"]


def test_native_preferred_choices_are_immutable_read_only(tmp_path: Path) -> None:
    project = project_at(tmp_path / "project café 空")
    doc = file_at(project.root, "course.BRRES")
    exe = file_at(tmp_path, "editor café 空")
    path = tmp_path / "settings.json"
    path.write_text(
        '{"format":1,"tools":{"riistudio":'
        + json.dumps(str(exe))
        + '},"editor_preferences":{".brres":"riistudio"}}',
        encoding="utf-8",
    )
    finder = Finder(tmp_path)
    before = tree(tmp_path)
    prepared = EditorLaunchService(path, discover_tool=finder).prepare(project, doc)
    assert prepared.document == doc.resolve() and prepared.kind == ".brres"
    assert tuple(option.choice for option in prepared.options) == (
        EditorChoice("builtin", "riistudio"),
        EditorChoice("builtin", "brawlcrate"),
    )
    assert [option.state for option in prepared.options] == ["available", "missing"]
    assert prepared.options[0].label == "RiiStudio"
    assert prepared.options[1].explanation and prepared.options[1].hint
    assert isinstance(assignment_error(prepared, "kind", ".szs"), FrozenInstanceError)
    assert isinstance(
        assignment_error(prepared.options[0], "label", "changed"), FrozenInstanceError
    )
    assert isinstance(
        assignment_error(prepared.options[0].choice, "namespace", "custom"), FrozenInstanceError
    )
    assert isinstance(prepared.options, tuple)
    assert not hasattr(prepared, "executable")
    assert not hasattr(prepared.options[0], "args_template")
    assert tree(tmp_path) == before


@pytest.mark.parametrize("suffix", [".brres", ".odd", ""])
def test_custom_choices_keep_exact_namespace_insertion_order_and_fresh_settings(
    tmp_path: Path, suffix: str
) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "pièce 空" + suffix)
    exe = file_at(tmp_path, "custom program")
    path = tmp_path / "settings.json"
    loaded = settings.UserSettings().with_custom_tool(
        "zz", CustomTool("Last alphabetically", exe, ["{file}"])
    )
    loaded = loaded.with_custom_tool("brawlcrate", CustomTool("Collision", exe, []))
    loaded = loaded.with_custom_tool("aa", CustomTool("First alphabetically", exe, []))
    path.write_text(json.dumps({"format": 1, "tools": {}, **loaded.other}), encoding="utf8")
    service = EditorLaunchService(path, discover_tool=Finder(tmp_path))
    first = service.prepare(project, doc)
    custom = [option for option in first.options if option.choice.namespace == "custom"]
    assert [option.choice.tool_id for option in custom] == ["zz", "brawlcrate", "aa"]
    assert [option.label for option in custom] == [
        "Last alphabetically",
        "Collision",
        "First alphabetically",
    ]
    assert all(option.state == "available" for option in custom)
    changed = settings.UserSettings().with_custom_tool(
        "aa", CustomTool("Changed", tmp_path / "gone", [])
    )
    path.write_text(json.dumps({"format": 1, "tools": {}, **changed.other}), encoding="utf8")
    second = service.prepare(project, doc)
    assert [o.label for o in second.options if o.choice.namespace == "custom"] == ["Changed"]
    assert second.options[-1].state == "missing" and second.options[-1].hint
    assert custom[0].label == "Last alphabetically"


def test_fresh_builtin_preference_and_discovery_use_actual_filesystem(tmp_path: Path) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "course.szs")
    (tmp_path / "bin").mkdir()
    file_at(tmp_path / "bin", "BrawlCrate.exe")
    finder = Finder(tmp_path)
    finder.environment = replace(finder.environment, variables={"PATH": str(tmp_path / "bin")})
    path = tmp_path / "settings.json"
    service = EditorLaunchService(path, discover_tool=finder)
    first = service.prepare(project, doc)
    assert first.options[0].choice.tool_id == "brawlcrate" and first.options[0].state == "available"
    path.write_text(
        json.dumps({"format": 1, "editor_preferences": {".szs": "riistudio"}}), encoding="utf8"
    )
    second = service.prepare(project, doc)
    assert second.options[0].choice.tool_id == "riistudio" and second.options[0].state == "missing"
    assert second.options[1].state == "available"
    assert finder.calls == [
        ("brawlcrate", None, True),
        ("riistudio", None, True),
        ("riistudio", None, True),
        ("brawlcrate", None, True),
    ]


@pytest.mark.parametrize("collision", ["absent", "COURSE.KCL", "directory", "course.kcl"])
def test_lorenzi_requires_exact_regular_sibling_not_installation(
    tmp_path: Path, collision: str
) -> None:
    project = project_at(tmp_path / "project")
    doc = file_at(project.root, "course.kmp")
    if collision == "directory":
        (project.root / "course.kcl").mkdir()
    elif collision != "absent":
        file_at(project.root, collision)
    result = EditorLaunchService(
        tmp_path / "settings.json", discover_tool=Finder(tmp_path)
    ).prepare(project, doc)
    option = result.options[0]
    assert option.choice.tool_id == "kmp_editor_lorenzi"
    assert option.state == ("missing" if collision == "course.kcl" else "ineligible")
    assert "course.kcl" in option.explanation or collision == "course.kcl"
    assert option.hint


@pytest.mark.parametrize("kind", ["folder", "missing"])
def test_non_regular_documents_are_typed_refusals(tmp_path: Path, kind: str) -> None:
    project = project_at(tmp_path / "project")
    target = project.root / "course.brres"
    if kind == "folder":
        target.mkdir()
    result: object = None
    try:
        result = EditorLaunchService(
            tmp_path / "settings.json", discover_tool=Finder(tmp_path)
        ).prepare(project, target)
    except BaseException as error:
        result = error
    assert isinstance(result, CTStudioError) and result.hint
