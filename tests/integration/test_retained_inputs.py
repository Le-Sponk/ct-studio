"""P2-GATE Should fix 6: rebuild the retained minimap BRRES inputs with the real tools.

``tests/fakes/recordings/inputs_provenance.json`` marks two inputs ``rebuilt``. This test
makes them again from the committed synthetic ``map.obj`` and checks the bytes:
``abmatt convert map.obj to map_model.brres -o`` and then ``wszst minimap --auto`` on a copy.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.tools.process import run

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

RECORDINGS = ROOT / "tests" / "fakes" / "recordings"
MANIFEST = json.loads((RECORDINGS / "inputs_provenance.json").read_text(encoding="utf-8"))
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        not tp.ABMATT.is_file() or not tp.WSZST.is_file(),
        reason="Requires ABMatt 1.3.2 and Wiimm 2.42a",
    ),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _listed(name: str) -> str:
    return MANIFEST["inputs"][f"wszst/2.42a/inputs/{name}"]["sha256"]


def test_the_rebuilt_inputs_are_marked_so() -> None:
    rebuilt = {k for k, v in MANIFEST["inputs"].items() if v["origin"] == "rebuilt"}
    assert rebuilt == {
        "wszst/2.42a/inputs/map_model.brres",
        "wszst/2.42a/inputs/map_model_patched.brres",
    }


def test_map_model_and_its_patched_copy_rebuild_byte_for_byte(tmp_path: Path) -> None:
    work = tmp_path / "rebuild é"
    work.mkdir()
    shutil.copy2(RECORDINGS / "abmatt" / "1.3.2" / "inputs" / "map.obj", work / "map.obj")
    convert = [str(tp.ABMATT), "convert", "map.obj", "to", "map_model.brres", "-o"]
    assert run(convert, cwd=work, timeout=120).exit_code == 0
    assert _sha(work / "map_model.brres") == _listed("map_model.brres")
    shutil.copy2(work / "map_model.brres", work / "patched.brres")
    patch = [str(tp.WSZST), "minimap", "--auto", "patched.brres"]
    assert run(patch, cwd=work, timeout=120).exit_code == 0
    assert _sha(work / "patched.brres") == _listed("map_model_patched.brres")
