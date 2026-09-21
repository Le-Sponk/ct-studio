"""S5 contract tests: producing a minimap (`map_model.brres`) headlessly.

Pins the behaviour P9 relies on, measured in P0-T08 against Wiimms SZS Tools
2.42a, ABMatt 1.3.2 and RiiStudio Alpha 5.11.5. Findings: docs/dev/SPIKES.md §S5.

These run against the real tools and skip when they are absent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / ".tools"
RSZST = TOOLS / "riistudio-build-pinned" / "source" / "cli" / "rszst"
ABMATT = TOOLS / "abmatt" / "bin" / "abmatt"
WIIMMS_BIN = TOOLS / "wiimms-szs-tools" / "bin"
FIXTURE_KCL = REPO / "tests" / "fixtures" / "generated" / "course.kcl"
FIXTURE_DAE = REPO / "spikes" / "out" / "s2" / "course_builtin.dae"
KCL_FILTER = REPO / "spikes" / "s5_minimap.py"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not ABMATT.is_file(), reason="abmatt not installed"),
    pytest.mark.skipif(not (WIIMMS_BIN / "wszst").is_file(), reason="wiimms tools not installed"),
    pytest.mark.skipif(not FIXTURE_KCL.is_file(), reason="fixture KCL not generated"),
]

# Kept in step with spikes/s5_minimap.py; duplicated so the test is self-contained.
FILTER_SCRIPT = """\
@def removed = 0

@function isNotDrivable # flag
    @pdef t = $1 & 0x1f
    @return t == 0x0c || t == 0x0d || t == 0x0f || t == 0x10 \\
         || t == 0x14 || t == 0x1e || t == 0x1f
@endfunction

@for t=0;tri$n()-1
    @if isNotDrivable(tri$flag(t))
        @def status = tri$remove(t)
        @def removed = removed+1
    @endif
