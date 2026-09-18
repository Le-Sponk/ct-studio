"""Integration tests for the BRRES backend bake-off (P0-T06b, spike S3b).

These pin the behaviour ADR-004 and the P5 `BrresBackend` adapter depend on:
which backend can name an MDL0, which can read the other's output, and which
material/texture controls actually take effect.

The probe runs once per session (a few seconds) and the tests assert against its
recorded findings.

Run: uv run python -m pytest tests/integration -m integration
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ABMATT = REPO_ROOT / ".tools" / "abmatt" / "bin" / "abmatt"
RSZST = REPO_ROOT / ".tools" / "riistudio-build-pinned" / "source" / "cli" / "rszst"
WSZST = REPO_ROOT / ".tools" / "wiimms-szs-tools" / "bin" / "wszst"
DAE = REPO_ROOT / "spikes" / "out" / "s2" / "course_builtin.dae"
DRIVER = REPO_ROOT / "spikes" / "s3_backend_bakeoff.py"
FINDINGS = REPO_ROOT / "spikes" / "out" / "s3b" / "s3b_findings.json"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(600),
    pytest.mark.skipif(not ABMATT.exists(), reason="ABMatt missing; run bootstrap_tools.py"),
    pytest.mark.skipif(not RSZST.exists(), reason="build rszst using the S3a recipe in SPIKES.md"),
    pytest.mark.skipif(not WSZST.exists(), reason="Wiimms tools missing; run bootstrap_tools.py"),
    pytest.mark.skipif(not DAE.exists(), reason="S2 outputs missing; run spikes/s2_blender.py"),
]


@pytest.fixture(scope="module")
def findings() -> dict:
    proc = subprocess.run(  # noqa: S603 - local probe, argv only
        [sys.executable, str(DRIVER)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert FINDINGS.exists(), (
        f"probe wrote no findings:\n{proc.stdout[-2000:]}\n{proc.stderr[-1000:]}"
    )
    return json.loads(FINDINGS.read_text(encoding="utf-8"))


def backend(findings: dict, name: str) -> dict:
    for record in findings["backends"]:
        if record["backend"] == name:
            return record
    raise AssertionError(f"no backend {name!r} in findings")


def test_both_backends_import_the_same_dae(findings: dict) -> None:
    for name in ("rszst", "abmatt"):
        record = backend(findings, name)
        assert record["exit_code"] == 0, name
        assert record["bytes"] > 0, name
        assert record["mdl0_name"] == "course", name


def test_both_backends_emit_all_four_textures(findings: dict) -> None:
    for name in ("rszst", "abmatt"):
        assert sorted(backend(findings, name)["textures"]) == ["fence", "grass", "road", "water"]


def test_abmatt_generates_more_mipmaps_by_default(findings: dict) -> None:
    """Defaults differ, so the adapter must set this explicitly rather than inherit it."""
    rszst_road = backend(findings, "rszst")["textures"]["road"]["mipmaps"]
    abmatt_road = backend(findings, "abmatt")["textures"]["road"]["mipmaps"]
    assert int(abmatt_road) > int(rszst_road)


def test_rszst_names_the_model_with_a_flag(findings: dict) -> None:
    record = findings["model_naming"]["rszst_model_name_flag"]
    assert record["exit_code"] == 0
    assert record["mdl0_name"] == "vrcorn"


def test_abmatt_takes_the_model_name_from_the_source_filename(findings: dict) -> None:
    """ABMatt has no model-name flag: the DAE's stem prefix decides the MDL0 name."""
    record = findings["model_naming"]["abmatt_name_from_source_stem"]
    assert record["exit_code"] == 0
    assert record["mdl0_name"] == "vrcorn"


def test_abmatt_refuses_a_slot_destination_that_contradicts_the_source_name(
    findings: dict,
) -> None:
    """`course*.dae` -> `map_model.brres` fails; the adapter must rename the source."""
    record = findings["model_naming"]["abmatt_stem_destination_mismatch"]
    assert record["exit_code"] != 0
    assert record["wrote_file"] is False
    assert "does not match" in record["message"]


def test_abmatt_can_read_an_rszst_brres(findings: dict) -> None:
    record = findings["interoperability"]["abmatt_reads_rszst"]
    assert record["exit_code"] == 0
    assert record["saw_materials"] is True


def test_rszst_cannot_read_an_abmatt_brres(findings: dict) -> None:
    """The one-way wall that decides the backend order in ADR-004."""
    record = findings["interoperability"]["rszst_reads_abmatt"]
    assert record["exit_code"] != 0
    assert record["wrote_json"] is False
    assert "quantization" in record["error"]


def test_rszst_json_round_trip_works(findings: dict) -> None:
    record = findings["interoperability"]["rszst_json_round_trip"]
    assert record["to_json_exit"] == 0
    assert record["to_brres_exit"] == 0
    assert record["json_bytes"] > 0
    assert record["brres_bytes"] > 0


def test_abmatt_inline_command_flag_is_unusable_for_multi_word_commands(
    findings: dict,
) -> None:
    """`-c 'set material ...'` gets mangled; a command file is the supported path."""
    assert findings["material_control"]["abmatt_inline_command_exit"] != 0
    assert findings["material_control"]["abmatt_command_file_exit"] == 0
    assert findings["material_control"]["abmatt_xlu_applied"] is True


def test_abmatt_tex0_format_change_is_a_silent_no_op(findings: dict) -> None:
    """Exits 0 and writes the file, but the stored format is unchanged."""
    assert findings["material_control"]["abmatt_tex0_format_exit"] == 0
    assert findings["material_control"]["abmatt_tex0_format_changed"] is False


def test_rszst_mipmaps_flag_needs_min_mip_lowered(findings: dict) -> None:
    """`--mipmaps` alone changes nothing at the default --min-mip 32."""
    counts = findings["material_control"]["rszst_mipmap_counts"]
    assert counts["--mipmaps"] == counts["default"]
    assert int(counts["--mipmaps --min-mip 8"]) > int(counts["default"])


@pytest.mark.parametrize("name", ["rszst", "abmatt"])
def test_either_backend_packs_into_a_valid_track(findings: dict, name: str) -> None:
    """Only the two known fixture camera warnings; no ERROR marker (S1 rule)."""
    record = findings["packs_into_a_track"][name]
    assert record["create_exit"] == 0
    assert record["szs_bytes"] > 0
    assert record["has_error_marker"] is False
    assert len(record["warnings"]) == 2
    assert all("camera" in w for w in record["warnings"])
