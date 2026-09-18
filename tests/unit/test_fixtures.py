"""Tests for the synthetic fixture track (P0-T03).

Two layers:
  * Pure-Python tests of the PNG writer and the KMP source (no Blender, always run).
  * Tests of the generated fixture, which need Blender and Wiimms from .tools/ and
    skip with a clear reason when the fixtures have not been generated yet.

Regenerate with: uv run python scripts/fixtures/make_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "fixtures"))

import make_textures as mt

GENERATED = REPO_ROOT / "tests" / "fixtures" / "generated"
KMP_SOURCE = REPO_ROOT / "scripts" / "fixtures" / "course.kmp.txt"
WKMPT = REPO_ROOT / ".tools" / "wiimms-szs-tools" / "bin" / "wkmpt"

pytestmark = pytest.mark.timeout(60)

needs_fixtures = pytest.mark.skipif(
    not (GENERATED / "fixture_manifest_good.json").exists(),
    reason="fixtures not generated; run scripts/fixtures/make_fixtures.py",
)


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Temp dir on the repo volume (the container mounts /tmp noexec)."""
    base = REPO_ROOT / ".ctstudio" / "pytest-tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def read_png_header(path: Path) -> tuple[int, int, int, int]:
    """Return (width, height, bit_depth, colour_type) from a PNG's IHDR."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    assert data[12:16] == b"IHDR", f"{path.name}: first chunk is not IHDR"
    width, height, depth, colour = struct.unpack_from(">IIBB", data, 16)
    return width, height, depth, colour


# --- texture generation (no Blender needed) --------------------------------------


def test_write_png_round_trips_pixels(tmp_path: Path) -> None:
    """The hand-rolled encoder must produce data a decoder can read back exactly."""
    rgba = bytes([255, 0, 0, 255, 0, 255, 0, 128, 0, 0, 255, 255, 9, 9, 9, 0])
    path = tmp_path / "probe.png"
    mt.write_png(path, 2, 2, rgba)

    data = path.read_bytes()
    idat = b""
    pos = 8
    while pos < len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        tag = data[pos + 4 : pos + 8]
        if tag == b"IDAT":
            idat += data[pos + 8 : pos + 8 + length]
        pos += 12 + length

    raw = zlib.decompress(idat)
    # Each row is prefixed with its filter byte (0 = None).
    assert raw[0] == 0 and raw[9] == 0
    assert raw[1:9] == rgba[:8]
    assert raw[10:18] == rgba[8:]


def test_write_png_rejects_wrong_buffer_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="expected"):
        mt.write_png(tmp_path / "bad.png", 4, 4, b"\x00" * 10)


def test_write_png_is_deterministic(tmp_path: Path) -> None:
    """Fixtures are cached by content, so repeated generation must be byte-identical."""
    first = tmp_path / "a"
    second = tmp_path / "b"
    mt.generate_textures(first)
    mt.generate_textures(second)
    for name in mt.TEXTURE_SIZES:
        assert (first / f"{name}.png").read_bytes() == (second / f"{name}.png").read_bytes()


def test_generated_textures_have_the_declared_sizes(tmp_path: Path) -> None:
    paths = mt.generate_textures(tmp_path)
    for name, (width, height) in mt.TEXTURE_SIZES.items():
        got_w, got_h, depth, colour = read_png_header(paths[name])
        assert (got_w, got_h) == (width, height), name
        assert (depth, colour) == (8, 6), f"{name} should be 8-bit RGBA"


def test_all_textures_are_power_of_two_except_the_bad_one() -> None:
    """MKW_DOMAIN section 3: power-of-two sizes; one fixture deliberately is not."""

    def is_pot(value: int) -> bool:
        return value > 0 and value & (value - 1) == 0

    for name, (width, height) in mt.TEXTURE_SIZES.items():
        both_pot = is_pot(width) and is_pot(height)
        if name == mt.NON_POWER_OF_TWO:
            assert not both_pot, "the bad variant must not be a power of two"
        else:
            assert both_pot, f"{name} ({width}x{height}) must be a power of two"


def test_fence_alpha_is_binary_and_water_alpha_is_not(tmp_path: Path) -> None:
    """The cutout and translucent cases must be genuinely different, or the material
    recommendation tests in P7 would be testing nothing."""
    paths = mt.generate_textures(tmp_path)

    def alpha_values(path: Path, width: int, height: int) -> set[int]:
        data = path.read_bytes()
        idat = b""
        pos = 8
        while pos < len(data):
            (length,) = struct.unpack_from(">I", data, pos)
            if data[pos + 4 : pos + 8] == b"IDAT":
                idat += data[pos + 8 : pos + 8 + length]
            pos += 12 + length
        raw = zlib.decompress(idat)
        stride = width * 4
        values = set()
        for y in range(height):
            row = raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)]
            values.update(row[3::4])
        return values

    fence_w, fence_h = mt.TEXTURE_SIZES["fence"]
    assert alpha_values(paths["fence"], fence_w, fence_h) == {0, 255}

    water_w, water_h = mt.TEXTURE_SIZES["water"]
    water_alpha = alpha_values(paths["water"], water_w, water_h)
    assert len(water_alpha) > 2
    assert not water_alpha <= {0, 255}, "water must have partial alpha (translucent)"


# --- the generated fixture -------------------------------------------------------


@needs_fixtures
def test_manifest_lists_the_expected_collections_and_objects() -> None:
    manifest = json.loads((GENERATED / "fixture_manifest_good.json").read_text(encoding="utf-8"))
    objects = manifest["objects"]
    assert set(objects) == {"Course", "KCL", "Skybox"}
    assert len(objects["Course"]) == 4, "ring road, grass, fence, water"
    assert len(objects["KCL"]) == 5
    assert len(objects["Skybox"]) == 1


@needs_fixtures
def test_every_kcl_object_carries_a_valid_flag_suffix() -> None:
    """The add-on only exports objects named `*_F####` with uppercase hex digits."""
    manifest = json.loads((GENERATED / "fixture_manifest_good.json").read_text(encoding="utf-8"))
    for name in manifest["objects"]["KCL"]:
        stem, _, flag = name.rpartition("_F")
        assert stem, f"{name} has no _F suffix"
        assert len(flag) == 4, f"{name}: flag must be exactly 4 hex digits"
        assert flag == flag.upper(), f"{name}: flag digits must be uppercase"
        int(flag, 16)  # raises if not hex


@needs_fixtures
def test_course_and_skybox_objects_have_no_kcl_flags() -> None:
    """Visual meshes must be skipped by the KCL exporter, not exported as collision."""
    manifest = json.loads((GENERATED / "fixture_manifest_good.json").read_text(encoding="utf-8"))
    for group in ("Course", "Skybox"):
        for name in manifest["objects"][group]:
            assert "_F" not in name, f"{name} would be picked up by the KCL exporter"


@needs_fixtures
def test_fixture_stays_inside_the_game_coordinate_limit() -> None:
    """MKW_DOMAIN section 4: drivable geometry must stay within +/-131071 game units."""
    manifest = json.loads((GENERATED / "fixture_manifest_good.json").read_text(encoding="utf-8"))
    limit = manifest["game_coord_limit"]
    assert manifest["max_abs_game_coord"] < limit
    for axis_values in (manifest["extent"]["min_game"], manifest["extent"]["max_game"]):
        for value in axis_values:
            assert abs(value) <= limit


@needs_fixtures
def test_bad_variant_uses_the_non_power_of_two_texture() -> None:
    """The warning-test fixture must actually differ from the good one."""
    good = json.loads((GENERATED / "fixture_manifest_good.json").read_text(encoding="utf-8"))
    bad = json.loads((GENERATED / "fixture_manifest_bad.json").read_text(encoding="utf-8"))
    assert good["variant"] == "good" and bad["variant"] == "bad"
    npot_size = bad["textures"][mt.NON_POWER_OF_TWO]["size"]
    assert npot_size == list(mt.TEXTURE_SIZES[mt.NON_POWER_OF_TWO])
    assert (GENERATED / "fixture_track_bad.blend").exists()


@needs_fixtures
def test_both_blend_files_exist_and_are_small_enough_to_commit() -> None:
    """TESTING_STRATEGY section 3 allows a committed copy under 2 MB."""
    for variant in ("good", "bad"):
        blend = GENERATED / f"fixture_track_{variant}.blend"
        assert blend.exists(), blend
        assert blend.stat().st_size < 2 * 1024 * 1024, f"{blend.name} is too large to commit"


# --- the fixture KMP -------------------------------------------------------------


def parse_kmp_sections(path: Path) -> dict[str, int]:
    """Entry count per section, read straight from the binary KMP header."""
    data = path.read_bytes()
    assert data[:4] == b"RKMD", "not a KMP file"
    n_sections, header_len = struct.unpack_from(">HH", data, 8)
    offsets = struct.unpack_from(f">{n_sections}I", data, 0x10)
    counts: dict[str, int] = {}
    for offset in offsets:
        base = header_len + offset
        magic = data[base : base + 4].decode("ascii", "replace")
        (count,) = struct.unpack_from(">H", data, base + 4)
        counts[magic] = count
    return counts


@pytest.mark.skipif(not (GENERATED / "course.kmp").exists(), reason="fixtures not generated")
def test_fixture_kmp_has_the_sections_a_racing_track_needs() -> None:
    counts = parse_kmp_sections(GENERATED / "course.kmp")
    assert counts["KTPT"] == 1, "exactly one start position"
    assert counts["ENPT"] == 4, "enemy route points"
    assert counts["ITPT"] == 4, "item route points"
    assert counts["CKPT"] == 4, "checkpoints"
    assert counts["ENPH"] == counts["ITPH"] == counts["CKPH"] == 1, "one group each"
    assert counts["JGPT"] == 1, "one respawn point"
    assert counts["STGI"] == 1, "stage info"


@pytest.mark.skipif(not (GENERATED / "course.kmp").exists(), reason="fixtures not generated")
def test_fixture_kmp_declares_no_objects() -> None:
    """GOBJ entries would need object files from the user's own game (AGENTS.md rule 7)."""
    assert parse_kmp_sections(GENERATED / "course.kmp")["GOBJ"] == 0


