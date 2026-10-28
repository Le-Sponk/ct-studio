"""P2-T05c2: typed KCL analysis/flags and minimap patching from real Wiimm 2.42a output."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ctstudio.core.errors import ParseError

ROOT = Path(__file__).resolve().parents[1] / "fakes" / "recordings"
WSZST_IN = ROOT / "wszst" / "2.42a" / "inputs"
WKCLT_IN = ROOT / "wkclt" / "2.42a" / "inputs"


def _stdout(tool: str, case: str) -> str:
    rows = json.loads((ROOT / tool / "2.42a" / "windows-ops.json").read_text(encoding="utf-8"))
    return next(str(row["stdout"]) for row in rows if row["case"] == case)


def _copy(tmp_path: Path, source: Path, name: str | None = None) -> Path:
    target = tmp_path / (name or source.name)
    shutil.copyfile(source, target)
    return target


# --- parsers, on the recorded real output -------------------------------------------------


def test_parse_analysis_of_the_fixture_kcl() -> None:
    from ctstudio.core.tools.wiimm_kcl import parse_kcl_analysis

    result = parse_kcl_analysis(_stdout("wkclt", "kcl analyze"), Path("course.kcl"))
    assert (result.triangles, result.vertices) == (292, 292)
    assert result.vertex_min == pytest.approx(-14475.09)
    assert result.vertex_max == pytest.approx(24000.0)
    assert (result.normal_min, result.normal_max) == (pytest.approx(-0.9978589), 1.0)


def test_parse_flags_of_a_kcl_with_variants() -> None:
    from ctstudio.core.tools.wiimm_kcl import KclFlag, KclType, parse_kcl_flags

    result = parse_kcl_flags(_stdout("wkclt", "kcl flags variant"), Path("variant.kcl"))
    assert result.flags == (
        KclFlag(0x0120, 0x00, 0x009, 96),
        KclFlag(0x0003, 0x03, 0x000, 96),
        KclFlag(0x0006, 0x06, 0x000, 2),
        KclFlag(0x212C, 0x0C, 0x109, 96),
        KclFlag(0x0010, 0x10, 0x000, 2),
    )
    assert result.types == (
        KclType(0x00, 96, "Road"),
        KclType(0x03, 96, "Off-road"),
        KclType(0x06, 2, "Boost Pad"),
        KclType(0x0C, 96, "Wall"),
        KclType(0x10, 2, "Fall Boundary"),
    )
    assert result.triangles == 292


@pytest.mark.parametrize(
    "mangle",
    [
        lambda text: text.replace("T 0x10 :      2", "T 0x10 :      3"),  # types disagree
        lambda text: text.replace(" 0x0006 = 0x06", " 0x0006 = 0x07"),  # flag and type
        lambda text: text.split("   type :")[0],  # type table missing
        lambda text: text.replace("0x0120 = 0x00 | 0x009", "0x0120 = 0x00 | 0x008"),
        lambda text: "KCL Flags of KCL:v.kcl\n   type :  triangle count  : type description\n",
    ],
    ids=["count mismatch", "type mismatch", "truncated", "variant mismatch", "no rows"],
)
def test_parse_flags_refuses_inconsistent_tables(mangle) -> None:
    from ctstudio.core.tools.wiimm_kcl import parse_kcl_flags

    text = mangle(_stdout("wkclt", "kcl flags variant"))
    with pytest.raises(ParseError):
        parse_kcl_flags(text, Path("variant.kcl"))


def test_parse_analysis_refuses_missing_rows() -> None:
    from ctstudio.core.tools.wiimm_kcl import parse_kcl_analysis

    text = _stdout("wkclt", "kcl analyze").replace(" max:", " mux:")
    with pytest.raises(ParseError):
        parse_kcl_analysis(text, Path("course.kcl"))
    with pytest.raises(ParseError):
        parse_kcl_analysis("Analyze KCL:course.kcl\n", Path("course.kcl"))


def test_parse_minimap_patch() -> None:
    from ctstudio.core.tools.wiimm_kcl import parse_minimap

    result = parse_minimap(_stdout("wszst", "minimap auto brres"), Path("map_model.brres"))
    assert result.patched is True
    assert result.before == ((-6000.0, 0.0, 6100.0), (6100.0, 0.0, -6000.0))
    assert result.after == ((-102.0, 0.0, 202.0), (202.0, 0.0, -102.0))
    assert result.recommended == result.after


def test_parse_minimap_already_patched_is_unchanged_not_failure() -> None:
    from ctstudio.core.tools.wiimm_kcl import parse_minimap

    result = parse_minimap(_stdout("wszst", "minimap auto brres patched"), Path("p.brres"))
    assert result.patched is False
    assert result.before == result.after == result.recommended


@pytest.mark.parametrize("case", ["minimap auto no bones", "minimap auto junk"])
def test_parse_minimap_without_bones_is_failure(case: str) -> None:
    from ctstudio.core.tools.wiimm import WiimmError
    from ctstudio.core.tools.wiimm_kcl import parse_minimap

    # Real: exit 0, header only, file untouched; the only signal is the missing rows.
    with pytest.raises(WiimmError, match="posLD/posRU"):
        parse_minimap(_stdout("wszst", case), Path("x.brres"))


def test_parse_minimap_patch_line_without_new_rows_is_parse_error() -> None:
    from ctstudio.core.tools.wiimm_kcl import parse_minimap

    text = _stdout("wszst", "minimap auto brres")
    head, _, _ = text.partition("Idx+Id+Flags:         1         1     0x31f")
    with pytest.raises(ParseError):
        parse_minimap(head + "PATCH MINIMAP BRRES:map_model.brres\n", Path("m.brres"))


# --- adapters through the fakes -----------------------------------------------------------


def test_kcl_analyze_and_flags_via_fake(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm_kcl import kcl_analyze, kcl_flags

    kcl = _copy(tmp_path, WKCLT_IN / "variant.kcl")
    assert kcl_analyze(kcl).triangles == 292
    assert kcl_flags(kcl).flags[3].variant == 0x109
    assert [call["argv"] for call in fake_tools_path.calls()] == [
        ["analyze", "variant.kcl"],
        ["flags", "variant.kcl"],
    ]
    assert {call["tool"] for call in fake_tools_path.calls()} == {"wkclt"}


@pytest.mark.parametrize("command", ["analyze", "flags"])
def test_kcl_junk_raises_typed_error(fake_tools_path, tmp_path: Path, command: str) -> None:
    from ctstudio.core.tools import wiimm_kcl
    from ctstudio.core.tools.wiimm import WiimmError

    junk = tmp_path / "junk.kcl"
    junk.write_bytes(b"not a track file\n" * 4)
    with pytest.raises(WiimmError) as caught:
        getattr(wiimm_kcl, f"kcl_{command}")(junk)
    assert (caught.value.error_code, caught.value.exit_code) == (36, 36)


def test_minimap_auto_patches_via_fake(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm_kcl import minimap_auto

    brres = _copy(tmp_path, WSZST_IN / "map_model.brres")
    result = minimap_auto(brres)
    assert result.patched is True
    assert brres.read_bytes() == (WSZST_IN / "map_model_patched.brres").read_bytes()
    assert fake_tools_path.calls()[0]["argv"] == ["minimap", "--auto", "map_model.brres"]


def test_minimap_auto_without_bones_raises_and_leaves_file(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError
    from ctstudio.core.tools.wiimm_kcl import minimap_auto

    brres = _copy(tmp_path, WSZST_IN / "no_bones_model.brres")
    with pytest.raises(WiimmError, match="posLD/posRU") as caught:
        minimap_auto(brres)
    assert caught.value.exit_code == 0
    assert brres.read_bytes() == (WSZST_IN / "no_bones_model.brres").read_bytes()


def test_minimap_auto_patched_line_without_change_is_failure(monkeypatch, tmp_path: Path) -> None:
    from ctstudio.core.tools import wiimm, wiimm_kcl
    from ctstudio.core.tools.process import RunResult

    brres = _copy(tmp_path, WSZST_IN / "map_model.brres")
    text = _stdout("wszst", "minimap auto brres")

    def fake_run(cmd, *, on_line, **_kwargs) -> RunResult:
        for line in text.splitlines():
            on_line("stdout", line)
        return RunResult(0, 0.0, "", "", None)  # claims PATCH but leaves the bytes

    monkeypatch.setattr(wiimm, "run", fake_run)
    with pytest.raises(wiimm.WiimmError, match="unchanged"):
        wiimm_kcl.minimap_auto(brres, executable=tmp_path / "wszst")


def test_minimap_auto_missing_file(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError
    from ctstudio.core.tools.wiimm_kcl import minimap_auto

    with pytest.raises(WiimmError) as caught:
        minimap_auto(tmp_path / "missing.brres")
    assert (caught.value.error_code, caught.value.exit_code) == (78, 78)
