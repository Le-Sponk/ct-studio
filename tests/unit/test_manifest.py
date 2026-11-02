"""P3-T01: the project manifest ``ctstudio.toml`` — model, load and save.

The model mirrors ARCHITECTURE §6. ``load`` never writes; ``save`` writes the whole file
atomically. Keys CT Studio does not know are kept and written back (with one logged
warning each); comments are not kept, because the TOML writer (tomli-w) cannot keep them.
"""

from __future__ import annotations

import dataclasses
import logging
import tomllib
from pathlib import Path

import pytest

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.manifest import (
    SCHEMA_VERSION,
    BuildSettings,
    CourseModel,
    Manifest,
    MaterialOverride,
    ProjectInfo,
    TextureOverride,
)
from ctstudio.core.project.manifest_io import FILE_NAME, load, save
from ctstudio.core.project.slots import SLOTS

pytestmark = pytest.mark.timeout(30)

# The ARCHITECTURE §6 sketch, comments and all.
SKETCH = """\
schema_version = 1

[project]
name = "Sponk Speedway"
author = "Le-Sponk"
version = "1.0"
slot = "beginner_course"
blend = "source/track.blend"

[build]
test_compression = "fast"        # mapped to verified wszst flags in the adapter
release_compression = "best"
make_d_variant = true
auto_add = true
extra_wszst_args = []

[blender.collections]           # mapping; auto-detected on project creation, user-reviewable
course = "Course"
kcl = "KCL"
skybox = "Skybox"
minimap = ""                     # empty → derive from KCL

[components.course_model]
mode = "auto"                    # auto | manual
backend = "default"              # resolves to the ADR-004 choice
extra_import_args = []
post_import_commands = ""        # optional ABMatt command file under overrides/

[components.course_model.textures."road.png"]    # only stored when overriding a recommendation
format = "CMPR"
mipmaps = 4

[components.course_model.materials."fence"]
transparency = "cutout"          # auto | opaque | cutout | translucent
cull = "none"                    # front (default) | back | none

[components.kcl]
mode = "auto"
unbean = "lower"                 # passed through to the Blender add-on exporter

[components.minimap]
mode = "auto"
source = "kcl"                   # kcl | blender | file
include_kcl_types = ["road", "slippery_road", "boost_panel", "boost_ramp", "jump_pad"]

[components.kmp]
mode = "manual"
file = "files/course.kmp"
editor = "lorenzi"

[components.skybox]
mode = "manual"
file = "files/vrcorn_model.brres"

[components.posteffect]
mode = "template"
template_track = "beginner_course"

[hooks]                           # optional power-user scripts, run with documented env vars
post_stage = ""
post_build = ""
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "Track é 日本" / FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_the_file_name_is_ctstudio_toml() -> None:
    assert FILE_NAME == "ctstudio.toml"


def test_the_architecture_sketch_loads_with_every_value(tmp_path: Path) -> None:
    m = load(_write(tmp_path, SKETCH))
    assert m.schema_version == SCHEMA_VERSION == 1
    assert m.project == ProjectInfo(
        name="Sponk Speedway",
        author="Le-Sponk",
        version="1.0",
        slot="beginner_course",
        blend="source/track.blend",
    )
    assert m.build == BuildSettings()
    assert m.blender.collections.course == "Course"
    assert m.blender.collections.minimap == ""
    course = m.components.course_model
    assert course.mode == "auto"
    assert course.backend == "default"
    assert course.textures == {"road.png": TextureOverride(format="CMPR", mipmaps=4)}
    assert course.materials == {"fence": MaterialOverride(transparency="cutout", cull="none")}
    assert m.components.kcl.unbean == "lower"
    assert m.components.minimap.include_kcl_types[0] == "road"
    assert m.components.kmp.file == "files/course.kmp"
    assert m.components.kmp.editor == "lorenzi"
    assert m.components.skybox.mode == "manual"
    assert m.components.posteffect.template_track == "beginner_course"
    assert m.hooks.post_build == ""
    assert m.extra == {}


def test_only_a_name_is_needed_and_everything_else_has_a_default(tmp_path: Path) -> None:
    m = load(_write(tmp_path, 'schema_version = 1\n[project]\nname = "X"\n'))
    assert m == Manifest(project=ProjectInfo(name="X"))
    assert m.project.slot == "beginner_course"
    assert m.project.blend is None
    assert m.components.kmp.mode == "manual"
    assert m.components.posteffect.mode == "template"


def test_a_skybox_can_be_copied_from_an_original_track(tmp_path: Path) -> None:
    text = 'schema_version = 1\n[project]\nname = "X"\n[components.skybox]\nmode = "template"\n'
    m = load(_write(tmp_path, text + 'template_track = "old_mario_gc"\n'))
    assert m.components.skybox.mode == "template"
    assert m.components.skybox.template_track == "old_mario_gc"
    assert load(_write(tmp_path, text)).components.skybox.template_track == "beginner_course"


def test_save_then_load_gives_the_same_manifest(tmp_path: Path) -> None:
    m = load(_write(tmp_path, SKETCH))
    out = tmp_path / "out" / FILE_NAME
    out.parent.mkdir()
    save(m, out)
    assert load(out) == m


def test_a_saved_file_starts_with_the_schema_version_and_is_stable(tmp_path: Path) -> None:
    out = tmp_path / FILE_NAME
    save(Manifest(project=ProjectInfo(name="Sponk é 日本")), out)
    first = out.read_bytes()
    assert first.startswith(b"schema_version = 1\n")
    assert b"\r\n" not in first
    assert "Sponk é 日本".encode() in first
    save(load(out), out)
    assert out.read_bytes() == first
    assert sorted(p.name for p in tmp_path.iterdir()) == [FILE_NAME]  # no temp or backup files


def test_save_writes_through_the_atomic_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed save must never leave a half-written ctstudio.toml (fsutil, ADR-014)."""
    from ctstudio.core.project import manifest_io

    written: list[Path] = []
    monkeypatch.setattr(manifest_io, "atomic_write_bytes", lambda p, _d: written.append(p))
    save(Manifest(project=ProjectInfo(name="X")), tmp_path / FILE_NAME)
    assert written == [tmp_path / FILE_NAME]
    assert not (tmp_path / FILE_NAME).exists()


