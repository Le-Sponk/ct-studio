"""P3-T03: the component registry — one declarative definition per track part.

Every part of a track file CT Studio manages (course model, collision, minimap, skybox,
course data, post-effects, objects, track info) is described once here, and the rest of the
app reads these definitions instead of hard-coding names, files, modes or tools.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS, ComponentSpec
from ctstudio.core.project import manifest as m
from ctstudio.core.tools.registry import TOOL_BY_ID

pytestmark = pytest.mark.timeout(30)

IDS = (
    "course_model",
    "kcl",
    "minimap",
    "skybox",
    "kmp",
    "posteffect",
    "objects",
    "track_info",
)
# Names a newcomer would not know; they belong in the wiki link, not the one-line description.
JARGON = re.compile(
    r"\b(BRRES|KCL|KMP|SZS|U8|MDL0|TEX0|Yaz0|vrcorn|posLD|posRU|wszst|wkclt|ABMatt|rszst|"
    r"RiiStudio|DAE|manifest|stage|node)\b",
    re.IGNORECASE,
)


def test_the_eight_parts_in_dashboard_order() -> None:
    assert tuple(c.id for c in COMPONENTS) == IDS
    assert set(COMPONENT_BY_ID) == set(IDS)
    assert all(COMPONENT_BY_ID[c.id] is c for c in COMPONENTS)


def test_specs_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        COMPONENTS[0].required = False  # type: ignore[misc]


def test_display_names_are_unique_and_short() -> None:
    names = [c.name for c in COMPONENTS]
    assert len(set(names)) == len(names)
    assert all(0 < len(name) <= 20 for name in names)


@pytest.mark.parametrize("spec", COMPONENTS, ids=lambda c: c.id)
def test_each_description_is_one_plain_sentence(spec: ComponentSpec) -> None:
    text = spec.description
    assert text[0].isupper()
    assert text.endswith(".")
    assert text.count(".") == 1, "one sentence"
    assert 30 <= len(text) <= 120
    assert not JARGON.search(text), JARGON.search(text)


@pytest.mark.parametrize("spec", COMPONENTS, ids=lambda c: c.id)
def test_each_part_links_to_its_mkwiiki_page(spec: ComponentSpec) -> None:
    assert re.fullmatch(r"https://mkwiiki\.org/wiki/[A-Za-z0-9_.()#-]+", spec.wiki)


def test_the_wiki_pages_are_the_ones_checked_to_exist() -> None:
    """Each page was opened on 2026-11-02; the plain names (e.g. ``Skybox``) do not exist."""
    assert {c.id: c.wiki.removeprefix("https://mkwiiki.org/wiki/") for c in COMPONENTS} == {
        "course_model": "Creating_a_BRRES_with_RiiStudio",
        "kcl": "KCL",
        "minimap": "Creating_a_Minimap",
        "skybox": "Custom_Track_Tutorial#Overview_of_a_Custom_Track_File",
        "kmp": "KMP",
        "posteffect": "Post-effects",
        "objects": "Object",
        "track_info": "Slot",
    }


def test_stage_outputs_are_the_files_every_track_needs() -> None:
    assert {c.id: c.outputs for c in COMPONENTS} == {
        "course_model": ("course_model.brres",),
        "kcl": ("course.kcl",),
        "minimap": ("map_model.brres",),
        "skybox": ("vrcorn_model.brres",),
        "kmp": ("course.kmp",),
        "posteffect": ("posteffect/",),
        "objects": (),  # added by Wiimms auto-add while the track is assembled
        "track_info": (),  # settings only: name, slot, credits
    }


def _overlaps(a: str, b: str) -> bool:
    if a == b:
        return True
    return (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b))


def test_no_two_parts_write_the_same_file_or_into_each_others_folder() -> None:
    owned = [(c.id, out) for c in COMPONENTS for out in c.outputs]
    for i, (id_a, a) in enumerate(owned):
        for id_b, b in owned[i + 1 :]:
            assert not _overlaps(a, b), (id_a, a, id_b, b)


@pytest.mark.parametrize(
    ("a", "b", "clash"),
    [
        ("course.kcl", "course.kcl", True),
        ("posteffect/", "posteffect/posteffect.blight", True),
        ("posteffect/x", "posteffect/", True),
        ("course.kcl", "course.kmp", False),
        ("posteffect/", "posteffect.bfg", False),
    ],
)
def test_the_overlap_check_itself(a: str, b: str, clash: bool) -> None:
    assert _overlaps(a, b) is clash


def test_outputs_are_plain_relative_names_with_forward_slashes() -> None:
    for c in COMPONENTS:
        for out in c.outputs:
            assert re.fullmatch(r"[a-z_]+(\.[a-z]+|/)", out), out


def test_the_parts_a_track_cannot_load_without_are_required() -> None:
    """The Custom Track Tutorial's list of files a track needs, plus the track's own info."""
    assert {c.id for c in COMPONENTS if c.required} == set(IDS) - {"objects"}


@pytest.mark.parametrize(
    ("component", "manifest_modes"),
    [
        ("course_model", m.GENERATED_MODES),
        ("kcl", m.GENERATED_MODES),
        ("minimap", m.GENERATED_MODES),
        ("skybox", m.SKYBOX_MODES),
        ("kmp", m.KMP_MODES),
        ("posteffect", m.POSTEFFECT_MODES),
    ],
)
def test_modes_and_default_match_what_ctstudio_toml_allows(
    component: str, manifest_modes: tuple[str, ...]
) -> None:
    spec = COMPONENT_BY_ID[component]
    assert spec.modes == manifest_modes
    assert spec.manifest_table == component
    default = getattr(m.Components(), component).mode
    assert spec.default_mode == default == spec.modes[0]


def test_parts_without_a_ctstudio_toml_table_say_so() -> None:
    assert COMPONENT_BY_ID["objects"].manifest_table is None
    assert COMPONENT_BY_ID["track_info"].manifest_table == "project"
    assert COMPONENT_BY_ID["objects"].modes == ("auto",)
    assert COMPONENT_BY_ID["track_info"].modes == ("manual",)


def test_every_mode_lists_its_tools_and_every_tool_exists() -> None:
    for c in COMPONENTS:
        assert set(c.tools) == set(c.modes), c.id
        for mode, tools in c.tools.items():
            assert len(set(tools)) == len(tools), (c.id, mode)
            for tool in tools:
                assert tool in TOOL_BY_ID, (c.id, mode, tool)


def test_tools_needed_per_mode() -> None:
    assert {(c.id, mode): tools for c in COMPONENTS for mode, tools in c.tools.items()} == {
        ("course_model", "auto"): ("blender", "rszst", "abmatt", "wimgt"),
        ("course_model", "manual"): (),
        ("kcl", "auto"): ("blender", "wkclt"),
        ("kcl", "manual"): (),
        ("minimap", "auto"): ("wkclt", "abmatt", "wszst"),
        ("minimap", "manual"): (),
        ("skybox", "auto"): ("blender", "rszst", "abmatt", "wimgt"),
        ("skybox", "template"): ("wszst",),
        ("skybox", "manual"): (),
        ("kmp", "manual"): (),
        ("posteffect", "template"): ("wszst",),
        ("posteffect", "manual"): (),
        ("objects", "auto"): ("wszst",),
        ("track_info", "manual"): (),
    }


def test_tools_for_a_mode_the_part_does_not_have_is_an_error() -> None:
    with pytest.raises(KeyError):
        COMPONENT_BY_ID["kmp"].tools_for("auto")
    assert COMPONENT_BY_ID["kcl"].tools_for("auto") == ("blender", "wkclt")


def test_a_spec_must_offer_modes_once_each_with_tools_for_every_mode() -> None:
    spec = COMPONENT_BY_ID["kmp"]
    with pytest.raises(ValueError, match="kmp: needs at least one mode, each listed once"):
        dataclasses.replace(spec, modes=(), tools={})
    with pytest.raises(ValueError, match="kmp: needs at least one mode, each listed once"):
        dataclasses.replace(spec, modes=("manual", "manual"))
    with pytest.raises(ValueError, match=r"kmp: tools must list exactly the modes \('manual',\)"):
        dataclasses.replace(spec, tools={})
    with pytest.raises(ValueError, match="kmp: tools must list exactly the modes"):
        dataclasses.replace(spec, tools={"manual": (), "auto": ("wszst",)})  # a mode it lacks
