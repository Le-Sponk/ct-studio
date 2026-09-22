"""Integration tests for the headless Blender export path (P0-T05, spike S2).

These pin the add-on entry points the P6 bridge will depend on: operator names,
arguments, stdout markers and the preconditions that are easy to get wrong
(ABMatt on PATH, materials on collision meshes).

Running Blender takes ~2 s, so the whole probe runs once per session and the tests
assert against its recorded findings.

Run: uv run python -m pytest tests/integration -m integration
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BLENDER = REPO_ROOT / ".tools" / "blender" / "blender"
ADDON = REPO_ROOT / "vendor" / "blender-mkw-utilities" / "__init__.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "generated" / "fixture_track_good.blend"
DRIVER = REPO_ROOT / "spikes" / "s2_blender.py"
OUT = REPO_ROOT / "spikes" / "out" / "s2"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        not BLENDER.exists(), reason="Blender not installed; run bootstrap_tools.py"
    ),
    pytest.mark.skipif(not ADDON.exists(), reason="add-on submodule not checked out"),
    pytest.mark.skipif(not FIXTURE.exists(), reason="fixtures not generated"),
]


@pytest.fixture(scope="module")
def findings() -> dict:
    """Run the export probe once, then assert against what it recorded.

    The stale-artefact trap: `spikes/out/` is gitignored and survives between
    sessions, so a findings file from a previous run will satisfy these tests
    even when the probe is broken or cannot start. Delete it first and check the
    exit code, so what is asserted is always what this run produced.
    """
    path = OUT / "s2_findings.json"
    path.unlink(missing_ok=True)
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(DRIVER)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(REPO_ROOT),
        check=False,
    )
    detail = f"exit={proc.returncode}\n{proc.stdout[-2000:]}\n{proc.stderr[-1000:]}"
    assert proc.returncode == 0, f"probe failed:\n{detail}"
    assert path.exists(), f"probe wrote no findings:\n{detail}"
    return json.loads(path.read_text(encoding="utf-8"))


def by_name(findings: dict, prefix: str) -> dict:
    for record in findings["exports"]:
        if record["name"].startswith(prefix):
            return record
    names = [e["name"] for e in findings["exports"]]
    raise AssertionError(f"no export named {prefix!r} in {names}")


def test_addon_registers_from_a_plain_directory(findings: dict) -> None:
    """The bridge registers the add-on from vendor/ without installing it."""
    assert findings["addon"]["registered"] is True
    assert findings["addon"]["bl_info_version"], "bl_info version should be readable"


def test_blender_runs_headless(findings: dict) -> None:
    assert findings["context_notes"]["background"] is True


def test_every_export_operator_the_bridge_needs_exists(findings: dict) -> None:
    for operator in ("kcl.export", "export.autodesk_dae", "export.minimap", "export_scene.objkcl"):
        assert operator in findings["export_operators"], operator


def test_all_exports_succeed_headlessly(findings: dict) -> None:
    """The whole point of S2: no operator needs a GUI context."""
    failed = [e["name"] for e in findings["exports"] if not e["ok"]]
    assert not failed, f"these exports failed headlessly: {failed}"


def test_kcl_export_produces_a_file(findings: dict) -> None:
    record = by_name(findings, "kcl.export unBeanCorner=LOWER")
    assert record["output_exists"] and record["output_bytes"] > 0


def test_unbean_modes_change_the_output(findings: dict) -> None:
    """LOWER and NONE give the same byte count, so the mode must be compared by hash."""
    assert findings["kcl_unbean_differs"] is True, (
        "kclExportUnBeanCorner had no effect; the bridge would be passing a dead option"
    )


def test_dae_export_writes_textures_beside_the_file(findings: dict) -> None:
    """S3 needs the textures next to the DAE for the BRRES import to find them."""
    record = by_name(findings, "export.autodesk_dae method=BUILTIN")
    assert record["output_exists"] and record["output_bytes"] > 0
    assert findings["dae_sidecar_textures"], "no PNGs were copied next to the DAE"


def test_dae_auto_falls_back_to_the_builtin_writer_on_linux(findings: dict) -> None:
    """FbxConverter is a Windows binary, so AUTO must equal BUILTIN here."""
    assert findings["dae_auto_equals_builtin"] is True


def test_minimap_export_produces_a_brres(findings: dict) -> None:
    """Needs ABMatt on PATH and materials on every mesh; both are easy to get wrong."""
    record = by_name(findings, "export.minimap")
    assert record["ok"], record.get("error")
    assert record["output_bytes"] > 0
