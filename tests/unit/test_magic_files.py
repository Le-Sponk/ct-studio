"""P3-T05: the sniffer recognises files real tools made (committed, synthetic content).

These are the committed recording inputs (origins in ``inputs_provenance.json``; no game
data): the KCL and KMP come from Wiimm's tools, the DAE and .blend from Blender 5 (the
.blend is saved compressed, so the ``BLENDER`` header is not at the start), the BRRES from
ABMatt and Wiimm. ``tests/fixtures/generated`` is git-ignored and only exists after
``make_fixtures.py``, so it is not used here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.formats.magic import FileKind, identify

RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings"
pytestmark = pytest.mark.timeout(30)


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("wkclt/2.42a/inputs/course.kcl", FileKind.KCL),
        ("wkclt/2.42a/inputs/variant.kcl", FileKind.KCL),
        ("wszst/2.42a/inputs/course.kmp", FileKind.KMP),
        ("wszst/2.42a/inputs/objects.kmp", FileKind.KMP),
        ("abmatt/1.3.2/inputs/course.dae", FileKind.DAE),
        ("rszst/5.11.5/inputs/course.dae", FileKind.DAE),
        ("blender/5.2.2/inputs/good.blend", FileKind.BLEND),
        ("abmatt/1.3.2/inputs/road.png", FileKind.PNG),
        ("wimgt/2.42a/inputs/textures/bad_npot.png", FileKind.PNG),
        ("wszst/2.42a/inputs/map_model.brres", FileKind.BRRES),
        ("wszst/2.42a/inputs/map_model_patched.brres", FileKind.BRRES),
        ("wszst/2.42a/inputs/no_bones_model.brres", FileKind.BRRES),
        ("abmatt/1.3.2/inputs/map.obj", FileKind.OBJ),
    ],
)
def test_files_made_by_real_tools(name: str, kind: FileKind) -> None:
    assert identify(RECORDINGS / name) is kind


def test_a_json_file_is_not_mistaken_for_anything() -> None:
    assert identify(RECORDINGS / "inputs_provenance.json") is None
