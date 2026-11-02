"""P3-T06: the 42 original tracks and arenas, generated from recorded ``wstrt`` output.

``slots.json`` must be exactly what ``scripts/make_slot_catalogue.py`` makes from the committed
recording, so nobody types track names by hand. The loader checks the file again at start-up.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ctstudio.core.project import slots
from ctstudio.core.project.slots import (
    CATALOGUE,
    DEFAULT_SLOT,
    SLOTS,
    CatalogueError,
    Slot,
    UnknownSlot,
    arenas,
    cups,
    find,
    race_tracks,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import make_slot_catalogue as msc  # scripts added to sys.path above; E402 disabled project-wide

RACE_CUPS = (
    "Mushroom Cup",
    "Flower Cup",
    "Star Cup",
    "Special Cup",
    "Shell Cup",
    "Banana Cup",
    "Leaf Cup",
    "Lightning Cup",
)


def _data() -> dict[str, Any]:
    return json.loads(slots.CATALOGUE_PATH.read_text(encoding="utf-8"))


# --- acceptance ---------------------------------------------------------------------------


def test_there_are_32_race_tracks_and_10_arenas() -> None:
    assert len(race_tracks()) == 32
    assert len(arenas()) == 10
    assert len(CATALOGUE) == len(SLOTS) == 42


def test_luigi_circuit_is_the_first_track_and_the_default() -> None:
    first = find("beginner_course")
    assert first == Slot(
        file="beginner_course",
        name="Luigi Circuit",
        abbr="LC",
        kind="race",
        cup="Mushroom Cup",
        cup_number=1,
        position=1,
    )
    assert DEFAULT_SLOT == "beginner_course" == SLOTS[0]
    assert first.label == "Luigi Circuit (Mushroom Cup, track 1)"


def test_the_committed_file_is_exactly_what_the_script_makes_from_the_recording() -> None:
    expected = msc.render(msc.build(msc.load_recording(msc.RECORDING)))
    assert slots.CATALOGUE_PATH.read_text(encoding="utf-8") == expected, (
        "run: uv run python scripts/make_slot_catalogue.py"
    )


# --- order and grouping ---------------------------------------------------------------------


def test_the_game_order_is_kept() -> None:
    assert SLOTS[:4] == ("beginner_course", "farm_course", "kinoko_course", "factory_course")
    assert SLOTS[15] == "rainbow_course"
    assert SLOTS[16] == "old_peach_gc"
    assert SLOTS[31] == "old_koopa_64"
    assert SLOTS[32:] == (
        "block_battle",
        "venice_battle",
        "skate_battle",
        "casino_battle",
        "sand_battle",
        "old_battle4_sfc",
        "old_battle3_gba",
        "old_matenro_64",
        "old_CookieLand_gc",
        "old_House_ds",
    )
    assert SLOTS == tuple(s.file for s in CATALOGUE)


def test_eight_cups_of_four_tracks_then_two_arena_groups_of_five() -> None:
    groups = cups()
    assert tuple(groups) == (*RACE_CUPS, "Wii Arenas", "Retro Arenas")
    for number, name in enumerate(RACE_CUPS, start=1):
        members = groups[name]
        assert [s.position for s in members] == [1, 2, 3, 4]
        assert {s.cup_number for s in members} == {number}
        assert {s.kind for s in members} == {"race"}
    for number, name in enumerate(("Wii Arenas", "Retro Arenas"), start=1):
        members = groups[name]
        assert [s.position for s in members] == [1, 2, 3, 4, 5]
        assert {(s.kind, s.cup_number) for s in members} == {("arena", number)}


@pytest.mark.parametrize(
    ("file", "name", "cup", "position"),
    [
        ("castle_course", "Mario Circuit", "Flower Cup", 1),
        ("volcano_course", "Grumble Volcano", "Star Cup", 4),
        ("old_obake_sfc", "SNES Ghost Valley 2", "Shell Cup", 3),
        ("old_mario_gc", "GCN Mario Circuit", "Leaf Cup", 4),
        ("old_koopa_64", "N64 Bowser's Castle", "Lightning Cup", 4),
        ("sand_battle", "Thwomp Desert", "Wii Arenas", 5),
        ("old_House_ds", "DS Twilight House", "Retro Arenas", 5),
    ],
)
def test_known_tracks_land_in_the_right_cup(file: str, name: str, cup: str, position: int) -> None:
    found = find(file)
    assert (found.name, found.cup, found.position) == (name, cup, position)


def test_every_way_of_naming_a_track_is_unique() -> None:
    keys = [k.casefold() for s in CATALOGUE for k in {s.file, s.name, s.abbr}]
    assert len(keys) == len(set(keys))


# --- lookups ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text", ["beginner_course", "Luigi Circuit", "luigi circuit", "LC", "lc", "  LC  "]
)
def test_a_track_can_be_found_by_file_name_display_name_or_abbreviation(text: str) -> None:
    assert find(text).file == "beginner_course"


def test_an_unknown_track_suggests_the_closest_ones() -> None:
    with pytest.raises(UnknownSlot, match=r"'begginer_course'.*beginner_course \(Luigi Circuit\)"):
        find("begginer_course")
    with pytest.raises(UnknownSlot, match=r"Moonview Highway"):
        find("moonveiw highway")


def test_an_unknown_track_with_nothing_close_says_how_to_list_them() -> None:
    with pytest.raises(UnknownSlot, match=r"'zzz' is not an original track or arena") as info:
        find("zzz")
    message = str(info.value)
    assert "Did you mean" not in message
    assert "beginner_course" in message and "Luigi Circuit" in message and "LC" in message


def test_an_unknown_track_is_a_value_error() -> None:
    assert issubclass(UnknownSlot, ValueError)


# --- loader checks ------------------------------------------------------------------------------


def _break(change: Any) -> dict[str, Any]:
    data = copy.deepcopy(_data())
    change(data)
    return data


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["slots"].pop(), r"32 race tracks and 10 arenas"),
        (lambda d: d["slots"].pop(0), r"32 race tracks and 10 arenas"),
        (lambda d: d["slots"][1].update(file="beginner_course"), r"beginner_course.*twice"),
        (lambda d: d["slots"][2].update(name="Luigi Circuit"), r"Luigi Circuit.*twice"),
        (lambda d: d["slots"][2].update(abbr="lc"), r"lc.*twice"),
        (lambda d: d["slots"][0].update(kind="battle"), r"kind.*'battle'"),
        (lambda d: d["slots"][0].update(position="1"), r"position"),
        (lambda d: d["slots"][0].update(cup_number=True), r"cup_number"),
        (lambda d: d["slots"][0].pop("cup"), r"slot 1: missing cup$"),
        (lambda d: d["slots"][0].update(extra=1), r"slot 1: unknown extra$"),
        (
            lambda d: d["slots"][0].pop("abbr") and d["slots"][0].update(x=1),
            r"missing abbr; unknown x",
        ),
        (lambda d: d["slots"][0].update(name=""), r"name"),
        (lambda d: d.update(slots={}), r"must hold a 'slots' list"),
        (lambda d: d["slots"].append(d["slots"].pop(0)), r"in that order"),
        (lambda d: d["slots"][0].pop("position"), r"slot 1: missing position$"),
        (lambda d: d["slots"][0].update(position=0), r"position must be a whole number from 1"),
        (lambda d: d["slots"].__setitem__(0, "beginner_course"), r"slot 1 must be a table"),
    ],
)
def test_a_damaged_catalogue_is_refused(change: Any, message: str) -> None:
    with pytest.raises(CatalogueError, match=message):
        slots.parse(_break(change))


def test_the_catalogue_sits_inside_the_package_so_it_ships_in_the_wheel() -> None:
    package = Path(slots.__file__).parent
    assert slots.CATALOGUE_PATH.parent == package
    assert slots.CATALOGUE_PATH.is_relative_to(ROOT / "src" / "ctstudio")


@pytest.mark.parametrize("data", [[], None, "slots"])
def test_a_catalogue_that_is_not_a_table_is_refused(data: Any) -> None:
    with pytest.raises(CatalogueError, match=r"must hold a 'slots' list"):
        slots.parse(data)


def test_arenas_are_labelled_as_arenas() -> None:
    assert find("block_battle").label == "Block Plaza (Wii Arenas, arena 1)"
    assert find("old_House_ds").label == "DS Twilight House (Retro Arenas, arena 5)"


def test_race_tracks_and_arenas_are_split_by_kind_not_by_position() -> None:
    swapped = _break(lambda d: d["slots"].insert(31, d["slots"].pop(32)))
    with pytest.raises(CatalogueError, match=r"in that order"):
        slots.parse(swapped)
    assert {s.kind for s in race_tracks()} == {"race"}
    assert {s.kind for s in arenas()} == {"arena"}
    assert race_tracks() + arenas() == CATALOGUE


def test_the_committed_catalogue_passes_the_loader_checks() -> None:
    assert slots.parse(_data()) == CATALOGUE


# --- the generator ------------------------------------------------------------------------------


def _recording() -> list[dict[str, Any]]:
    return copy.deepcopy(msc.load_recording(msc.RECORDING))


def _run(records: list[dict[str, Any]], argv: list[str]) -> dict[str, Any]:
    return next(r for r in records if r["argv"] == argv)


def test_the_recording_is_from_the_pinned_wiimm_version() -> None:
    version = _run(_recording(), ["version"])
    assert "v2.42a" in version["stdout"]


def test_a_recording_from_another_version_is_refused() -> None:
    records = _recording()
    run = _run(records, ["version"])
    run["stdout"] = run["stdout"].replace("v2.42a", "v2.43a")
    with pytest.raises(msc.GenerateError, match=r"2\.42a"):
        msc.build(records)


def test_a_missing_row_is_refused() -> None:
    records = _recording()
    run = _run(records, ["tracks", "--long"])
    run["stdout"] = "".join(
        line for line in run["stdout"].splitlines(keepends=True) if "old_koopa_64" not in line
    )
    with pytest.raises(msc.GenerateError, match=r"32 race tracks"):
        msc.build(records)


def test_a_reordered_table_is_refused() -> None:
    records = _recording()
    run = _run(records, ["tracks", "--long"])
    run["stdout"] = run["stdout"].replace("  1.1  1.1  beginner", "  1.2  1.1  beginner")
    with pytest.raises(msc.GenerateError, match=r"beginner_course.*standard order"):
        msc.build(records)


def test_an_unreadable_row_is_refused_not_skipped() -> None:
    records = _recording()
    run = _run(records, ["arenas", "--long"])
    run["stdout"] = run["stdout"].replace("0xb7  n_block_n", "0xb7  n_block_n  extra")
    with pytest.raises(msc.GenerateError, match=r"cannot read this arena row: '1\.  1\.1"):
        msc.build(records)


def test_names_with_spaces_and_full_width_abbreviations_are_read_whole() -> None:
    data = msc.build(_recording())["slots"]
    by_file = {row["file"]: row for row in data}
    assert (by_file["old_donkey_64"]["abbr"], by_file["old_donkey_64"]["name"]) == (
        "nDKJP",
        "N64 DK's Jungle Parkway",
    )
    assert (by_file["old_House_ds"]["abbr"], by_file["old_House_ds"]["name"]) == (
        "adTH",
        "DS Twilight House",
    )


def test_a_row_whose_new_and_standard_slots_differ_is_refused() -> None:
    records = _recording()
    run = _run(records, ["tracks", "--long"])
    run["stdout"] = run["stdout"].replace("  1.1  1.1  beginner", "  1.2  1.1  beginner")
    run["stdout"] = run["stdout"].replace("  1.2  1.2  farm", "  1.1  1.2  farm")
    with pytest.raises(msc.GenerateError, match=r"beginner_course.*got 1\.2 / 1\.1"):
        msc.build(records)


def test_two_whole_rows_swapped_are_refused() -> None:
    records = _recording()
    run = _run(records, ["tracks", "--long"])
    lines = run["stdout"].splitlines(keepends=True)
    first = next(i for i, line in enumerate(lines) if "beginner_course" in line)
    lines[first], lines[first + 1] = lines[first + 1], lines[first]
    run["stdout"] = "".join(lines)
    with pytest.raises(msc.GenerateError, match=r"farm_course.*expected 1\.1, got 1\.2 / 1\.2"):
        msc.build(records)


def test_a_failed_tool_run_is_refused() -> None:
    records = _recording()
    _run(records, ["arenas", "--long"])["exit_code"] = 1
    with pytest.raises(msc.GenerateError, match=r"arenas --long.*exit code 1"):
        msc.build(records)


def test_check_mode_reports_a_stale_file(tmp_path: Path) -> None:
    out = tmp_path / "slots.json"
    out.write_text("{}\n", encoding="utf-8")
    assert msc.main(["--check", "--out", str(out)]) == 1
    assert msc.main(["--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == slots.CATALOGUE_PATH.read_text(encoding="utf-8")
    assert msc.main(["--check", "--out", str(out)]) == 0
