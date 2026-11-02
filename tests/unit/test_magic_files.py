"""P3-T05: the sniffer recognises files real tools made (committed, synthetic content).

The KCL and KMP come from Wiimm's tools, the DAE and .blend from Blender 5 (the .blend is
saved compressed, so the ``BLENDER`` header is not at the start), the BRRES from ABMatt.
None of them contain game data (``inputs_provenance.json``, ``make_fixtures.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.formats.magic import FileKind, identify

ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "tests" / "fixtures" / "generated"
INPUTS = ROOT / "tests" / "fakes" / "recordings"
pytestmark = pytest.mark.timeout(30)


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        (GENERATED / "course.kcl", FileKind.KCL),
        (GENERATED / "course.kmp", FileKind.KMP),
        (GENERATED / "course.dae", FileKind.DAE),
        (GENERATED / "fixture_track_good.blend", FileKind.BLEND),
        (GENERATED / "fixture_track_bad.blend", FileKind.BLEND),
        (GENERATED / "road.png", FileKind.PNG),
        (INPUTS / "wszst" / "2.42a" / "inputs" / "map_model.brres", FileKind.BRRES),
        (INPUTS / "wszst" / "2.42a" / "inputs" / "no_bones_model.brres", FileKind.BRRES),
        (INPUTS / "abmatt" / "1.3.2" / "inputs" / "map.obj", FileKind.OBJ),
        (INPUTS / "abmatt" / "1.3.2" / "inputs" / "course.dae", FileKind.DAE),
    ],
    ids=lambda v: v.name if isinstance(v, Path) else None,
)
def test_files_made_by_real_tools(path: Path, kind: FileKind) -> None:
    assert identify(path) is kind


def test_the_fixture_manifests_are_not_mistaken_for_anything() -> None:
    assert identify(GENERATED / "fixture_manifest_good.json") is None
