"""Windows-native rszst 5.11.5 through the P2-T05e adapter, in a folder named with é.

The real build cannot read non-ASCII argv; these runs prove the adapter's ASCII staging
makes such a project folder work, and that refusals happen before the tool runs.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.name != "nt", reason="native rszst recordings are Windows-only so far"),
    pytest.mark.timeout(300),
]

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "tests" / "fakes" / "recordings" / "rszst" / "5.11.5" / "inputs"
RSZST = ROOT / ".tools" / "riistudio" / "rszst.exe"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    if not RSZST.is_file():
        pytest.skip("pinned rszst not bootstrapped")
    folder = tmp_path / "piste é"
    folder.mkdir()
    for name in ("course.dae", "road.png", "grass.png", "fence.png", "water.png"):
        shutil.copyfile(INPUTS / name, folder / name)
    return folder / "course.dae"


def test_real_import_json_round_trip_and_presets(project: Path, tmp_path: Path) -> None:
    from ctstudio.core.tools.riistudio import (
        brres_to_json,
        dump_presets,
        import_brres,
        json_to_brres,
    )

    out = tmp_path / "sortie é"
    model = import_brres(project, out / "course_model.brres", model_name="course", executable=RSZST)
    assert model.read_bytes()[:4] == b"bres" and model.stat().st_size > 1000
    json_path, bin_path = brres_to_json(model, out / "model.json", executable=RSZST)
    assert b'"textures"' in json_path.read_bytes() and bin_path.read_bytes()[:4] == b"RBUF"
    rebuilt = json_to_brres(json_path, out / "rebuilt.brres", executable=RSZST)
    assert rebuilt.read_bytes()[:4] == b"bres"
    presets = dump_presets(model, out / "préréglages", executable=RSZST)
    assert sorted(p.stem for p in presets) == ["fence", "grass", "road", "water"]
    again = import_brres(
        project,
        out / "again.brres",
        model_name="course",
        presets=presets[0].parent,
        executable=RSZST,
    )
    assert again.read_bytes()[:4] == b"bres"


def test_real_import_keeps_every_texture_size(project: Path, tmp_path: Path) -> None:
    """The fence is 32x64: a 32x32 texture would be rszst's silent placeholder."""
    import json

    from ctstudio.core.tools.riistudio import brres_to_json, import_brres

    model = import_brres(project, tmp_path / "m.brres", model_name="course", executable=RSZST)
    json_path, _ = brres_to_json(model, tmp_path / "m.json", executable=RSZST)
    textures = json.loads(json_path.read_text(encoding="utf-8"))["textures"]
    sizes = {t["name"]: (t["width"], t["height"]) for t in textures}
    assert sizes == {"fence": (32, 64), "grass": (64, 64), "road": (64, 64), "water": (64, 64)}


def test_real_refusals_happen_before_running(project: Path, tmp_path: Path) -> None:
    from ctstudio.core.tools.riistudio import RiiStudioError, import_brres

    (project.parent / "fence.png").unlink()
    with pytest.raises(RiiStudioError, match="missing"):
        import_brres(project, tmp_path / "o.brres", model_name="course", executable=RSZST)
    assert not (tmp_path / "o.brres").exists()