@endfor
"""


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{WIIMMS_BIN}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(  # noqa: S603 - local pinned tools, argv only
        args, cwd=cwd, capture_output=True, text=True, timeout=180, check=False, env=env
    )


def mdl0_name(work: Path, brres: str) -> str | None:
    for line in run(["wszst", "list", brres], work).stdout.splitlines():
        line = line.strip()
        if line.startswith("3DModels(NW4R)/") and not line.endswith("/"):
            return line.split("/", 1)[1]
    return None


def minimap_translations(work: Path, brres: str) -> list[str]:
    """Empty when the model has no posLD/posRU bones: wszst prints no data rows."""
    result = run(["wszst", "minimap", brres], work)
    rows = [line for line in result.stdout.splitlines() if "Translation:" in line]
    return rows[0].split(":", 1)[1].split() if rows else []


def face_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("f "))


def convert(work: Path, source: str, dest: str) -> subprocess.CompletedProcess[str]:
    return run([str(ABMATT), "convert", source, "to", dest, "-o"], work)


@pytest.fixture
def work(tmp_path: Path) -> Path:
    shutil.copy(FIXTURE_KCL, tmp_path / "course.kcl")
    (tmp_path / "drivable.txt").write_text(FILTER_SCRIPT, encoding="utf-8")
    return tmp_path


def decode_drivable(work: Path) -> Path:
    run(
        ["wkclt", "decode", "course.kcl", "--dest", "drivable.obj", "--kcl-script", "drivable.txt"],
        work,
    )
    return work / "drivable.obj"


def test_kcl_script_filters_out_walls_and_boundaries(work: Path) -> None:
    """Path 1 depends on wkclt dropping non-drivable triangles from the decode."""
    run(["wkclt", "decode", "course.kcl", "--dest", "full.obj"], work)
    filtered = decode_drivable(work)

    total = face_count(work / "full.obj")
    kept = face_count(filtered)

    assert total == 292
    assert kept == 194
    assert kept < total


def test_path_1_kcl_to_map_model_is_a_valid_minimap(work: Path) -> None:
    """KCL → filtered OBJ → ABMatt produces MDL0 `map` with the position bones."""
    decode_drivable(work)

    result = convert(work, "drivable.obj", "map_model.brres")

    assert result.returncode == 0
    assert mdl0_name(work, "map_model.brres") == "map"
    assert minimap_translations(work, "map_model.brres")


def test_wszst_minimap_auto_rewrites_the_translations(work: Path) -> None:
    decode_drivable(work)
    convert(work, "drivable.obj", "map_model.brres")
    before = minimap_translations(work, "map_model.brres")

    patched = run(["wszst", "minimap", "--auto", "map_model.brres"], work)
    after = minimap_translations(work, "map_model.brres")

    assert patched.returncode == 0
    assert before == ["-20600.0", "0.0", "20600.0", "20600.0", "0.0", "-20600.0"]
    assert after == ["-15284.0", "0.0", "15284.0", "15284.0", "0.0", "-15284.0"]
    assert before != after


def test_position_bones_come_from_the_destination_name_not_the_mdl0_name(work: Path) -> None:
    """The trap: an MDL0 called `map` does NOT imply a usable minimap.

    ABMatt adds posLD/posRU when the *destination* filename contains `map`. A
    source file named `map*` renames the MDL0 but creates no bones, so the file
    looks right to `wszst list` and is silently useless in game.
    """
    decode_drivable(work)
    shutil.copy(work / "drivable.obj", work / "mapsource.obj")
    if (work / "drivable.mtl").is_file():
        shutil.copy(work / "drivable.mtl", work / "mapsource.mtl")

    convert(work, "mapsource.obj", "plain.brres")
    convert(work, "drivable.obj", "map_model.brres")

    # Both claim the right MDL0 name...
    assert mdl0_name(work, "plain.brres") == "map"
    assert mdl0_name(work, "map_model.brres") == "map"
    # ...but only the one with `map` in the destination has the bones.
    assert not minimap_translations(work, "plain.brres")
    assert minimap_translations(work, "map_model.brres")


def test_destination_map_matching_is_case_sensitive(work: Path) -> None:
    decode_drivable(work)

    convert(work, "drivable.obj", "MAP.brres")
    convert(work, "drivable.obj", "mymap.brres")

    assert mdl0_name(work, "MAP.brres") == "drivable"
    assert not minimap_translations(work, "MAP.brres")
    assert mdl0_name(work, "mymap.brres") == "map"
    assert minimap_translations(work, "mymap.brres")


def test_a_non_map_destination_produces_an_ordinary_model(work: Path) -> None:
    decode_drivable(work)

    convert(work, "drivable.obj", "vrcorn_model.brres")

    assert mdl0_name(work, "vrcorn_model.brres") == "vrcorn"
    assert not minimap_translations(work, "vrcorn_model.brres")


@pytest.mark.skipif(not FIXTURE_DAE.is_file(), reason="S2 fixture DAE not generated")
@pytest.mark.skipif(not RSZST.is_file(), reason="rszst not built (P0-T06a)")
def test_path_2_rszst_names_the_mdl0_but_creates_no_position_bones(work: Path) -> None:
    """rszst --model-name map is not enough: no posLD/posRU, so no minimap."""
    shutil.copy(FIXTURE_DAE, work / "course.dae")
    for png in FIXTURE_DAE.parent.glob("*.png"):
        shutil.copy(png, work / png.name)

    result = run(
        [str(RSZST), "import-brres", "course.dae", "rszst_map.brres", "--model-name", "map"], work
    )

    assert result.returncode == 0
    assert mdl0_name(work, "rszst_map.brres") == "map"
    assert not minimap_translations(work, "rszst_map.brres")

    # --auto cannot help: there are no bones to patch.
    patched = run(["wszst", "minimap", "--auto", "rszst_map.brres"], work)
    assert patched.returncode == 0
    assert not minimap_translations(work, "rszst_map.brres")


@pytest.mark.skipif(not RSZST.is_file(), reason="rszst not built (P0-T06a)")
def test_abmatt_minimap_bones_are_named_map_posld_posru(work: Path) -> None:
    decode_drivable(work)
    convert(work, "drivable.obj", "map_model.brres")

    dumped = run([str(RSZST), "brres-to-json", "map_model.brres", "map.json"], work)
    assert dumped.returncode == 0
    model = json.loads((work / "map.json").read_text(encoding="utf-8"))["models"][0]

    assert [bone.get("name") for bone in model["bones"]] == ["map", "posLD", "posRU"]
