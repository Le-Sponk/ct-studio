"""P5-T06b: Lock as manual and Discard when the disk lets them down part-way.

Each failure is a ``ProjectError`` that says the action was not done, and leaves the project
as it was: the edit where it was, ctstudio.toml unchanged, and no empty backup folder behind.
"""

from __future__ import annotations

import errno
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from edited_helpers import edit, everything, folders, made, stage
from test_magic import kcl

from ctstudio.core.components import assign
from ctstudio.core.components import edited as edited_module
from ctstudio.core.components.edited import discard_edit, edited_files, lock_as_manual
from ctstudio.core.components.state import ComponentRecord, ProjectState, load_state, save_state
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project

pytestmark = pytest.mark.timeout(30)

type Action = Callable[[Project, str], object]
EACH = pytest.mark.parametrize(
    ("action", "done"),
    [(lock_as_manual, "locked as manual"), (discard_edit, "discarded")],
    ids=["lock", "discard"],
)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "Pistë 日本", "T") as opened:
        yield opened


def failed(project: Project, action: Action, part: str) -> ProjectError:
    before = everything(project), folders(project)
    with pytest.raises(ProjectError) as caught:
        action(project, part)
    assert (everything(project), folders(project)) == before, "nothing may change"
    return caught.value


def test_a_failed_save_says_the_part_was_not_locked(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    made(project, "kcl")
    edit(project, "kcl")

    def disk_full(*_args: object, **_kwargs: object) -> Path:
        raise ProjectError("Could not save ctstudio.toml.", hint="Free some disk space.")

    monkeypatch.setattr(assign, "replace_with_backup", disk_full)
    error = failed(project, lock_as_manual, "kcl")
    assert error.user_message == (
        "Could not save ctstudio.toml, so the Collision was not locked as manual."
    )
    assert error.hint is not None and error.hint.endswith("Free some disk space.")


def test_an_edited_file_that_cannot_be_read_says_the_part_was_not_locked(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    made(project, "kcl")
    edit(project, "kcl")

    def unreadable(*_args: object) -> object:
        raise ProjectError("Could not read course.kcl.", hint="Choose a file.", details="busy")

    monkeypatch.setattr(edited_module, "type_problem", unreadable)
    error = failed(project, lock_as_manual, "kcl")
    assert (
        error.user_message
        == "Could not read course.kcl, so the Collision was not locked as manual."
    )
    assert error.hint == "Close programs using the file, then try again."
    assert error.details == "busy"


@EACH
def test_an_unreadable_state_says_what_was_not_done(
    project: Project, action: Action, done: str
) -> None:
    made(project, "kcl")
    edit(project, "kcl")
    state = project.root / ".ctstudio" / "state.json"
    record = state.read_bytes()
    state.unlink()
    state.mkdir()  # cannot be read as a file (a damaged one is read as empty instead)
    (state / "kept.json").write_bytes(record)
    error = failed(project, action, "kcl")
    assert error.user_message == f"Could not read state.json, so the Collision was not {done}."
    assert error.hint is not None and "state.json" in error.hint


@pytest.mark.parametrize("fail_at", ["stamp", "inner"])
def test_a_discard_failing_while_making_its_folders_leaves_none_behind(
    project: Project, monkeypatch: pytest.MonkeyPatch, fail_at: str
) -> None:
    made(project, "kcl")
    edit(project, "kcl")
    real_mkdir = Path.mkdir
    backups = project.root / ".ctstudio" / "backups"

    def mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if self.is_relative_to(backups):
            depth = len(self.relative_to(backups).parts)  # 1: the stamp folder; 3: its stage
            if (fail_at == "stamp" and depth == 1) or (fail_at == "inner" and depth == 3):
                raise OSError(errno.EACCES, "Access is denied", str(self))
        real_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "mkdir", mkdir)
    error = failed(project, discard_edit, "kcl")
    assert error.user_message.endswith("The Collision was not discarded.")


def test_a_discard_failure_keeps_a_backups_folder_that_was_already_there(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    made(project, "kcl")
    edit(project, "kcl")
    (project.root / ".ctstudio" / "backups").mkdir()

    def busy(_source: Path, _target: Path) -> None:
        raise PermissionError(13, "The file is in use", "course.kcl")

    monkeypatch.setattr(edited_module, "move", busy)
    failed(project, discard_edit, "kcl")
    assert (project.root / ".ctstudio" / "backups").is_dir()


@EACH
def test_an_output_replaced_by_a_folder(project: Project, action: Action, done: str) -> None:
    made(project, "kcl")
    (stage(project) / "course.kcl").unlink()
    (stage(project) / "course.kcl" / "inside").mkdir(parents=True)
    (stage(project) / "course.kcl" / "inside" / "note.txt").write_bytes(b"x")
    if action is lock_as_manual:
        error = failed(project, action, "kcl")
        assert error.user_message == (
            "course.kcl is the wrong type: expected collision file (KCL), found a folder, "
            f"so the Collision was not {done}."
        )
        return
    folder = discard_edit(project, "kcl")
    assert (
        folder / ".ctstudio" / "stage" / "course.kcl" / "inside" / "note.txt"
    ).read_bytes() == b"x"
    assert not (stage(project) / "course.kcl").exists()


def test_edited_files_ignores_a_part_id_it_does_not_know(project: Project) -> None:
    made(project, "kcl")
    record = load_state(project.root).components["kcl"]
    state = ProjectState({"kcl": record, "retired_part": ComponentRecord("", record.outputs, {})})
    save_state(project.root, state)
    edit(project, "kcl", kcl(size=0x480))
    try:
        retired = edited_files(project, "retired_part")
    except Exception as exc:  # a crash is a wrong answer here, not an error
        retired = exc
    assert retired == ()
    assert edited_files(project, "kcl") == ("course.kcl",)


def test_a_failed_discard_removes_only_empty_folders_it_made(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    made(project, "kcl")
    edit(project, "kcl", kcl(size=0x440))
    backups = project.root / ".ctstudio" / "backups"
    earlier = backups / "2026-01-01T00-00-00.000000Z" / ".ctstudio" / "stage" / "course.kcl"
    earlier.parent.mkdir(parents=True)
    earlier.write_bytes(b"an earlier backup")
    real_new_folder = edited_module.new_backup_folder
    made_folders: list[Path] = []

    def new_folder(root: Path) -> Path:
        folder = real_new_folder(root)
        made_folders.append(folder)
        (folder / "written meanwhile").write_bytes(b"not ours to delete")  # e.g. another writer
        return folder

    def busy(_source: Path, _target: Path) -> None:
        raise PermissionError(13, "The file is in use", "course.kcl")

    monkeypatch.setattr(edited_module, "new_backup_folder", new_folder)
    monkeypatch.setattr(edited_module, "move", busy)
    with pytest.raises(ProjectError):
        discard_edit(project, "kcl")
    assert earlier.read_bytes() == b"an earlier backup"
    [folder] = made_folders
    kept = folder / "written meanwhile"
    assert kept.is_file(), "a file it did not write is never deleted"
    assert kept.read_bytes() == b"not ours to delete"
    assert not (folder / ".ctstudio").exists(), "its own empty folders are removed"
