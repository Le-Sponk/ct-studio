"""P5-T07e1: the status check says whether a single-file part's file exists right now."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from test_component_status import BLEND, MANUAL, World, build, out, tools_without
from test_magic import png

from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS
from ctstudio.core.components.state import GENERATED_DIR
from ctstudio.core.components.status import State, evaluate, single_file
from ctstudio.core.project.project import Project

pytestmark = pytest.mark.timeout(30)
FILE_PARTS = ("course_model", "kcl", "minimap", "skybox")


def world(tmp_path: Path) -> World:
    w = World(tmp_path / "Piste é")
    w.root.mkdir()
    return w


@pytest.mark.parametrize("part", FILE_PARTS)
def test_error_without_an_output_is_not_present(tmp_path: Path, part: str) -> None:
    w = world(tmp_path)
    w.blend()
    tools_without("blender" if part != "minimap" else "wszst")(w)
    got = w.status(part)
    assert got.state == State.ERROR, "precondition: a blocked part that was never made"
    assert not got.present, f"{part}: an unmade output counted as present"


@pytest.mark.parametrize("part", FILE_PARTS)
def test_made_edited_and_stale_outputs_are_present(tmp_path: Path, part: str) -> None:
    w = world(tmp_path)
    build(part)(w)
    assert w.status(part).present
    w.edit(out(part))
    assert w.status(part).state == State.EDITED_EXTERNALLY and w.status(part).present
    if part != "minimap":
        w.edit(BLEND)
        assert w.status(part).present


@pytest.mark.parametrize("part", FILE_PARTS)
def test_a_deleted_output_is_not_present(tmp_path: Path, part: str) -> None:
    w = world(tmp_path)
    build(part)(w)
    w.delete(out(part))
    assert not w.status(part).present


@pytest.mark.parametrize("part", FILE_PARTS)
def test_an_unrecorded_leftover_output_is_missing_and_not_present(
    tmp_path: Path, part: str
) -> None:
    """A file in the stage folder that CT Studio never recorded making is not its output."""
    w = world(tmp_path)
    w.blend()
    w.write(out(part), b"left over from somewhere else")
    got = w.status(part)
    assert got.state == State.MISSING, "precondition: never made, as far as the record says"
    assert not got.present, f"{part}: an unrecorded leftover was offered as the made file"
    tools_without("blender" if part != "minimap" else "wszst")(w)  # a blocker makes it Error
    blocked = w.status(part)
    assert blocked.state == State.ERROR, "precondition: a blocked, never-recorded part"
    assert not blocked.present, f"{part}: a blocked leftover was offered as the made file"


def test_a_source_gone_error_still_has_its_made_file(tmp_path: Path) -> None:
    w = world(tmp_path)
    build("kcl")(w)
    w.delete(BLEND)
    got = w.status("kcl")
    assert got.state == State.ERROR and got.present, "the made file still exists"


@pytest.mark.parametrize("part", [*FILE_PARTS, "kmp"])
def test_manual_files_are_present_only_when_they_exist(tmp_path: Path, part: str) -> None:
    w = world(tmp_path)
    w.manual(part)
    assert w.status(part).state == State.MANUAL and w.status(part).present
    w.manual(part, png())  # wrong type: an Error, but the file is there to inspect
    assert w.status(part).state == State.ERROR and w.status(part).present
    w.delete(MANUAL[part][0])
    assert not w.status(part).present


def test_a_manual_folder_where_a_file_belongs_is_not_present(tmp_path: Path) -> None:
    w = world(tmp_path)
    w.part("kcl", mode="manual", file="files/course.kcl")
    w.mkdir("files/course.kcl")
    got = w.status("kcl")
    assert got.state == State.ERROR and not got.present


def test_parts_without_a_single_file_are_never_present(tmp_path: Path) -> None:
    w = world(tmp_path)
    build("posteffect")(w)
    for part in ("posteffect", "objects", "track_info"):
        assert not w.status(part).present, part
        assert single_file(COMPONENT_BY_ID[part], w) is None


def test_a_new_project_without_tools_offers_no_files(tmp_path: Path) -> None:
    with Project.create(tmp_path / "New é", "New") as project:
        statuses = evaluate(project, ())
    errors = {part for part, status in statuses.items() if status.state == State.ERROR}
    assert errors >= set(FILE_PARTS), "precondition: the first-run state the review found"
    assert not any(status.present for status in statuses.values())


def test_single_file_matches_the_planned_output_paths(tmp_path: Path) -> None:
    w = world(tmp_path)
    for spec in COMPONENTS:
        if spec.kind is not None and spec.id != "kmp":
            expected = w.root / GENERATED_DIR / spec.outputs[0]
            assert single_file(spec, w) == expected, spec.id
    w.manual("kmp")
    assert single_file(COMPONENT_BY_ID["kmp"], w) == w.root / MANUAL["kmp"][0]
    w.part("kmp", mode="manual", file=None)
    assert single_file(COMPONENT_BY_ID["kmp"], w) is None


def test_present_is_part_of_equality(tmp_path: Path) -> None:
    w = world(tmp_path)
    w.manual("kcl")
    got = w.status("kcl")
    assert got != dataclasses.replace(got, present=False)