def test_a_missing_blend_or_file_is_left_out_not_written_empty(tmp_path: Path) -> None:
    out = tmp_path / FILE_NAME
    save(Manifest(project=ProjectInfo(name="X")), out)
    data = tomllib.loads(out.read_text(encoding="utf-8"))
    assert "blend" not in data["project"]
    assert "file" not in data["components"]["kmp"]


def test_the_manifest_is_frozen_and_edited_with_replace() -> None:
    m = Manifest(project=ProjectInfo(name="X"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.project.name = "Y"  # type: ignore[misc]
    edited = dataclasses.replace(m, project=dataclasses.replace(m.project, slot="old_mario_gc"))
    assert edited.project.slot == "old_mario_gc"
    assert m.project.slot == "beginner_course"


UNKNOWN = """\
schema_version = 1
future_top = 7

[project]
name = "X"
colour = "red"

[components.course_model]
mode = "auto"
lod = 2

[components.course_model.textures."road.png"]
format = "CMPR"
sharpen = true

[components.objects]
library = "mine"

[future_table]
a = [1, 2]
"""


def test_unknown_keys_are_kept_and_written_back(tmp_path: Path) -> None:
    m = load(_write(tmp_path, UNKNOWN))
    assert m.extra == {"future_top": 7, "future_table": {"a": [1, 2]}}
    assert m.project.extra == {"colour": "red"}
    assert m.components.course_model.extra == {"lod": 2}
    assert m.components.course_model.textures["road.png"].extra == {"sharpen": True}
    assert m.components.extra == {"objects": {"library": "mine"}}
    out = tmp_path / FILE_NAME
    save(m, out)
    data = tomllib.loads(out.read_text(encoding="utf-8"))
    assert data["future_top"] == 7
    assert data["future_table"] == {"a": [1, 2]}
    assert data["project"]["colour"] == "red"
    assert data["components"]["course_model"]["lod"] == 2
    assert data["components"]["course_model"]["textures"]["road.png"]["sharpen"] is True
    assert data["components"]["objects"] == {"library": "mine"}
    assert load(out) == m


def test_each_unknown_key_is_logged_once_by_its_full_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="ctstudio.core.project.manifest_io"):
        load(_write(tmp_path, UNKNOWN))
    warned = sorted(r.getMessage() for r in caplog.records)
    assert warned == sorted(
        f"ctstudio.toml: unknown key '{key}' is kept as it is"
        for key in (
            "future_top",
            "future_table",
            "project.colour",
            "components.course_model.lod",
            'components.course_model.textures."road.png".sharpen',
            "components.objects",
        )
    )


def test_a_known_file_logs_no_warnings(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="ctstudio.core.project.manifest_io"):
        load(_write(tmp_path, SKETCH))
    assert caplog.records == []


def test_comments_are_not_kept_on_save(tmp_path: Path) -> None:
    """Documented in docs/user/PROJECT_FILE.md: tomli-w cannot write comments."""
    path = _write(tmp_path, SKETCH)
    save(load(path), path)
    assert "#" not in path.read_text(encoding="utf-8")


def test_override_tables_are_written_only_when_present(tmp_path: Path) -> None:
    out = tmp_path / FILE_NAME
    course = CourseModel(textures={"a.png": TextureOverride(mipmaps=0)})
    m = Manifest(project=ProjectInfo(name="X"))
    save(
        dataclasses.replace(m, components=dataclasses.replace(m.components, course_model=course)),
        out,
    )
    data = tomllib.loads(out.read_text(encoding="utf-8"))
    assert data["components"]["course_model"]["textures"] == {"a.png": {"mipmaps": 0}}
    assert "materials" not in data["components"]["course_model"]


def test_a_missing_file_says_which_folder(tmp_path: Path) -> None:
    with pytest.raises(ProjectError) as raised:
        load(tmp_path / FILE_NAME)
    assert raised.value.user_message == f"There is no ctstudio.toml in {tmp_path}."


def test_broken_toml_names_the_file_and_the_line(tmp_path: Path) -> None:
    path = _write(tmp_path, 'schema_version = 1\n[project]\nname = "X\n')
    with pytest.raises(ProjectError) as raised:
        load(path)
    message = raised.value.user_message
    assert message.startswith(f"{path} is not valid TOML: ")
    assert "line 3" in message


def test_a_file_that_is_not_utf8_is_a_project_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    path.write_bytes(b'schema_version = 1\n[project]\nname = "\xff"\n')
    with pytest.raises(ProjectError, match="is not valid TOML"):
        load(path)


def test_slots_are_the_42_original_track_and_arena_names() -> None:
    assert len(SLOTS) == len(set(SLOTS)) == 42
    assert SLOTS[0] == "beginner_course"
    assert {"old_koopa_64", "block_battle", "old_House_ds"} <= set(SLOTS)
