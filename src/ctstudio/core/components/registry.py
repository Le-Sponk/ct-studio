"""The track parts CT Studio manages, each described once (P3-T03, ARCHITECTURE §4).

A ``ComponentSpec`` says what a part is (name, one plain sentence, mkwiiki.org page), how it
can be made (modes, default first), which files it puts into the track (stage outputs; a
trailing ``/`` marks a folder), whether a track needs it, and which tools each mode uses
(ids from ``core.tools.registry``). Modes come from the manifest's own tuples so the two can
never disagree. Status, build and GUI code read these definitions instead of hard-coding them.

Wiki pages were each opened on 2026-11-02; mkwiiki.org has no page for the skybox, so it
links to the tutorial's overview of a track's files.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ctstudio.core.formats.magic import FileKind
from ctstudio.core.project import manifest as m

_WIKI = "https://mkwiiki.org/wiki/"
_BRRES_TOOLS = ("blender", "rszst", "abmatt", "wimgt")  # export, import, materials, textures


@dataclass(frozen=True)
class ComponentSpec:
    id: str
    name: str
    description: str
    wiki: str
    modes: tuple[str, ...]
    outputs: tuple[str, ...]
    required: bool
    tools: Mapping[str, tuple[str, ...]]
    manifest_table: str | None  # [components.<id>], "project", or None (no settings)
    kind: FileKind | None = None  # what a supplied file must be; None: a folder or no file

    def __post_init__(self) -> None:
        if not self.modes or len(set(self.modes)) != len(self.modes):
            raise ValueError(f"{self.id}: needs at least one mode, each listed once")
        if set(self.tools) != set(self.modes):
            raise ValueError(f"{self.id}: tools must list exactly the modes {self.modes}")

    @property
    def default_mode(self) -> str:
        """The first mode listed (the manifest's default for this part)."""
        return self.modes[0]

    def tools_for(self, mode: str) -> tuple[str, ...]:
        return self.tools[mode]


def _spec(
    component_id: str,
    name: str,
    description: str,
    page: str,
    outputs: tuple[str, ...],
    tools: dict[str, tuple[str, ...]],
    *,
    modes: tuple[str, ...],
    required: bool = True,
    table: str | None = "component",
    kind: FileKind | None = None,
) -> ComponentSpec:
    return ComponentSpec(
        id=component_id,
        name=name,
        description=description,
        wiki=_WIKI + page,
        modes=modes,
        outputs=outputs,
        required=required,
        tools=MappingProxyType(tools),
        manifest_table=component_id if table == "component" else table,
        kind=kind,
    )


COMPONENTS: tuple[ComponentSpec, ...] = (
    _spec(
        "course_model",
        "Course model",
        "The track you see: its shapes, textures and materials.",
        "Creating_a_BRRES_with_RiiStudio",
        ("course_model.brres",),
        {"auto": _BRRES_TOOLS, "manual": ()},
        modes=m.GENERATED_MODES,
        kind=FileKind.BRRES,
    ),
    _spec(
        "kcl",
        "Collision",
        "What karts can drive on, where the walls and boost pads are, and where you fall off.",
        "KCL",
        ("course.kcl",),
        {"auto": ("blender", "wkclt"), "manual": ()},
        modes=m.GENERATED_MODES,
        kind=FileKind.KCL,
    ),
    _spec(
        "minimap",
        "Minimap",
        "The small top-down map of the track shown during a race.",
        "Creating_a_Minimap",
        ("map_model.brres",),
        {"auto": ("wkclt", "abmatt", "wszst"), "manual": ()},
        modes=m.GENERATED_MODES,
        kind=FileKind.BRRES,
    ),
    _spec(
        "skybox",
        "Skybox",
        "The background around the track, usually the sky.",
        "Custom_Track_Tutorial#Overview_of_a_Custom_Track_File",
        ("vrcorn_model.brres",),
        {"auto": _BRRES_TOOLS, "template": ("wszst",), "manual": ()},
        modes=m.SKYBOX_MODES,
        kind=FileKind.BRRES,
    ),
    _spec(
        "kmp",
        "Course data",
        "Start positions, checkpoints, item boxes, CPU routes, cameras and object placement.",
        "KMP",
        ("course.kmp",),
        {"manual": ()},
        modes=m.KMP_MODES,
        kind=FileKind.KMP,
    ),
    _spec(
        "posteffect",
        "Post-effects",
        "The track's lighting, fog, glow and bloom.",
        "Post-effects",
        ("posteffect/",),
        {"template": ("wszst",), "manual": ()},
        modes=m.POSTEFFECT_MODES,
    ),
    _spec(
        "objects",
        "Objects",
        "The files for trees, item boxes and other objects that the course data places.",
        "Object",
        (),
        {"auto": ("wszst",)},
        modes=("auto",),
        required=False,
        table=None,
    ),
    _spec(
        "track_info",
        "Track info",
        "The track's name, author and which original track it replaces.",
        "Slot",
        (),
        {"manual": ()},
        modes=("manual",),
        table="project",
    ),
)

COMPONENT_BY_ID: Mapping[str, ComponentSpec] = MappingProxyType({c.id: c for c in COMPONENTS})
