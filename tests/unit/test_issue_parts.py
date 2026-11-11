"""P5-T05a: which track part (dashboard card) a finding is about.

Lines are the measured real ``wszst check`` 2.42a output (the recording in
``tests/fakes/recordings/wszst/2.42a`` and, written out here, lines it printed for a
complete stand-in stage and for retail tracks, including a ``_d`` one); the rest are the
issues CT Studio's own steps make. Nothing here comes from a game file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.validation.issue_parts import part_of
from ctstudio.core.validation.issues import Issue
from ctstudio.core.validation.wszst_check import parse_check

pytestmark = pytest.mark.timeout(60)


def issue(component: str = "archive", *, file: Path | None = None, message: str = "x") -> Issue:
    return Issue("warning", component, "X", message, None, "test", file)


@pytest.mark.parametrize(
    ("found", "part"),
    [
        (issue("kcl"), "kcl"),  # the part's own id (stage, validate)
        (issue("objects"), "objects"),
        (issue(file=Path("map_model.brres")), "minimap"),  # one of its files
        (issue(file=Path("posteffect/posteffect.bblm")), "posteffect"),  # inside a folder part
        (issue("stage", file=Path("posteffect")), "posteffect"),  # the folder part itself
        (issue(file=Path("C:/Tracks/T/.ctstudio/stage/course.kcl")), "kcl"),  # absolute
        (issue("vrcorn_model"), "skybox"),  # "* CHECK BRRES:vrcorn_model.brres"
        (issue("course_d_model"), "course_model"),  # the model of a '_d' track
        (issue(file=Path("course_d_model.brres")), "course_model"),
        (issue("map_d_model"), "minimap"),  # not seen from Wiimm; the same rule for each model
        (issue("course_model_d"), None),  # not a name Wiimm uses
        (issue(file=Path("course_model_d.brres")), None),
        (issue("course_dmodel"), None),
        (issue("archive"), None),  # the whole track
        (issue("validate", file=Path("build/t.szs")), None),
        (issue("assemble", file=Path("ctstudio.toml")), None),
        (issue("kmpx", file=Path("course.kmpx")), None),  # not a near match
        (issue("castletree1"), None),  # an object's model: the whole track
    ],
)
def test_a_finding_belongs_to_the_part_it_names(found: Issue, part: str | None) -> None:
    assert part_of(found) == part


@pytest.mark.parametrize(
    ("message", "part"),
    [
        ("Optional file:   ./posteffect/posteffect.bblm", "posteffect"),
        ("Optional file:   ./posteffect/posteffect2.blight", "posteffect"),
        ("File 'vrcorn_model.brres' has 497 vertices in 1 MDL file.", "skybox"),
        ("File 'map_model.brres' has 3675 vertices in 1 MDL file.", "minimap"),
        ("Missing bones 'posLD' and 'posRU' in minimap MDL.", "minimap"),
        ("Track will only run at slot 6.1 (sherbet), because KCL uses 'ice.brres'.", "track_info"),
        (
            "Track will run at slot 4.2, because car+truck and all needed MDL materials",
            "track_info",
        ),
        ("Track will not run at slot 4.2, because of some missed MDL materials.", "track_info"),
        ("Track will also run at slot 6.1 (sherbet).", "track_info"),
        ("Track may run at slot 4.2, because car+truck are used.", "track_info"),
        ("Track most likely run at slot 4.2.", "track_info"),
        ("Track will not run at slots 3.1 and 7.1.", "track_info"),
        ("Old Track will run at slot 4.2", None),  # only a line that starts with "Track"
        ("Track will run at slot machines", None),  # a slot number must follow
        ("Additional file: ./course.bmm", None),  # extra files belong to no card
        ("Additional file: ./itembox.brres", None),
        ("Modified file:   ./itembox.brres", None),
        ("BREFT-IMG.IA8 58x52: Image size not power of 2: ./effect/quicksand/rk_x", None),
        ("Signature: WiimmSZS v2.42", None),
        ("The minimap model is fine", None),  # only Wiimm's "minimap MDL" wording counts
        ("Bones in myminimap MDLs", None),  # whole words only
        ("See ./posteffectx/a.bblm", None),
        ("See /course.kcl", None),  # Wiimm names archive files as "./name"
        ("See ./sub/posteffect/a.bblm", None),  # a folder part only at the top of the archive
        ("Additional file: ./slot_test.bin (will run at slot 4.2?)", None),  # not the slot line
    ],
)
def test_a_whole_archive_finding_goes_to_the_part_its_message_names(
    message: str, part: str | None
) -> None:
    assert part_of(issue(message=message)) == part


def test_only_findings_about_the_whole_archive_are_read_for_part_names() -> None:
    # CT Studio's own steps say which part they mean; a message naming a file is not enough
    said = "Track will only run at slot 4.2; see ./course.kcl and the minimap MDL"
    assert part_of(issue("assemble", message=said)) is None
    assert part_of(issue("archive", message=said)) == "track_info"
    with_file = issue("archive", file=Path("ctstudio.toml"), message="Optional file: ./course.kcl")
    assert part_of(with_file) is None  # a finding's own file decides first


def test_the_first_part_a_message_names_wins() -> None:
    said = "File 'vrcorn_model.brres' is bigger than ./course.kcl"
    assert part_of(issue(message=said)) == "skybox"
    assert part_of(issue(message="Additional file: ./x.brres, see ./course.kcl")) == "kcl"


def test_a_folder_named_like_a_part_above_the_project_does_not_count() -> None:
    root = Path("C:/mods/posteffect/Track1")
    inside = issue("validate", file=root / "build" / "castle_course.szs")
    toml = issue("assemble", file=root / "ctstudio.toml")
    assert (part_of(inside, root), part_of(toml, root)) == (None, None)
    staged = issue("stage", file=root / ".ctstudio" / "stage" / "posteffect" / "posteffect.bblm")
    assert part_of(staged, root) == "posteffect"
    deeper = issue("stage", file=root / ".ctstudio" / "stage" / "posteffect" / "sub" / "a.bin")
    assert part_of(deeper, root) == "posteffect"  # any folder below the project counts
    elsewhere = issue("assemble", file=Path("D:/posteffect/Other/ctstudio.toml"))
    assert part_of(elsewhere, root) is None  # outside the project: only its own folder counts
    own_folder = issue("assemble", file=Path("D:/Downloads/posteffect/posteffect.bblm"))
    assert part_of(own_folder, root) == "posteffect"
    project_named_posteffect = Path("C:/mods/posteffect")
    toml_there = issue("assemble", file=project_named_posteffect / "ctstudio.toml")
    assert part_of(toml_there, project_named_posteffect) is None


def test_a_real_check_of_a_complete_stand_in_stage_lands_on_the_right_cards() -> None:
    found = parse_check(STAND_IN, Path("stage"), exit_code=2)
    assert [(i.message[:24], part_of(i)) for i in found] == [
        ("Signature: WiimmSZS v2.4", "kcl"),
        ("Invalid link to not exis", "kmp"),
        ("Invalid link to not exis", "kmp"),
        ("Missing a camera with ty", "kmp"),
        ("Self linked item route.", "kmp"),
        ("Optional file:   ./poste", "posteffect"),
        ("Additional file: ./itemb", None),
        ("Modified file:   ./itemb", None),
        ("Missing bones 'posLD' an", "minimap"),
    ]


def test_a_real_d_track_s_model_findings_land_on_the_course_model_card() -> None:
    found = parse_check(D_TRACK, Path("castle_course_d.szs"), exit_code=2)
    assert [part_of(i) for i in found] == ["course_model", "course_model", "skybox", None]


STAND_IN = """CHECK U8:stage
* CHECK KCL:stage/course.kcl
    * INFO: Signature: WiimmSZS v2.42
