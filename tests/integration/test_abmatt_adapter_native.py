"""Windows-native ABMatt 1.3.2 through the P2-T05e2 adapter, in folders named with 日本.

ABMatt crashes printing CJK paths after writing; these runs prove the staged conversion
still delivers a checked archive, and that the minimap bones it makes are real (Wiimm's
``minimap --auto`` finds and patches them).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.tools.abmatt import AbmattError, convert_minimap, convert_model
from ctstudio.core.tools.wiimm_kcl import minimap_auto

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

INPUTS = ROOT / "tests" / "fakes" / "recordings" / "abmatt" / "1.3.2" / "inputs"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        os.name != "nt" or not tp.ABMATT.is_file() or not tp.WIMGT.is_file(),
        reason="Requires native Windows ABMatt 1.3.2 and Wiimm 2.42a",
    ),
]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    folder = tmp_path / "piste 日本"
    folder.mkdir()
    for name in ("course.dae", "road.png", "grass.png", "fence.png", "water.png"):
        shutil.copyfile(INPUTS / name, folder / name)
    return folder / "course.dae"


def test_real_model_conversion_in_a_cjk_folder(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "sortie 日本" / "vrcorn_model.brres"
    result = convert_model(project, out, model_name="vrcorn", executable=tp.ABMATT, wimgt=tp.WIMGT)
    assert result.path == out and out.read_bytes()[:4] == b"bres"
    assert [(m.model, m.material) for m in result.materials] == [
        ("vrcorn", "road"),
        ("vrcorn", "grass"),
        ("vrcorn", "fence"),
        ("vrcorn", "water"),
    ]


def test_real_minimap_has_bones_wiimm_can_patch(tmp_path: Path) -> None:
    obj = tmp_path / "carte 日本" / "drivable.obj"
    obj.parent.mkdir()
    shutil.copyfile(INPUTS / "map.obj", obj)
    result = convert_minimap(
        obj, tmp_path / "map_model.brres", executable=tp.ABMATT, wimgt=tp.WIMGT
    )
    assert [(m.model, m.material) for m in result.materials] == [("map", "road")]
    patch = minimap_auto(result.path, executable=tp.WSZST)
    assert patch.patched


def test_real_missing_texture_is_refused_before_running(project: Path, tmp_path: Path) -> None:
    (project.parent / "fence.png").unlink()
    with pytest.raises(AbmattError, match=r"missing.*fence\.png"):
        convert_model(project, tmp_path / "o.brres", model_name="course", executable=tp.ABMATT)
    assert not (tmp_path / "o.brres").exists()
