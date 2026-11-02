"""The project manifest ``ctstudio.toml`` as frozen dataclasses (P3-T01, ARCHITECTURE §6).

Snapshots are immutable: edit with ``dataclasses.replace`` and save the new snapshot
(``manifest_io.save``). Every table keeps the keys this version does not know in ``extra``,
so a file written by a newer CT Studio (or edited by hand) loses nothing on save.
Optional values are ``None`` when the file leaves them out; override tables
(``textures``/``materials``) hold only what the user chose to override.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from ctstudio.core.project.slots import DEFAULT_SLOT

SCHEMA_VERSION = 1

type Compression = Literal["best", "fast", "none"]
type GeneratedMode = Literal["auto", "manual"]
type KmpMode = Literal["manual"]
type PosteffectMode = Literal["template", "manual"]
type Backend = Literal["default", "rszst", "abmatt"]
type MinimapSource = Literal["kcl", "blender", "file"]
type KmpEditor = Literal["lorenzi", "kmp_cloud"]
type TextureFormat = Literal[
    "CMPR", "RGB5A3", "RGBA32", "RGB565", "IA8", "IA4", "I8", "I4", "C4", "C8", "C14X2"
]
type Transparency = Literal["auto", "opaque", "cutout", "translucent"]
type Cull = Literal["front", "back", "none"]

COMPRESSIONS: tuple[Compression, ...] = ("best", "fast", "none")
GENERATED_MODES: tuple[GeneratedMode, ...] = ("auto", "manual")
KMP_MODES: tuple[KmpMode, ...] = ("manual",)
POSTEFFECT_MODES: tuple[PosteffectMode, ...] = ("template", "manual")
BACKENDS: tuple[Backend, ...] = ("default", "rszst", "abmatt")
MINIMAP_SOURCES: tuple[MinimapSource, ...] = ("kcl", "blender", "file")
KMP_EDITORS: tuple[KmpEditor, ...] = ("lorenzi", "kmp_cloud")
TEXTURE_FORMATS: tuple[TextureFormat, ...] = (
    "CMPR", "RGB5A3", "RGBA32", "RGB565", "IA8", "IA4", "I8", "I4", "C4", "C8", "C14X2"
)  # fmt: skip
TRANSPARENCIES: tuple[Transparency, ...] = ("auto", "opaque", "cutout", "translucent")
CULLS: tuple[Cull, ...] = ("front", "back", "none")
MAX_MIPMAPS = 10

MINIMAP_KCL_TYPES = ("road", "slippery_road", "boost_panel", "boost_ramp", "jump_pad")


def _extra() -> Mapping[str, object]:
    return {}


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    author: str = ""
    version: str = "1.0"
    slot: str = DEFAULT_SLOT
    blend: str | None = None  # relative to the project folder when inside it
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class BuildSettings:
    test_compression: Compression = "fast"
    release_compression: Compression = "best"
    make_d_variant: bool = True
    auto_add: bool = True
    extra_wszst_args: tuple[str, ...] = ()
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class BlenderCollections:
    """Blender collection name per part; empty means "not in Blender" (minimap: from KCL)."""

    course: str = "Course"
    kcl: str = "KCL"
    skybox: str = "Skybox"
    minimap: str = ""
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class BlenderSettings:
    collections: BlenderCollections = field(default_factory=BlenderCollections)
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class TextureOverride:
    format: TextureFormat | None = None
    mipmaps: int | None = None
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class MaterialOverride:
    transparency: Transparency | None = None
    cull: Cull | None = None
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class CourseModel:
    mode: GeneratedMode = "auto"
    file: str | None = None
    backend: Backend = "default"
    extra_import_args: tuple[str, ...] = ()
    post_import_commands: str = ""
    textures: Mapping[str, TextureOverride] = field(default_factory=lambda: {})
    materials: Mapping[str, MaterialOverride] = field(default_factory=lambda: {})
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class Kcl:
    mode: GeneratedMode = "auto"
    file: str | None = None
    unbean: str = "lower"  # passed through to the Blender add-on's KCL exporter
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class Minimap:
    mode: GeneratedMode = "auto"
    file: str | None = None
    source: MinimapSource = "kcl"
    include_kcl_types: tuple[str, ...] = MINIMAP_KCL_TYPES
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class Kmp:
    mode: KmpMode = "manual"
    file: str | None = None
    editor: KmpEditor = "lorenzi"
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class Skybox:
    mode: GeneratedMode = "auto"
    file: str | None = None
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class Posteffect:
    mode: PosteffectMode = "template"
    file: str | None = None
    template_track: str = DEFAULT_SLOT
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class Components:
    course_model: CourseModel = field(default_factory=CourseModel)
    kcl: Kcl = field(default_factory=Kcl)
    minimap: Minimap = field(default_factory=Minimap)
    kmp: Kmp = field(default_factory=Kmp)
    skybox: Skybox = field(default_factory=Skybox)
    posteffect: Posteffect = field(default_factory=Posteffect)
    extra: Mapping[str, object] = field(default_factory=_extra)  # components added later


@dataclass(frozen=True)
class Hooks:
    post_stage: str = ""
    post_build: str = ""
    extra: Mapping[str, object] = field(default_factory=_extra)


@dataclass(frozen=True)
class Manifest:
    project: ProjectInfo
    schema_version: int = SCHEMA_VERSION
    build: BuildSettings = field(default_factory=BuildSettings)
    blender: BlenderSettings = field(default_factory=BlenderSettings)
    components: Components = field(default_factory=Components)
    hooks: Hooks = field(default_factory=Hooks)
    extra: Mapping[str, object] = field(default_factory=_extra)
