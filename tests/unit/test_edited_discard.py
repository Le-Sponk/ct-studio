"""P5-T06b: Discard puts a part's edited output into the backups so the next build remakes it.

ARCHITECTURE §8 choice 3: the output CT Studio made and the user then edited is moved, in one
rename, into ``.ctstudio/backups/<UTC time>/.ctstudio/stage/…`` (its project-relative path).
Nothing is deleted: the edit is kept whole in the backup and the part reports Missing, so the
next build makes it again (the build cache backs up only outputs that are there, so no second
backup is made). ctstudio.toml is not touched.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from edited_helpers import BACKUPS, GAME_NAME, MADE, PARTS, edit, made, stage, tree, write

from ctstudio.core.components.edited import discard_edit
from ctstudio.core.components.state import STATE_FILE
from ctstudio.core.components.status import State, evaluate
from ctstudio.core.project.project import Project

pytestmark = pytest.mark.timeout(30)
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d\.\d{6}Z(-\d+)?")


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    blend = write(tmp_path / "art" / "track.blend", b"BLENDER-v300REND")  # so parts can be made
    with Project.create(tmp_path / "Pistë 日本", "T", blend=blend) as opened:
        yield opened


@pytest.mark.parametrize("part", PARTS)
def test_the_edited_output_moves_whole_into_a_new_backup_folder(
    project: Project, part: str
) -> None:
    made(project, part)
    edit(project, part)
    in_stage = tree(stage(project))
    toml = project.manifest_path.read_bytes()

    backup = discard_edit(project, part)

    assert backup.parent == project.root / BACKUPS
    assert STAMP.fullmatch(backup.name), backup.name
    assert tree(backup) == {f".ctstudio/stage/{rel}": data for rel, data in in_stage.items()}
    assert not (stage(project) / GAME_NAME[part]).exists(), "gone, so the build makes it again"
    assert project.manifest_path.read_bytes() == toml


@pytest.mark.parametrize("part", PARTS)
def test_the_part_then_reports_missing_so_the_next_build_makes_it(
    project: Project, part: str
) -> None:
    made(project, part)
    edit(project, part)
    discard_edit(project, part)
    status = evaluate(project, ("blender", "rszst", "abmatt", "wimgt", "wkclt", "wszst"))[part]
    assert status.state is State.MISSING
    assert status.reasons == tuple(f"{rel} is gone; it will be made again" for rel in MADE[part])


def test_other_parts_and_the_record_of_what_was_made_are_left_alone(project: Project) -> None:
    made(project, "kcl")
    made(project, "course_model")
    edit(project, "kcl")
    state = (project.root / STATE_FILE).read_bytes()
    model = (stage(project) / "course_model.brres").read_bytes()
    discard_edit(project, "kcl")
    assert (stage(project) / "course_model.brres").read_bytes() == model
    assert (project.root / STATE_FILE).read_bytes() == state


def test_a_file_added_to_the_post_effects_folder_goes_into_the_backup_too(
    project: Project,
) -> None:
    made(project, "posteffect")
    added = stage(project) / "posteffect" / "posteffect.bdof"
    added.write_bytes(b"added by hand")
    backup = discard_edit(project, "posteffect")
    assert tree(backup)[".ctstudio/stage/posteffect/posteffect.bdof"] == b"added by hand"
    assert not (stage(project) / "posteffect").exists()


def test_each_discard_gets_its_own_backup_folder(project: Project) -> None:
    made(project, "kcl")
    first_edit = edit(project, "kcl", b"first edit").read_bytes()
    first = discard_edit(project, "kcl")
    made(project, "kcl")
    edit(project, "kcl", b"second edit")
    second = discard_edit(project, "kcl")
    assert first != second
    assert tree(first) == {".ctstudio/stage/course.kcl": first_edit}
    assert tree(second) == {".ctstudio/stage/course.kcl": b"second edit"}