def test_kmp_source_is_committed_and_declares_the_lap_counter() -> None:
    """The KMP text is the real source; the binary is regenerated from it."""
    text = KMP_SOURCE.read_text(encoding="utf-8")
    assert text.startswith("#KMP"), "wkmpt requires the #KMP magic on the first line"
    checkpoints = text.split("[CKPT]")[1].split("[")[0]
    rows = [ln.split() for ln in checkpoints.splitlines() if ln.strip() and ln[0].isspace()]
    data_rows = [r for r in rows if r and r[0].isdigit()]
    assert len(data_rows) == 4, "four checkpoints"
    assert data_rows[0][-3] == "0", "checkpoint 0 must be the lap counter (mode 0)"


@pytest.mark.integration
@pytest.mark.skipif(not WKMPT.exists(), reason="wkmpt not installed; run bootstrap_tools.py")
def test_wkmpt_compiles_the_fixture_kmp_with_only_the_expected_warnings(tmp_path: Path) -> None:
    """Real tool run: the only warnings must be the deferred opening camera (P10-T05)."""
    dest = tmp_path / "course.kmp"
    proc = subprocess.run(  # noqa: S603
        [str(WKMPT), "encode", str(KMP_SOURCE), "--dest", str(dest), "--overwrite"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert dest.exists()

    warnings = [ln.strip() for ln in (proc.stdout + proc.stderr).splitlines() if "WARNING:" in ln]
    assert len(warnings) == 2, "unexpected warnings:\n" + "\n".join(warnings)
    assert all("camera" in w.lower() for w in warnings), warnings
