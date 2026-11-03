"""P4-T05b: the KMP object table and Wiimm's object -> file database (wkmpt 2.42a).

The texts below are real 2.42a output for synthetic KMPs (measured 2026-11-03): ``wkmpt cat``
of a KMP placing pocha, pochaMori, two itemboxes, dummy and the unknown id 0x3ff, and
``wkmpt objects --long --width 4000`` for those ids (Info lines shortened).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.errors import ParseError
from ctstudio.core.tools import wiimm_objects
from ctstudio.core.tools.wiimm import WiimmOutput
from ctstudio.core.tools.wiimm_objects import (
    KmpObject,
    kmp_objects,
    object_files,
    parse_kmp_objects,
    parse_object_files,
)

RULE = "##" + "-" * 92
STATS = "\n".join(
    [
        "@SORT-REFERENCE = DOB$OFF",
        "",
        "# Object statistics:",
        RULE,
        "##count id/hex  name               characteristics",
        RULE,
        "##   1    0x7   pocha              no route, found in tracks + arenas",
        "##   1   0x13   pochaMori          no route, found in tracks + arenas",
        "##   2   0x65   itembox            no route, solid, found in tracks + arenas + other",
        "##   1  0x12d   dummy              ",
        "##   1  0x3ff",
        "##" + "-" * 83,
        "## GOBJ total: 6 objects, 5 types",
        "##" + "-" * 83,
        "",
        "   o0   0x7       0.000       0.000       0.000      0      0      0      0      -1",
    ]
)
NONE = (
    f"# Object statistics:\n{RULE}\n##count id/hex  name\n{RULE}\n"
    "## GOBJ total: 0 objects, 0 types\n"
)
ONE = (
    f"# Object statistics:\n{RULE}\n"
    "##   1   0x65   itembox            no route, solid\n## GOBJ total: 1 object, 1 type\n"
)
LINE = "-" * 110
DATABASE = "\n".join(
    [
        "",
        "  ID Object name        Characteristics",
        LINE,
        "   7 pocha              no route, found in tracks + arenas",
        "   Info:  Generates a water splash effect when a player touches KCL flag 0x10.",
        "   Files: effect/pocha/rk_pocha.breff",
        "          effect/pocha/rk_pocha.breft",
        "          pocha.brres",
        "   Set#1: Group Y KCL Index",
        LINE,
        "  13 pochaMori          no route, found in tracks + arenas",
        "   Info:  Generates a leaf splash effect. Only the Y coordinate is used.",
        "          Second paragraph of the info.",
        "   Files: effect/pochaMori/rk_pochaLeaf.breff",
        "          effect/pochaMori/rk_pochaLeaf.breft",
        "   Set#1: Group Y KCL Index",
        LINE,
        "  65 itembox            no route, solid, found in tracks + arenas + other files",
        "   Info:  Spinning box with a question mark inside it.",
        "   Files: itembox.brres",
        "   Set#1: Unknown",
        "   Set#7: [?] Additional height, multiplied with unknown number (always 1?).",
        LINE,
        " 12d dummy              ",
        "   Info:  Object not used in any track.",
        LINE,
        "",
    ]
)


def test_the_object_table_is_read_with_counts_and_unknown_ids() -> None:
    assert parse_kmp_objects(STATS, Path("course.kmp")) == (
        KmpObject(0x7, "pocha", 1),
        KmpObject(0x13, "pochaMori", 1),
        KmpObject(0x65, "itembox", 2),
        KmpObject(0x12D, "dummy", 1),
        KmpObject(0x3FF, "", 1),
    )
    assert parse_kmp_objects(NONE, Path("course.kmp")) == ()
    assert parse_kmp_objects(ONE, Path("course.kmp")) == (KmpObject(0x65, "itembox", 1),)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("[GOBJ]\n", "no object statistics"),
        (STATS.replace("## GOBJ total: 6 objects, 5 types", ""), "no GOBJ total"),
        (STATS.replace("6 objects", "7 objects"), "disagree"),
        (STATS.replace("5 types", "4 types"), "disagree"),
    ],
)
def test_a_cut_short_or_inconsistent_table_is_refused(text: str, reason: str) -> None:
    with pytest.raises(ParseError, match=reason):
        parse_kmp_objects(text, Path("course.kmp"))


def test_the_database_gives_every_file_line_and_nothing_else() -> None:
    assert parse_object_files(DATABASE) == {
        0x7: ("effect/pocha/rk_pocha.breff", "effect/pocha/rk_pocha.breft", "pocha.brres"),
        0x13: ("effect/pochaMori/rk_pochaLeaf.breff", "effect/pochaMori/rk_pochaLeaf.breft"),
        0x65: ("itembox.brres",),
        0x12D: (),
    }
    assert parse_object_files("\n\n") == {}


def _fake_invoke(
    stdout: str, calls: list[tuple[list[str], Path, str]], exit_code: int = 0
) -> object:
    def invoke(
        _exe: Path | None,
        args: list[str],
        cwd: Path,
        _timeout: float,
        _cancel: object,
        *,
        tool: str = "wszst",
    ) -> WiimmOutput:
        calls.append((args, cwd, tool))
        return WiimmOutput(exit_code, stdout, "")

    return invoke


def test_kmp_objects_runs_wkmpt_cat_in_the_kmp_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], Path, str]] = []
    monkeypatch.setattr(wiimm_objects, "invoke", _fake_invoke(ONE, calls))
    kmp = tmp_path / "stage é" / "course.kmp"
    assert kmp_objects(kmp) == (KmpObject(0x65, "itembox", 1),)
    assert calls == [(["cat", "course.kmp"], kmp.parent, "wkmpt")]


def test_object_files_asks_once_and_keeps_only_the_asked_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], Path, str]] = []
    monkeypatch.setattr(wiimm_objects, "invoke", _fake_invoke(DATABASE, calls))
    assert object_files([0x65, 0x7, 0x65, 0x3FF]) == {
        0x7: ("effect/pocha/rk_pocha.breff", "effect/pocha/rk_pocha.breft", "pocha.brres"),
        0x65: ("itembox.brres",),
    }
    [(args, _cwd, tool)] = calls
    assert args == ["objects", "--long", "--width", "4000", "0x7", "0x65", "0x3ff"]
    assert tool == "wkmpt"
    assert object_files([]) == {}
    assert len(calls) == 1, "no ids: wkmpt is not started"


def test_a_failed_wkmpt_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], Path, str]] = []
    monkeypatch.setattr(wiimm_objects, "invoke", _fake_invoke("", calls, exit_code=78))
    with pytest.raises(Exception, match="78"):
        kmp_objects(tmp_path / "course.kmp")
    with pytest.raises(Exception, match="78"):
        object_files([0x65])
