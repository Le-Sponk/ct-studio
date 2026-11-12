"""P5-T06b: Lock as manual and Discard refuse, changing nothing, when they cannot be done.

Each refusal is a ``ProjectError`` that says what was not done and why, and leaves every file
and folder in the project exactly as it was (ctstudio.toml, files/, the edited output, no
backup folder), for both actions.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from edited_helpers import edit, everything, folders, made, stage
from test_magic import kcl

from ctstudio.core.components import edited as edited_module
from ctstudio.core.components.edited import discard_edit, edited_files, lock_as_manual
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project

pytestmark = pytest.mark.timeout(30)

type Action = Callable[[Project, str], object]
ACTIONS: list[tuple[str, Action, str]] = [
    ("lock", lock_as_manual, "locked as manual"),
    ("discard", discard_edit, "discarded"),
]
EACH = pytest.mark.parametrize(
    ("action", "done"), [(a, d) for _, a, d in ACTIONS], ids=[n for n, _, _ in ACTIONS]
)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "Pistë 日本", "T") as opened:
        yield opened


def refused(project: Project, action: Action, part: str) -> ProjectError:
    before = everything(project), folders(project)
    error: BaseException | None = None
    try:
        action(project, part)
    except Exception as exc:  # a crash of another type is a wrong answer, not an error node
        error = exc
    assert error is not None, f"{part} was not refused"
    assert isinstance(error, ProjectError), f"not explained: {error!r}"
    assert (everything(project), folders(project)) == before, "nothing may change"
    return error


def read_only_copy(project: Project) -> Project:
    """The same project opened read-only (as when another CT Studio holds it); still editable
    files, unchanged ctstudio.toml, so being read-only is the only reason to refuse."""
    return dataclasses.replace(project, lock=None, read_only_reason="it is open elsewhere")


@EACH
def test_a_read_only_project_is_refused(project: Project, action: Action, done: str) -> None:
    made(project, "kcl")
    edit(project, "kcl")
    error = refused(read_only_copy(project), action, "kcl")
    assert error.user_message == f"The project is read-only, so the Collision was not {done}."
    assert error.hint == "It is open elsewhere. Reopen it for editing."


@EACH
def test_a_closed_project_is_refused(project: Project, action: Action, done: str) -> None:
    made(project, "kcl")
    edit(project, "kcl")
    project.close()
    error = refused(project, action, "kcl")
    assert error.user_message == f"The project is read-only, so the Collision was not {done}."
    assert error.hint == "The project was closed. Reopen it for editing."


@EACH
@pytest.mark.parametrize("part", ["objects", "track_info", "kmp", "nonsense"])
def test_a_part_ct_studio_never_makes_is_refused(
    project: Project, action: Action, done: str, part: str
) -> None:
    error = refused(project, action, part)
    assert error.user_message.endswith(f"has no file made by CT Studio, so it was not {done}.")
    assert error.hint == "Only a part CT Studio makes can be edited outside it."


@EACH
def test_a_part_using_your_own_file_is_refused(project: Project, action: Action, done: str) -> None:
    made(project, "kcl")
    edit(project, "kcl")
    parts = project.manifest.components
    manual = dataclasses.replace(parts.kcl, mode="manual", file="files/course.kcl")
    project.save(
        dataclasses.replace(project.manifest, components=dataclasses.replace(parts, kcl=manual))
    )
    error = refused(project, action, "kcl")
    assert error.user_message == f"The Collision uses your own file, so it was not {done}."
    assert error.hint == "Press Refresh statuses to see each part's current state."


def never_made(_project: Project) -> None:
    pass


def not_edited(project: Project) -> None:
    made(project, "kcl")


def output_gone(project: Project) -> None:
    made(project, "kcl")
    (stage(project) / "course.kcl").unlink()


@EACH
@pytest.mark.parametrize("setup", [never_made, not_edited, output_gone])
def test_a_part_that_is_not_edited_is_refused(
    project: Project, action: Action, done: str, setup: Callable[[Project], object]
) -> None:
    setup(project)
    error = refused(project, action, "kcl")
    assert error.user_message == (
        f"The Collision was not changed outside CT Studio, so it was not {done}."
    )
    assert error.hint == "Press Refresh statuses to see each part's current state."


@EACH
def test_a_manifest_changed_on_disk_is_refused(project: Project, action: Action, done: str) -> None:
    made(project, "kcl")
    edit(project, "kcl")
    changed = project.manifest_path.read_bytes().replace(b'name = "T"', b'name = "Edited"')
    project.manifest_path.write_bytes(changed)
    error = refused(project, action, "kcl")
    assert error.user_message == "ctstudio.toml changed since the project was opened."
    assert error.hint == "Reopen the project, then try again."


def test_edited_files_names_each_changed_or_added_output(project: Project) -> None:
    made(project, "posteffect")
    made(project, "kcl")
    assert edited_files(project, "posteffect") == ()
    edit(project, "posteffect")
    (stage(project) / "posteffect" / "extra.bdof").write_bytes(b"added")
    assert edited_files(project, "posteffect") == (
        "posteffect/extra.bdof",
        "posteffect/posteffect.bblm",
    )
    assert edited_files(project, "kcl") == ()


def test_a_discard_whose_move_fails_keeps_the_edit_and_leaves_no_backup_folder(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    made(project, "kcl")
    edit(project, "kcl", kcl(size=0x440))
    failures = [PermissionError(13, "The file is in use", "course.kcl")]

    def busy(_source: Path, _target: Path) -> None:
        if failures:
            raise failures.pop()

    monkeypatch.setattr(edited_module, "move", busy)
    error = refused(project, discard_edit, "kcl")
    assert error.user_message == (
        "Could not move course.kcl into the backups: The file is in use. "
        "The Collision was not discarded."
    )
    assert error.hint == "Close programs using the file, then try again. Your edit was not touched."
