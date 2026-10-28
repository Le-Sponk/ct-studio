"""Windows-native Wiimm 2.42a KCL reports and minimap patching against the real tools.

The fakes replay these only for byte-identical recorded inputs; this checks the real
tools still produce what was recorded, including the retained patched BRRES bytes.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.tools.wiimm import WiimmError
from ctstudio.core.tools.wiimm_kcl import kcl_analyze, kcl_flags, minimap_auto

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

FIXTURES = ROOT / "tests" / "fixtures" / "generated"
KEPT = ROOT / "tests" / "fakes" / "recordings"
WSZST_IN = KEPT / "wszst" / "2.42a" / "inputs"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(120),
    pytest.mark.skipif(
        os.name != "nt" or not tp.WSZST.is_file() or not (FIXTURES / "course.kcl").is_file(),
        reason="Requires native Windows Wiimm 2.42a and generated fixtures",
    ),
]


@pytest.fixture
def work(tmp_path: Path) -> Path:
    folder = tmp_path / "kcl é"
    folder.mkdir()
    return folder


def test_real_kcl_reports_of_the_fixture(work: Path) -> None:
    kcl = work / "course.kcl"
    shutil.copyfile(FIXTURES / "course.kcl", kcl)
    analysis = kcl_analyze(kcl, executable=tp.WKCLT)
    flags = kcl_flags(kcl, executable=tp.WKCLT)
    assert analysis.triangles == flags.triangles == 292
    assert {entry.description for entry in flags.types} == {
        "Road",
        "Off-road",
        "Boost Pad",
        "Wall",
        "Fall Boundary",
    }


def test_real_kcl_flags_with_variants(work: Path) -> None:
    kcl = work / "variant.kcl"
    shutil.copyfile(KEPT / "wkclt" / "2.42a" / "inputs" / "variant.kcl", kcl)
    walls = [entry for entry in kcl_flags(kcl, executable=tp.WKCLT).flags if entry.type == 0x0C]
    assert [(entry.flag, entry.variant) for entry in walls] == [(0x212C, 0x109)]


def test_real_minimap_patch_matches_the_retained_result(work: Path) -> None:
    brres = work / "map_model.brres"
    shutil.copyfile(WSZST_IN / "map_model.brres", brres)
    first = minimap_auto(brres, executable=tp.WSZST)
    assert first.patched and first.after == first.recommended
    assert brres.read_bytes() == (WSZST_IN / "map_model_patched.brres").read_bytes()
    again = minimap_auto(brres, executable=tp.WSZST)
    assert not again.patched and again.before == first.after


def test_real_minimap_without_bones_is_failure(work: Path) -> None:
    brres = work / "plain_model.brres"
    shutil.copyfile(WSZST_IN / "no_bones_model.brres", brres)
    with pytest.raises(WiimmError, match="posLD/posRU") as caught:
        minimap_auto(brres, executable=tp.WSZST)
    assert caught.value.exit_code == 0
    assert brres.read_bytes() == (WSZST_IN / "no_bones_model.brres").read_bytes()