* CHECK KMP:stage/course.kmp
  > All indices are zero based!
  > Section CAME, header
    + WARNING: Invalid link to not existing opening camera #0 (max=#-1).
    + WARNING: Invalid link to not existing selection camera #0 (max=#-1).
  > Section CAME
    - HINT: Missing a camera with type 0.
  > Section ITPH, Item route group #0 of 1
    - HINT: Self linked item route.
* CHECK U8:stage
    - HINT: Optional file:   ./posteffect/posteffect.bblm
    - HINT: Additional file: ./itembox.brres
    - HINT: Modified file:   ./itembox.brres
    + WARNING: Missing bones 'posLD' and 'posRU' in minimap MDL.
 => 3 warnings, 5 hints and 1 info for U8:stage
"""

D_TRACK = """CHECK YAZ0.U8:castle_course_d.szs
* CHECK BRRES:course_d_model.brres
    + WARNING: TEX v2 (2 sections) will freeze track: Textures(NW4R)/t_road_a
    + WARNING: TEX v2 (2 sections) will freeze track: Textures(NW4R)/t_road_b
* CHECK YAZ0.U8:castle_course_d.szs
    * INFO: File 'vrcorn_model.brres' has 382 vertices in 1 MDL file.
    - HINT: Additional file: ./course.bmm
 => 2 warnings, 1 hint and 1 info for YAZ0.U8:castle_course_d.szs
"""
