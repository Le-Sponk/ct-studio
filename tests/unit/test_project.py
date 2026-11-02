"""P3-T02: create and open a project folder (ARCHITECTURE §5).

``Project.create`` makes the folders, a default ``ctstudio.toml`` and a ``.gitignore``;
it refuses a folder that already has things in it unless ``force``, and never replaces an
existing ``ctstudio.toml``. ``Project.open`` loads the manifest and takes the lock, or
opens read-only and says why.
"""

from __future__ import annotations

import dataclasses
import os
import socket
from pathlib import Path

import pytest

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.project.manifest_io import FILE_NAME, load
from ctstudio.core.project.project import GITIGNORE, Project

pytestmark = pytest.mark.timeout(30)


def _dir(tmp_path: Path) -> Path:
    return tmp_path / "My Track é 日本"


def test_create_makes_the_layout_manifest_and_gitignore(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    with Project.create(root, "Sponk Speedway") as project:
        assert project.root == root
        assert not project.read_only
        for folder in ("files", "overrides", "build", ".ctstudio"):
            assert (root / folder).is_dir(), folder
        assert load(root / FILE_NAME) == Manifest(project=ProjectInfo(name="Sponk Speedway"))
        assert project.manifest == load(root / FILE_NAME)
        assert (root / ".gitignore").read_text(encoding="utf-8") == GITIGNORE
    assert GITIGNORE.splitlines() == [
        "# CT Studio: rebuilt on demand, safe to delete",
        ".ctstudio/",
        "build/",
    ]


def test_create_records_the_blend_and_slot(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    blend = root / "source" / "track.blend"
    with Project.create(root, "X", blend=blend, slot="old_mario_gc") as project:
        assert project.manifest.project.slot == "old_mario_gc"
        assert project.manifest.project.blend == "source/track.blend"  # relative, forward slashes


def test_a_blend_outside_the_project_is_stored_as_an_absolute_path(tmp_path: Path) -> None:
    blend = tmp_path / "elsewhere" / "track.blend"
    with Project.create(_dir(tmp_path), "X", blend=blend) as project:
        assert project.manifest.project.blend == str(blend.resolve())


def test_a_relative_blend_outside_the_project_is_stored_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with Project.create(Path("track"), "X", blend=Path("elsewhere") / "track.blend") as project:
        assert project.manifest.project.blend == str(
            tmp_path.resolve() / "elsewhere" / "track.blend"
        )


def test_create_checks_the_name_and_slot_before_touching_the_disk(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    with pytest.raises(ProjectError, match=r"project\.slot"):
        Project.create(root, "X", slot="rainbow")
    with pytest.raises(ProjectError, match=r"project\.name"):
        Project.create(root, "")
    assert not root.exists()


def test_create_refuses_a_folder_with_things_in_it(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    root.mkdir()
    (root / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(ProjectError) as raised:
        Project.create(root, "X")
    assert raised.value.user_message == f"{root} is not empty."
    assert raised.value.hint == (
        "Choose an empty or new folder, or use --force to add a project to this folder."
    )
    assert sorted(p.name for p in root.iterdir()) == ["notes.txt"]


def test_force_adds_a_project_and_leaves_the_users_files_alone(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    (root / "build").mkdir(parents=True)
    (root / "notes.txt").write_text("mine", encoding="utf-8")
    (root / ".gitignore").write_text("*.blend1\n", encoding="utf-8")
    with Project.create(root, "X", force=True):
        pass
    assert (root / "notes.txt").read_text(encoding="utf-8") == "mine"
    assert (root / ".gitignore").read_text(encoding="utf-8") == "*.blend1\n"  # theirs kept
    assert (root / FILE_NAME).is_file()


def test_create_never_replaces_an_existing_project_even_with_force(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    root.mkdir()
    (root / FILE_NAME).write_text("mine", encoding="utf-8")
    with pytest.raises(ProjectError) as raised:
        Project.create(root, "X", force=True)
    assert raised.value.user_message == f"{root} already has a CT Studio project."
    assert raised.value.hint == "Open it instead, or choose another folder."
    assert (root / FILE_NAME).read_text(encoding="utf-8") == "mine"


def test_create_refuses_a_file_where_the_folder_should_be(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    root.write_text("x", encoding="utf-8")
    with pytest.raises(ProjectError, match="is not a folder"):
        Project.create(root, "X")


def test_open_loads_the_manifest_and_holds_the_lock(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    Project.create(root, "X").close()
    assert not (root / ".ctstudio" / "lock").exists()
    with Project.open(root) as project:
        assert project.manifest.project.name == "X"
        assert not project.read_only
        assert project.read_only_reason is None
        assert (root / ".ctstudio" / "lock").is_file()
    assert not (root / ".ctstudio" / "lock").exists()


def test_a_second_open_is_read_only_and_says_why(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    with Project.create(root, "X"), Project.open(root) as second:
        assert second.read_only
        assert second.read_only_reason == (
            f"CT Studio (process {os.getpid()}) on this computer has this project open"
        )
        assert second.manifest.project.name == "X"


def test_save_writes_the_new_manifest(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    with Project.create(root, "X") as project:
        edited = dataclasses.replace(
            project.manifest, project=dataclasses.replace(project.manifest.project, author="Me")
        )
        project.save(edited)
        assert project.manifest == edited
    assert load(root / FILE_NAME).project.author == "Me"


def test_a_read_only_project_refuses_to_save(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    with Project.create(root, "X") as first, Project.open(root) as second:
        with pytest.raises(ProjectError) as raised:
            second.save(second.manifest)
        assert raised.value.user_message == "This project is open read-only, so it was not saved."
        assert first.manifest == load(root / FILE_NAME)


def test_a_closed_project_refuses_to_save(tmp_path: Path) -> None:
    project = Project.create(_dir(tmp_path), "X")
    project.close()
    assert project.read_only
    with pytest.raises(ProjectError, match="read-only"):
        project.save(project.manifest)


def test_open_creates_the_app_folder_when_it_was_deleted(tmp_path: Path) -> None:
    """.ctstudio/ is safe to delete (ARCHITECTURE §5)."""
    root = _dir(tmp_path)
    Project.create(root, "X").close()
    (root / ".ctstudio").rmdir()
    with Project.open(root) as project:
        assert not project.read_only


def test_open_of_a_folder_without_a_project_says_so(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    root.mkdir()
    with pytest.raises(ProjectError, match=r"There is no ctstudio\.toml in"):
        Project.open(root)
    assert not (root / ".ctstudio").exists()  # nothing created for a non-project


def test_a_bad_manifest_releases_the_lock(tmp_path: Path) -> None:
    root = _dir(tmp_path)
    Project.create(root, "X").close()
    (root / FILE_NAME).write_text("schema_version = 9\n", encoding="utf-8")
    with pytest.raises(ProjectError):
        Project.open(root)
    assert not (root / ".ctstudio" / "lock").exists()


def test_the_lock_names_this_computer(tmp_path: Path) -> None:
    with Project.create(_dir(tmp_path), "X") as project:
        assert project.lock_owner is None
        text = (project.root / ".ctstudio" / "lock").read_text(encoding="utf-8")
        assert socket.gethostname() in text
