"""Windows-native ABMatt 1.3.2 material edits and paste through P2-T05e3, in 日本 folders.

Every assertion reads the archive back through ABMatt itself (``-c info``), so these
runs prove the anchored selectors, the no-op skip and texture-removal reporting on the
real tool, including a paste into a separate minimap archive.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.tools.abmatt import convert_minimap, convert_model
from ctstudio.core.tools.abmatt_edit import (
    EditResult,
    MaterialEdit,
    MaterialRef,
    PasteResult,
    edit_materials,
    paste_material,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

INPUTS = ROOT / "tests" / "fakes" / "recordings" / "abmatt" / "1.3.2" / "inputs"
TOOLS = {"executable": tp.ABMATT, "wimgt": tp.WIMGT}
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        os.name != "nt" or not tp.ABMATT.is_file() or not tp.WIMGT.is_file(),
        reason="Requires native Windows ABMatt 1.3.2 and Wiimm 2.42a",
    ),
]


@pytest.fixture
def model(tmp_path: Path) -> Path:
    folder = tmp_path / "piste 日本"
    folder.mkdir()
    for name in ("course.dae", "road.png", "grass.png", "fence.png", "water.png"):
        shutil.copyfile(INPUTS / name, folder / name)
    out = tmp_path / "sortie 日本" / "course_model.brres"
    convert_model(folder / "course.dae", out, model_name="course", **TOOLS)
    return out


def _table(result: EditResult | PasteResult) -> dict[str, tuple[bool, str, tuple[str, ...]]]:
    return {m.material: (m.xlu, m.cull, m.layers) for m in result.materials}


def test_real_edit_changes_only_the_named_materials(model: Path) -> None:
    edits = [MaterialEdit("road", "course", xlu=True), MaterialEdit("grass", "course", cull="none")]
    result = edit_materials(model, edits, **TOOLS)
    assert result.changed
    assert _table(result) == {
        "road": (True, "inside", ("road",)),
        "grass": (False, "none", ("grass",)),
        "fence": (False, "inside", ("fence",)),
        "water": (False, "inside", ("water",)),
    }
    assert len(list(model.parent.glob("course_model.brres.*.bak"))) == 1
    again = edit_materials(model, edits, **TOOLS)
    assert not again.changed and len(list(model.parent.glob("*.bak"))) == 1


def test_real_paste_within_one_archive_reports_the_removed_texture(model: Path) -> None:
    edit_materials(model, [MaterialEdit("road", "course", xlu=True)], **TOOLS)
    paste = paste_material(
        MaterialRef(model, "course", "road"), MaterialRef(model, "course", "fence"), **TOOLS
    )
    assert paste.removed_textures == ("fence",)
    assert _table(paste)["fence"] == (True, "inside", ("road",))


def test_real_paste_into_a_minimap_archive(model: Path, tmp_path: Path) -> None:
    obj = tmp_path / "carte 日本" / "drivable.obj"
    obj.parent.mkdir()
    shutil.copyfile(INPUTS / "map.obj", obj)
    minimap = convert_minimap(obj, tmp_path / "map_model.brres", **TOOLS).path
    edit_materials(model, [MaterialEdit("road", "course", cull="none")], **TOOLS)
    paste = paste_material(
        MaterialRef(model, "course", "road"), MaterialRef(minimap, "map", "road"), **TOOLS
    )
    assert _table(paste) == {"road": (False, "none", ("road",))}
    assert paste.removed_textures == ()
    assert any("UV channel" in warning for warning in paste.warnings)
