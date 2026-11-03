"""P4-T06 with the real Wiimm 2.42a: assemble then validate synthetic tracks.

Two synthetic stages: the fixture KCL + KMP alone (three required parts missing), and the
same with stand-in BRRES files for the course, skybox and minimap (complete; Wiimm then
warns about the stand-in minimap). Both are built and checked with the real wszst.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.build.assemble import assemble_step
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildSummary
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import Profile
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.build.validate import ISSUES_FILE, validate_step
from ctstudio.core.project.manifest import BuildSettings, Manifest, ProjectInfo
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.process import CancelToken

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

KEPT = ROOT / "tests" / "fakes" / "recordings" / "wszst" / "2.42a" / "inputs"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(120),
    pytest.mark.skipif(
        not tp.WSZST.is_file() or not tp.WKMPT.is_file(), reason="Requires Wiimm 2.42a"
    ),
]
MANIFEST = Manifest(
    project=ProjectInfo(name="T", slot="castle_course"), build=BuildSettings(auto_add=False)
)


def build(tmp_path: Path, profile: Profile, *extra: str) -> tuple[Path, BuildSummary]:
    root = tmp_path / "Pistë 日本"
    stage = root / ".ctstudio" / "stage"
    stage.mkdir(parents=True)
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(KEPT / name, stage / name)
    for name in extra:
        (stage / name).write_bytes(b"synthetic stand-in")
    tools = {
        tool: ToolLocation(path, "2.42a", "dev", "direct")
        for tool, path in (("wszst", tp.WSZST), ("wkmpt", tp.WKMPT))
    }
    steps = [assemble_step(root, MANIFEST, profile), validate_step(root, MANIFEST, profile)]
    summary = run_build(
        BuildGraph(root, steps),
        BuildCache.load(root),
        BuildRequest(MANIFEST, profile, tools, {"wszst": "2.42a", "wkmpt": "2.42a"}),
        lambda _event: None,
        cancel=CancelToken(),
    )
    return root, summary


def test_real_validate_names_each_missing_part_and_fails_a_release_build(
    tmp_path: Path,
) -> None:
    root, summary = build(tmp_path, "release")
    assert summary.ran == ("assemble",) and summary.failed == ("validate",)
    missing = [i.component for i in summary.issues if i.code == "VALIDATE_PART_MISSING"]
    assert missing == ["course_model", "minimap", "skybox"]
    assert not any(i.code == "WSZST_MISSING_FILE" for i in summary.issues)
    assert {i.code for i in summary.issues} >= {"WSZST_WARNING", "WSZST_HINT", "WSZST_INFO"}
    report = json.loads((root / ISSUES_FILE).read_text(encoding="utf-8"))
    assert report["track"] == "build/castle_course.szs"
    assert len(report["issues"]) == len(summary.issues) - 1  # less the "stops here" reason


def test_real_validate_passes_a_complete_track_with_warnings(tmp_path: Path) -> None:
    parts = ("course_model.brres", "vrcorn_model.brres", "map_model.brres")
    _root, summary = build(tmp_path, "release", *parts)
    assert summary.outcome == "succeeded", summary
    assert summary.ran == ("assemble", "validate")
    assert not any(i.severity == "error" for i in summary.issues)
    assert any("minimap" in i.message for i in summary.issues), "the stand-in minimap"
