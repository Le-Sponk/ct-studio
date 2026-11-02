"""Load and save ``ctstudio.toml`` (P3-T01).

``load`` reads the file, upgrades an older schema (``migrations``), checks every value and
returns a ``Manifest``; it never writes. ``save`` writes the whole file atomically. Keys this
version does not know are kept in each table's ``extra``, written back on save, and logged
once each as a warning. Comments are not kept: the TOML writer (tomli-w, ADR-020) cannot
write them (docs/user/PROJECT_FILE.md).
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import cast

import tomli_w

from ctstudio.core.errors import ManifestError, ProjectError
from ctstudio.core.fsutil import atomic_write_bytes
from ctstudio.core.project import manifest as m
from ctstudio.core.project import migrations
from ctstudio.core.project.slots import DEFAULT_SLOT, SLOTS
from ctstudio.core.project.toml_table import Table, show

FILE_NAME = "ctstudio.toml"

_LOG = logging.getLogger(__name__)
_SLOT = 'the file name of an original track or arena, such as "beginner_course" or "old_mario_gc"'


def load(path: Path) -> m.Manifest:
    """The manifest in ``path``; ``ProjectError``/``ManifestError`` explain what is wrong."""
    data = _read(path)
    unknown: list[str] = []
    top = Table(migrations.upgrade(_versioned(data)), "", unknown)
    manifest = _manifest(top)
    for key in unknown:
        _LOG.warning("ctstudio.toml: unknown key '%s' is kept as it is", key)
    return manifest


def save(manifest: m.Manifest, path: Path) -> None:
    """Write ``manifest`` to ``path`` in one step (no half-written file on failure)."""
    atomic_write_bytes(path, tomli_w.dumps(_plain(manifest)).encode("utf-8"))


def _read(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise ProjectError(
            f"There is no {FILE_NAME} in {path.parent}.",
            hint="Open the folder that holds the project, or create a new project.",
        ) from exc
    except OSError as exc:
        raise ProjectError(f"{path} cannot be read.", details=str(exc)) from exc
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        reason = "it is not UTF-8 text" if isinstance(exc, UnicodeDecodeError) else str(exc)
        raise ProjectError(
            f"{path} is not valid TOML: {reason}.",
            hint=f"Fix that line in {FILE_NAME} with a text editor, then open the project again.",
        ) from exc


def _versioned(data: dict[str, object]) -> dict[str, object]:
    """``data`` after checking ``schema_version`` is one this CT Studio can read."""
    version = data.get("schema_version")
    if version is None:
        raise ManifestError(
            "schema_version", "missing; expected schema_version = 1 at the top of the file"
        )
    if isinstance(version, bool) or not isinstance(version, int):
        raise ManifestError("schema_version", f"expected a whole number; found {show(version)}")
    if version > migrations.CURRENT:
        raise ManifestError(
            "schema_version",
            f"this project was saved by a newer CT Studio (file version {version}; this CT"
            f" Studio reads up to {migrations.CURRENT}). Update CT Studio to open it",
        )
    if version < migrations.oldest_readable():
        raise ManifestError("schema_version", f"CT Studio cannot upgrade a version {version} file")
    return data


def _manifest(top: Table) -> m.Manifest:
    top.known("schema_version")  # checked by _versioned
    if "project" not in top.data:
        raise top.fail(
            "project",
            'missing; every project needs a [project] table with a name, such as name = "My Track"',
        )
    project = _project(top.table("project"))
    build = _build(top.table("build"))
    blender = _blender(top.table("blender"))
    components = _components(top.table("components"))
    hooks_table = top.table("hooks")
    hooks = m.Hooks(
        hooks_table.text("post_stage", ""),
        hooks_table.text("post_build", ""),
        hooks_table.rest(),
    )
    return m.Manifest(project, migrations.CURRENT, build, blender, components, hooks, top.rest())


def _project(t: Table) -> m.ProjectInfo:
    if "name" not in t.data:
        raise t.fail("name", "missing; every project needs a name")
    return m.ProjectInfo(
        name=t.text("name", "", empty_ok=False),
        author=t.text("author", ""),
        version=t.text("version", "1.0"),
        slot=t.member("slot", SLOTS, DEFAULT_SLOT, _SLOT),
        blend=t.optional_text("blend"),
        extra=t.rest(),
    )


def _build(t: Table) -> m.BuildSettings:
    return m.BuildSettings(
        test_compression=t.choice("test_compression", m.COMPRESSIONS, "fast"),
        release_compression=t.choice("release_compression", m.COMPRESSIONS, "best"),
        make_d_variant=t.flag("make_d_variant", True),
        auto_add=t.flag("auto_add", True),
        extra_wszst_args=t.texts("extra_wszst_args", ()),
        extra=t.rest(),
    )


def _blender(t: Table) -> m.BlenderSettings:
    c = t.table("collections")
    collections = m.BlenderCollections(
        course=c.text("course", "Course"),
        kcl=c.text("kcl", "KCL"),
        skybox=c.text("skybox", "Skybox"),
        minimap=c.text("minimap", ""),
        extra=c.rest(),
    )
    return m.BlenderSettings(collections, t.rest())


def _components(t: Table) -> m.Components:
    return m.Components(
        course_model=_course_model(t.table("course_model")),
        kcl=_kcl(t.table("kcl")),
        minimap=_minimap(t.table("minimap")),
        kmp=_kmp(t.table("kmp")),
        skybox=_skybox(t.table("skybox")),
        posteffect=_posteffect(t.table("posteffect")),
        extra=t.rest(),
    )


def _course_model(t: Table) -> m.CourseModel:
    return m.CourseModel(
        mode=t.choice("mode", m.GENERATED_MODES, "auto"),
        file=t.optional_text("file"),
        backend=t.choice("backend", m.BACKENDS, "default"),
        extra_import_args=t.texts("extra_import_args", ()),
        post_import_commands=t.text("post_import_commands", ""),
        textures={name: _texture(e) for name, e in t.named("textures").items()},
        materials={name: _material(e) for name, e in t.named("materials").items()},
        extra=t.rest(),
    )


def _texture(t: Table) -> m.TextureOverride:
    return m.TextureOverride(
        format=t.optional_choice("format", m.TEXTURE_FORMATS),
        mipmaps=t.whole("mipmaps", 0, m.MAX_MIPMAPS),
        extra=t.rest(),
    )


def _material(t: Table) -> m.MaterialOverride:
    return m.MaterialOverride(
        transparency=t.optional_choice("transparency", m.TRANSPARENCIES),
        cull=t.optional_choice("cull", m.CULLS),
        extra=t.rest(),
    )


def _kcl(t: Table) -> m.Kcl:
    return m.Kcl(
        mode=t.choice("mode", m.GENERATED_MODES, "auto"),
        file=t.optional_text("file"),
        unbean=t.text("unbean", "lower"),
        extra=t.rest(),
    )


def _minimap(t: Table) -> m.Minimap:
    return m.Minimap(
        mode=t.choice("mode", m.GENERATED_MODES, "auto"),
        file=t.optional_text("file"),
        source=t.choice("source", m.MINIMAP_SOURCES, "kcl"),
        include_kcl_types=t.texts("include_kcl_types", m.MINIMAP_KCL_TYPES),
        extra=t.rest(),
    )


def _kmp(t: Table) -> m.Kmp:
    return m.Kmp(
        mode=t.choice("mode", m.KMP_MODES, "manual"),
        file=t.optional_text("file"),
        editor=t.choice("editor", m.KMP_EDITORS, "lorenzi"),
        extra=t.rest(),
    )


def _skybox(t: Table) -> m.Skybox:
    return m.Skybox(t.choice("mode", m.GENERATED_MODES, "auto"), t.optional_text("file"), t.rest())


def _posteffect(t: Table) -> m.Posteffect:
    return m.Posteffect(
        mode=t.choice("mode", m.POSTEFFECT_MODES, "template"),
        file=t.optional_text("file"),
        template_track=t.member("template_track", SLOTS, DEFAULT_SLOT, _SLOT),
        extra=t.rest(),
    )


def _plain(obj: object) -> dict[str, object]:
    """A dataclass as TOML data: ``None`` and empty override tables left out, ``extra`` last.

    tomli-w writes plain values before tables, so ``schema_version`` comes first in the file.
    """
    out: dict[str, object] = {}
    extra: Mapping[str, object] = {}
    for f in fields(cast("m.Manifest", obj)):
        value: object = getattr(obj, f.name)
        if f.name == "extra":
            extra = cast("Mapping[str, object]", value)
        elif is_dataclass(value):
            out[f.name] = _plain(value)
        elif isinstance(value, Mapping):
            entries = cast("Mapping[str, object]", value)
            if entries:
                out[f.name] = {name: _plain(entry) for name, entry in entries.items()}
        elif value is not None:
            out[f.name] = value
    return {**out, **extra}
