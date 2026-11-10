"""P5-T04a: assigning a file the user supplies to a track part (core).

Every refusal happens before anything is touched: ctstudio.toml keeps its exact bytes,
``files/`` keeps its contents and no backup folder appears. Test files are synthetic
(``test_magic`` builders); nothing comes from a game disc.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from test_magic import brres, kcl, kmp, png, postfx

from ctstudio.core.components.assign import assign_file
from ctstudio.core.components.status import evaluate
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project

BACKUPS = ".ctstudio/backups"


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "Pistë 日本", "T") as opened:
        yield opened


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def tree(folder: Path) -> dict[str, bytes]:
    if not folder.exists():
        return {}
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def entries(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def snapshot(project: Project) -> tuple[bytes, dict[str, bytes], bool]:
    root = project.root
    return project.manifest_path.read_bytes(), tree(root / "files"), (root / BACKUPS).exists()


def saved(project: Project, part: str) -> tuple[str, str | None]:
    table = getattr(manifest_io.load(project.manifest_path).components, part)
    return table.mode, table.file


PARTS = [
    ("course_model", "course_model.brres", brres()),
    ("kcl", "course.kcl", kcl()),
    ("minimap", "map_model.brres", brres(0x100)),
    ("skybox", "vrcorn_model.brres", brres(0xC0)),
    ("kmp", "course.kmp", kmp()),
]


@pytest.mark.parametrize(("part", "game_name", "data"), PARTS, ids=[p[0] for p in PARTS])
def test_a_file_is_copied_into_files_under_its_game_name_and_recorded(
    project: Project, tmp_path: Path, part: str, game_name: str, data: bytes
) -> None:
    source = write(tmp_path / "elsewhere" / "my track file.bin", data)
    before = project.manifest
    result = assign_file(project, part, source)
    assert result.file == f"files/{game_name}"
    assert (project.root / "files" / game_name).read_bytes() == data
    assert saved(project, part) == ("manual", f"files/{game_name}")
    assert result.manifest == manifest_io.load(project.manifest_path), "reloads equal"
    assert project.manifest is before, "the caller publishes the returned manifest"
    assert source.read_bytes() == data, "the original is left where it was"
    assert result.backup is None and not (project.root / BACKUPS).exists()
    assert entries(project.root / "files") == [game_name], "no temporary files or folders left"


def test_the_part_then_reports_manual_with_that_file(project: Project, tmp_path: Path) -> None:
    result = assign_file(project, "kcl", write(tmp_path / "c.kcl", kcl()))
    project.manifest = result.manifest
    status = evaluate(project, ())["kcl"]
    assert status.state == "manual" and status.reasons == ("using files/course.kcl",)


def test_post_effects_are_copied_as_a_whole_folder(project: Project, tmp_path: Path) -> None:
    source = tmp_path / "fx"
    write(source / "posteffect.bblm", postfx(b"PBLM"))
    write(source / "deeper" / "notes.txt", b"kept")
    old = project.root / "files" / "posteffect"
    write(old / "posteffect.bdof", postfx(b"PDOF"))
    result = assign_file(project, "posteffect", source)
    assert result.file == "files/posteffect"
    assert tree(old) == tree(source), "the old folder's other files are gone"
    assert result.backup is not None
    assert tree(result.backup / "files" / "posteffect") == {"posteffect.bdof": postfx(b"PDOF")}
    assert saved(project, "posteffect") == ("manual", "files/posteffect")
    assert entries(project.root / "files") == ["posteffect"]


def test_replacing_a_different_copy_backs_it_up_first(project: Project, tmp_path: Path) -> None:
    target = write(project.root / "files" / "course.kcl", kcl())
    result = assign_file(project, "kcl", write(tmp_path / "new.kcl", kcl(size=0x800)))
    assert target.read_bytes() == kcl(size=0x800)
    assert result.backup is not None
    assert result.backup.parent == project.root / BACKUPS
    assert tree(result.backup) == {"files/course.kcl": kcl()}
    assert entries(project.root / "files") == ["course.kcl"]


def test_a_copy_of_the_same_size_but_other_bytes_is_replaced(
    project: Project, tmp_path: Path
) -> None:
    target = write(project.root / "files" / "course.kcl", kcl())
    other = kcl()[:-1] + b"\x01"
    result = assign_file(project, "kcl", write(tmp_path / "new.kcl", other))
    assert target.read_bytes() == other
    assert result.backup is not None and tree(result.backup) == {"files/course.kcl": kcl()}


def test_a_folder_with_the_same_names_but_other_bytes_is_replaced(
    project: Project, tmp_path: Path
) -> None:
    old = project.root / "files" / "posteffect"
    write(old / "posteffect.bblm", postfx(b"PBLM"))
    write(tmp_path / "fx" / "posteffect.bblm", postfx(b"PBLM", size=0x60))
    result = assign_file(project, "posteffect", tmp_path / "fx")
    assert tree(old) == {"posteffect.bblm": postfx(b"PBLM", size=0x60)}
    assert result.backup is not None


def test_an_identical_folder_is_left_alone(project: Project, tmp_path: Path) -> None:
    write(project.root / "files" / "posteffect" / "posteffect.bblm", postfx(b"PBLM"))
    write(tmp_path / "fx" / "posteffect.bblm", postfx(b"PBLM"))
    result = assign_file(project, "posteffect", tmp_path / "fx")
    assert result.backup is None and not (project.root / BACKUPS).exists()


def test_an_empty_folder_and_a_file_of_the_same_name_are_not_the_same(
    project: Project, tmp_path: Path
) -> None:
    old = project.root / "files" / "posteffect"
    write(old / "posteffect.bblm", postfx(b"PBLM"))
    write(old / "extra", b"a file")
    write(tmp_path / "fx" / "posteffect.bblm", postfx(b"PBLM"))
    (tmp_path / "fx" / "extra").mkdir()
    result = assign_file(project, "posteffect", tmp_path / "fx")
    assert result.backup is not None, "the old copy differs, so it is replaced"
    assert (old / "extra").is_dir()


def test_an_identical_copy_is_left_alone(project: Project, tmp_path: Path) -> None:
    target = write(project.root / "files" / "course.kcl", kcl())
    stamp = target.stat().st_mtime_ns
    result = assign_file(project, "kcl", write(tmp_path / "same.kcl", kcl()))
    assert result.backup is None and not (project.root / BACKUPS).exists()
    assert target.stat().st_mtime_ns == stamp, "not rewritten"
    assert saved(project, "kcl") == ("manual", "files/course.kcl")


def test_choosing_the_copy_itself_copies_nothing(project: Project) -> None:
    target = write(project.root / "files" / "course.kcl", kcl())
    stamp = target.stat().st_mtime_ns
    result = assign_file(project, "kcl", target)
    assert result.file == "files/course.kcl" and result.backup is None
    assert target.stat().st_mtime_ns == stamp


def test_reference_in_place_records_the_path_and_copies_nothing(
    project: Project, tmp_path: Path
) -> None:
    outside = write(tmp_path / "outside" / "c.kcl", kcl())
    inside = write(project.root / "tracks" / "mine.kcl", kcl())
    assert assign_file(project, "kcl", outside, reference=True).file == str(outside.resolve())
    assert saved(project, "kcl") == ("manual", str(outside.resolve()))
    project.manifest = manifest_io.load(project.manifest_path)
    result = assign_file(project, "kcl", inside, reference=True)
    assert result.file == "tracks/mine.kcl", "inside the project: relative, with /"
    assert tree(project.root / "files") == {}


def test_a_manifest_backup_is_kept(project: Project, tmp_path: Path) -> None:
    old = project.manifest_path.read_bytes()
    result = assign_file(project, "kmp", write(tmp_path / "k.kmp", kmp()))
    assert result.manifest_backup is not None
    assert result.manifest_backup.read_bytes() == old


def test_the_rest_of_the_manifest_is_unchanged(project: Project, tmp_path: Path) -> None:
    result = assign_file(project, "kcl", write(tmp_path / "c.kcl", kcl()))
    before = project.manifest
    assert result.manifest.project == before.project
    assert result.manifest.components.course_model == before.components.course_model
    assert result.manifest.components.kcl.unbean == before.components.kcl.unbean


# --- refusals: explained, and nothing changed --------------------------------------------------


def refused(project: Project, part: str, source: Path, *, reference: bool = False) -> ProjectError:
    before = snapshot(project)
    with pytest.raises(Exception) as caught:
        assign_file(project, part, source, reference=reference)
    assert isinstance(caught.value, ProjectError), f"not explained: {caught.value!r}"
    assert snapshot(project) == before, "nothing may change"
    return caught.value


@pytest.mark.parametrize("reference", [False, True])
def test_the_wrong_type_is_refused_with_an_explanation(
    project: Project, tmp_path: Path, reference: bool
) -> None:
    error = refused(project, "kcl", write(tmp_path / "photo.png", png()), reference=reference)
    assert error.user_message == (
        "photo.png is the wrong type: expected collision file (KCL), found PNG image."
    )
    assert error.hint == "Choose a collision file (KCL) for the Collision."


def test_a_wrong_post_effect_folder_is_refused(project: Project, tmp_path: Path) -> None:
    error = refused(project, "posteffect", write(tmp_path / "posteffect.bblm", postfx(b"PBLM")))
    assert (
        error.user_message == "posteffect.bblm is the wrong type: expected a folder, found a file."
    )
    assert error.hint is not None and "folder of post-effect files" in error.hint
    folder = tmp_path / "fx"
    write(folder / "posteffect.bblm", kcl())
    error = refused(project, "posteffect", folder)
    assert "fx/posteffect.bblm is the wrong type" in error.user_message


def test_a_missing_source_is_refused(project: Project, tmp_path: Path) -> None:
    error = refused(project, "kcl", tmp_path / "gone.kcl")
    assert error.user_message == "gone.kcl was not found."


@pytest.mark.parametrize("reference", [False, True])
def test_a_source_inside_ctstudio_is_refused(project: Project, reference: bool) -> None:
    source = write(project.root / ".ctstudio" / "stage" / "course.kcl", kcl())
    error = refused(project, "kcl", source, reference=reference)
    assert (
        error.user_message == "course.kcl is inside the .ctstudio folder, which CT Studio manages."
    )
    assert error.hint == "Choose a file or folder outside .ctstudio."


def test_the_whole_project_folder_is_refused_for_post_effects(project: Project) -> None:
    error = refused(project, "posteffect", project.root, reference=True)
    assert error.user_message == (
        f"{project.root.name} contains the .ctstudio folder, which CT Studio manages."
    )
    assert error.hint == "Choose a file or folder outside .ctstudio."


@pytest.mark.parametrize("inner", ["files", "files/posteffect/sub"])
def test_a_folder_cannot_be_copied_into_or_out_of_itself(project: Project, inner: str) -> None:
    write(project.root / "files" / "posteffect" / "sub" / "posteffect.bblm", postfx(b"PBLM"))
    error = refused(project, "posteffect", project.root / inner)
    assert error.user_message.endswith("overlaps files/posteffect, where it would be copied.")
    assert error.hint == "Choose a folder outside files/posteffect, or use Reference in place."


@pytest.mark.parametrize("part", ["objects", "track_info", "no_such_part"])
def test_a_part_without_a_manual_mode_is_refused(
    project: Project, tmp_path: Path, part: str
) -> None:
    error = refused(project, part, write(tmp_path / "c.kcl", kcl()))
    assert "cannot use a file you supply" in error.user_message


def test_a_read_only_project_is_refused(project: Project, tmp_path: Path) -> None:
    project.close()
    error = refused(project, "kcl", write(tmp_path / "c.kcl", kcl()))
    assert error.user_message == "The project is read-only, so no file was assigned."
    assert error.hint is not None and "the project was closed" in error.hint


def test_a_manifest_changed_on_disk_is_refused(project: Project, tmp_path: Path) -> None:
    changed = project.manifest_path.read_bytes().replace(b'name = "T"', b'name = "Edited"')
    project.manifest_path.write_bytes(changed)
    error = refused(project, "kcl", write(tmp_path / "c.kcl", kcl()))
    assert error.user_message == "ctstudio.toml changed since the project was opened."
    assert error.hint == "Reopen the project, then assign the file again."


def test_a_drive_or_filesystem_root_is_named_in_full(project: Project) -> None:
    anchor = Path(project.root.anchor)
    error = refused(project, "posteffect", anchor, reference=True)
    assert error.user_message == f"{anchor} contains the .ctstudio folder, which CT Studio manages."


def test_a_path_with_a_nul_character_is_explained(project: Project) -> None:
    error = refused(project, "kcl", Path("bad\x00name.kcl"))
    assert error.hint is not None
