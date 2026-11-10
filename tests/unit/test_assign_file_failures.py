"""P5-T04a: a copy, backup, swap or save that fails part-way leaves the old file and manifest.

Failures are injected with monkeypatch at the OS boundary (copy, rename, unlink) or at the
manifest save; a previous copy that cannot be put back is never deleted.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_assign_file import entries, refused, tree, write
from test_magic import kcl, kmp, png, postfx

from ctstudio.core.build import backups
from ctstudio.core.components import assign
from ctstudio.core.components.assign import assign_file
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "Pistë 日本", "T") as opened:
        yield opened


def test_a_failed_copy_keeps_the_old_file_and_manifest(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(project.root / "files" / "course.kcl", kcl())
    source = write(tmp_path / "new.kcl", kcl(size=0x800))

    def full(*_args: object, **_kwargs: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(shutil, "copyfileobj", full)
    error = refused(project, "kcl", source)
    assert error.user_message == "Could not copy new.kcl into the project: No space left on device."
    assert error.hint == "Close programs using the file and free some disk space, then try again."


def test_a_copy_that_comes_out_as_another_type_is_not_used(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(project.root / "files" / "course.kcl", kcl())
    source = write(tmp_path / "new.kcl", kcl(size=0x800))

    def swapped(_data: object, out: object, *_args: object) -> None:
        out.write(png())  # type: ignore[attr-defined]  # the file changed while being copied

    monkeypatch.setattr(shutil, "copyfileobj", swapped)
    error = refused(project, "kcl", source)
    assert error.user_message == (
        "new.kcl is the wrong type: expected collision file (KCL), found PNG image."
    )


def test_a_failed_backup_changes_nothing(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(project.root / "files" / "course.kcl", kcl())

    def denied(*_args: object, **_kwargs: object) -> Path:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(assign, "save_copies", denied)
    error = refused(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    assert (
        error.user_message
        == "Could not back up files/course.kcl before replacing it: Permission denied."
    )


def disk_full(*_args: object, **_kwargs: object) -> Path:
    raise ProjectError(  # what fsutil raises when the write fails
        "Could not write ctstudio.toml.",
        hint="Check folder permissions and available disk space, then try again.",
        details="error=[Errno 28] No space left on device",
    )


def test_a_failed_save_puts_the_old_copy_back(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = write(project.root / "files" / "course.kcl", kcl())
    raw = project.manifest_path.read_bytes()
    monkeypatch.setattr(assign, "replace_with_backup", disk_full)
    with pytest.raises(ProjectError) as caught:
        assign_file(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    error = caught.value
    assert error.user_message == "Could not save ctstudio.toml, so no file was assigned."
    assert error.hint == (
        "The previous files/course.kcl was put back. "
        "Check folder permissions and available disk space, then try again."
    )
    assert error.details is not None and "No space left" in error.details
    assert target.read_bytes() == kcl(), "the old copy is back"
    assert project.manifest_path.read_bytes() == raw
    assert entries(project.root / "files") == ["course.kcl"]


def test_a_failed_save_removes_a_new_copy(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assign, "replace_with_backup", disk_full)
    with pytest.raises(ProjectError) as caught:
        assign_file(project, "kmp", write(tmp_path / "k.kmp", kmp()))
    assert caught.value.hint is not None
    assert caught.value.hint.startswith("The copy was removed. ")
    assert entries(project.root / "files") == [], "no copy left that ctstudio.toml does not name"


def test_a_failed_save_of_a_folder_puts_the_old_folder_back(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = project.root / "files" / "posteffect"
    write(old / "posteffect.bdof", postfx(b"PDOF"))
    write(tmp_path / "fx" / "posteffect.bblm", postfx(b"PBLM"))
    monkeypatch.setattr(assign, "replace_with_backup", disk_full)
    with pytest.raises(ProjectError):
        assign_file(project, "posteffect", tmp_path / "fx")
    assert tree(project.root / "files") == {"posteffect/posteffect.bdof": postfx(b"PDOF")}
    assert entries(project.root / "files") == ["posteffect"]


def test_a_failed_swap_keeps_the_old_file_and_leaves_nothing_behind(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = write(project.root / "files" / "course.kcl", kcl())
    real = Path.rename
    failures = [PermissionError(13, "Access is denied")]  # once: e.g. a virus scanner

    def locked(self: Path, to: Path) -> Path:
        if Path(to) == target and failures:
            raise failures.pop()
        return real(self, to)

    monkeypatch.setattr(Path, "rename", locked)
    before = project.manifest_path.read_bytes()
    with pytest.raises(ProjectError) as caught:
        assign_file(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    assert caught.value.user_message == (
        "Could not put the copy in place of course.kcl: Access is denied."
    )
    assert target.read_bytes() == kcl(), "the old file is back in place"
    assert entries(project.root / "files") == ["course.kcl"]
    assert project.manifest_path.read_bytes() == before


def test_an_undo_that_fails_says_where_the_previous_copy_is(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = write(project.root / "files" / "course.kcl", kcl())
    monkeypatch.setattr(assign, "replace_with_backup", disk_full)
    real = Path.unlink

    def busy(self: Path, missing_ok: bool = False) -> None:
        if self == target:
            raise PermissionError(13, "Access is denied")
        real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", busy)
    with pytest.raises(ProjectError) as caught:
        assign_file(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    hint = caught.value.hint or ""
    assert hint.startswith("The new copy at files/course.kcl could not be taken out again.")
    kept = [p for p in (project.root / "files").rglob("course.kcl.old")]
    assert len(kept) == 1 and kept[0].read_bytes() == kcl(), "the previous copy is not lost"
    assert str(kept[0]) in hint


def test_a_swap_whose_restore_also_fails_keeps_the_previous_copy(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = write(project.root / "files" / "course.kcl", kcl())
    real = Path.rename

    def locked(self: Path, to: Path) -> Path:
        if Path(to) == target:
            raise PermissionError(13, "Access is denied")
        return real(self, to)

    monkeypatch.setattr(Path, "rename", locked)
    with pytest.raises(ProjectError) as caught:
        assign_file(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    kept = list((project.root / "files").rglob("course.kcl.old"))
    assert len(kept) == 1 and kept[0].read_bytes() == kcl(), "the previous copy is not lost"
    assert (caught.value.hint or "").startswith(f"The previous copy is kept as {kept[0]}.")


def test_a_manifest_edited_during_the_copy_is_not_overwritten(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disk bytes are checked again at the save, not only before the copy starts."""
    target = write(project.root / "files" / "course.kcl", kcl())
    edited = project.manifest_path.read_bytes().replace(b'name = "T"', b'name = "Edited"')
    real = assign.type_problem
    calls: list[Path] = []

    def edit_meanwhile(spec: object, path: Path, shown: str) -> str | None:
        calls.append(path)
        if len(calls) == 2:  # the re-check of the staged copy, after the first disk check
            project.manifest_path.write_bytes(edited)
        return real(spec, path, shown)  # type: ignore[arg-type]

    monkeypatch.setattr(assign, "type_problem", edit_meanwhile)
    with pytest.raises(ProjectError) as caught:
        assign_file(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    assert len(calls) == 2
    assert caught.value.user_message == "Could not save ctstudio.toml, so no file was assigned."
    assert project.manifest_path.read_bytes() == edited, "the other edit is kept"
    assert target.read_bytes() == kcl(), "the previous copy is back"


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, MemoryError])
def test_an_interrupted_save_still_puts_the_old_copy_back(
    project: Project,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt: type[BaseException],
) -> None:
    target = write(project.root / "files" / "course.kcl", kcl())
    raw = project.manifest_path.read_bytes()

    def stopped(*_args: object, **_kwargs: object) -> Path:
        raise interrupt

    monkeypatch.setattr(assign, "replace_with_backup", stopped)
    with pytest.raises(interrupt):
        assign_file(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    assert target.read_bytes() == kcl(), "the old copy is back"
    assert entries(project.root / "files") == ["course.kcl"]
    assert project.manifest_path.read_bytes() == raw


def test_a_folder_backup_that_fails_part_way_explains_and_leaves_no_partial_backup(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = project.root / "files" / "posteffect"
    write(old / "posteffect.bblm", postfx(b"PBLM"))
    write(old / "posteffect.bdof", postfx(b"PDOF"))
    write(tmp_path / "fx" / "posteffect.blight", postfx(b"LGHT"))
    raw = project.manifest_path.read_bytes()
    real = shutil.copy2

    def denied(src: Path, dst: Path) -> object:
        if Path(src).name == "posteffect.bdof":  # the second file: the first is already copied
            raise PermissionError(13, "Permission denied", str(src))
        return real(src, dst)

    monkeypatch.setattr(backups.shutil, "copy2", denied)
    with pytest.raises(ProjectError) as caught:
        assign_file(project, "posteffect", tmp_path / "fx")
    assert caught.value.user_message == (
        "Could not back up files/posteffect before replacing it: Permission denied."
    )
    assert list((project.root / ".ctstudio" / "backups").glob("*")) == [], "no partial backup"
    assert tree(old) == {"posteffect.bblm": postfx(b"PBLM"), "posteffect.bdof": postfx(b"PDOF")}
    assert entries(project.root / "files") == ["posteffect"]
    assert project.manifest_path.read_bytes() == raw


def test_an_interrupted_copy_leaves_no_temporary_folder(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(project.root / "files" / "course.kcl", kcl())

    def stopped(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(shutil, "copyfileobj", stopped)
    with pytest.raises(KeyboardInterrupt):
        assign_file(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    assert entries(project.root / "files") == ["course.kcl"]


def test_an_interrupted_swap_puts_the_old_copy_back(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = write(project.root / "files" / "course.kcl", kcl())
    real = Path.rename

    def stopped(self: Path, to: Path) -> Path:
        if Path(to) == target and self.name == "course.kcl":  # moving the new copy in
            raise KeyboardInterrupt
        return real(self, to)

    monkeypatch.setattr(Path, "rename", stopped)
    with pytest.raises(KeyboardInterrupt):
        assign_file(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    assert target.is_file(), "the old copy is back in place"
    assert target.read_bytes() == kcl()
    assert entries(project.root / "files") == ["course.kcl"]


def test_a_file_that_cannot_be_compared_is_explained(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(project.root / "files" / "course.kcl", kcl())

    def denied(*_args: object, **_kwargs: object) -> bool:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(assign.filecmp, "cmp", denied)
    error = refused(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    assert error.user_message == "Could not read new.kcl or files/course.kcl: Permission denied."
    assert error.hint == "Close programs using the files, then try again."


def test_a_files_entry_that_is_not_a_folder_is_explained(project: Project, tmp_path: Path) -> None:
    shutil.rmtree(project.root / "files", ignore_errors=True)
    write(project.root / "files", b"not a folder")
    before = tree(project.root)
    error = refused(project, "kcl", write(tmp_path / "new.kcl", kcl()))
    assert error.user_message.startswith("Could not copy new.kcl into the project: ")
    assert "WinError" not in error.user_message and "\\\\" not in error.user_message
    assert error.hint == "Close programs using the file and free some disk space, then try again."
    assert tree(project.root) == before
