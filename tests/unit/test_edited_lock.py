"""P5-T06b: Lock as manual keeps a part's edited output as the user's own file (core).

ARCHITECTURE §8 choice 2: the output CT Studio made and the user then edited is copied from
``.ctstudio/stage/`` into ``files/<game name>`` and the part switches to manual mode, so the
next build uses it as it is. The copy goes through the same checks and safe copy as
assigning a file (``assign.py``): a different copy already in ``files/`` is backed up first.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from edited_helpers import (
    BACKUPS,
    GAME_NAME,
    PARTS,
    edit,
    everything,
    made,
    stage,
    tree,
    write,
)
from test_magic import kcl

from ctstudio.core.components.edited import lock_as_manual
from ctstudio.core.components.status import ComponentStatus, State, evaluate
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "Pistë 日本", "T") as opened:
        yield opened


@pytest.mark.parametrize("part", PARTS)
def test_the_edited_output_is_copied_into_files_and_the_part_switches_to_manual(
    project: Project, part: str
) -> None:
    made(project, part)
    edit(project, part)
    in_stage = tree(stage(project))
    before = project.manifest
    name = GAME_NAME[part]

    result = lock_as_manual(project, part)

    assert result.file == f"files/{name}"
    table = getattr(result.manifest.components, part)
    assert (table.mode, table.file) == ("manual", f"files/{name}")
    saved = getattr(manifest_io.load(project.manifest_path).components, part)
    assert (saved.mode, saved.file) == ("manual", f"files/{name}")
    assert tree(project.root / "files") == in_stage, "files/ holds exactly the edited output"
    assert tree(stage(project)) == in_stage, "the edited output itself is left as it is"
    assert sorted(p.name for p in (project.root / "files").iterdir()) == [name]
    assert result.backup is None and not (project.root / BACKUPS).exists()
    assert result.manifest_backup is not None and result.manifest_backup.is_file()
    assert project.manifest == before, "the caller publishes the new manifest"


@pytest.mark.parametrize("part", PARTS)
def test_the_part_then_uses_its_own_file(project: Project, part: str) -> None:
    made(project, part)
    edit(project, part)
    project.manifest = lock_as_manual(project, part).manifest
    name = GAME_NAME[part]
    assert evaluate(project, ())[part] == ComponentStatus(State.MANUAL, (f"using files/{name}",))


def test_a_different_copy_already_in_files_is_backed_up_first(project: Project) -> None:
    old = write(project.root / "files" / "course.kcl", kcl(size=0x500)).read_bytes()
    made(project, "kcl")
    edited = edit(project, "kcl").read_bytes()
    result = lock_as_manual(project, "kcl")
    assert result.backup is not None
    assert tree(result.backup) == {"files/course.kcl": old}
    assert (project.root / "files" / "course.kcl").read_bytes() == edited


def test_only_the_locked_part_changes(project: Project) -> None:
    made(project, "kcl")
    made(project, "course_model")
    edit(project, "kcl")
    edit(project, "course_model")
    result = lock_as_manual(project, "kcl")
    model = result.manifest.components.course_model
    assert (model.mode, model.file) == ("auto", None)
    assert sorted(p.name for p in (project.root / "files").iterdir()) == ["course.kcl"]


def test_an_edit_that_is_no_longer_the_right_type_is_refused(project: Project) -> None:
    made(project, "kcl")
    edit(project, "kcl", b"not a collision file at all")
    before = everything(project)
    with pytest.raises(Exception) as caught:
        lock_as_manual(project, "kcl")
    error = caught.value
    assert isinstance(error, ProjectError), f"not explained: {error!r}"
    assert error.user_message == (
        "course.kcl is the wrong type: expected collision file (KCL), found an unrecognised "
        "file, so the Collision was not locked as manual."
    )
    assert error.hint == "Discard the edit, or fix the file in the program that changed it."
    assert everything(project) == before


def test_a_post_effects_edit_that_emptied_the_folder_is_refused(project: Project) -> None:
    made(project, "posteffect")
    for path in sorted((stage(project) / "posteffect").iterdir()):
        path.unlink()
    write(stage(project) / "posteffect" / "notes" / "x.txt", b"only a sub-folder")
    before = everything(project)
    with pytest.raises(Exception) as caught:
        lock_as_manual(project, "posteffect")
    assert isinstance(caught.value, ProjectError)
    assert caught.value.user_message.startswith("posteffect is empty, so the Post-effects")
    assert everything(project) == before
