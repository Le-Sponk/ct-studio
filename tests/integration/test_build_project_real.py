"""P4-T07a with the real Wiimm 2.42a: build a synthetic all-manual project end to end.

Every part is the user's own file: the committed synthetic KCL and KMP, stand-in BRRES for
the course, skybox and minimap, and a stand-in post-effect file. CT Studio finds the real
tools in this checkout's ``.tools/`` the way it does for a developer, stages, packs and
checks the track, then a second build skips every step.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import struct
import sys
from pathlib import Path

import pytest

from ctstudio.core.build.project_build import build_project, plan_build
from ctstudio.core.build.validate import ISSUES_FILE
from ctstudio.core.project.manifest import BuildSettings, Manifest, ProjectInfo
from ctstudio.core.tools.process import CancelToken

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

KEPT = ROOT / "tests" / "fakes" / "recordings" / "wszst" / "2.42a" / "inputs"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(180),
    pytest.mark.skipif(
        not tp.WSZST.is_file() or not tp.WKMPT.is_file(), reason="Requires Wiimm 2.42a"
    ),
]
# A BRRES header with no models (as test_magic.brres): enough for the type check and Wiimm.
BRRES = b"bres\xfe\xff\x00\x00" + struct.pack(">IHH", 0x80, 0x10, 1) + b"root" + bytes(0x6C)
POSTFX = b"PBLM" + struct.pack(">I", 0x50) + bytes(0x48)  # as test_magic.postfx
FILES = {
    "course_model": "files/course_model.brres",
    "kcl": "files/course.kcl",
    "minimap": "files/map_model.brres",
    "skybox": "files/vrcorn_model.brres",
    "kmp": "files/course.kmp",
    "posteffect": "files/fx",
}


def project(tmp_path: Path) -> tuple[Path, Manifest]:
    root = tmp_path / "Pistë 日本"
    (root / "files" / "fx").mkdir(parents=True)
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(KEPT / name, root / "files" / name)
    for name in ("course_model.brres", "map_model.brres", "vrcorn_model.brres"):
        (root / "files" / name).write_bytes(BRRES)
    (root / "files" / "fx" / "posteffect.bblm").write_bytes(POSTFX)
    base = Manifest(
        project=ProjectInfo(name="Pistë", slot="castle_course"),
        build=BuildSettings(auto_add=False),
    )
    parts = {
        part: dataclasses.replace(getattr(base.components, part), mode="manual", file=file)
        for part, file in FILES.items()
    }
    return root, dataclasses.replace(base, components=dataclasses.replace(base.components, **parts))


def test_a_manual_project_builds_with_the_real_tools_then_skips(tmp_path: Path) -> None:
    root, manifest = project(tmp_path)
    plan = plan_build(root, manifest, "test")
    assert plan.request.versions == {"wszst": "2.42a", "wkmpt": "2.42a"}
    first = build_project(plan, lambda _e: None, cancel=CancelToken())
    assert first.outcome == "succeeded", first
    assert first.ran[-2:] == ("assemble", "validate") and len(first.ran) == 8
    assert (root / "build" / "castle_course.szs").is_file()
    assert (root / "build" / "castle_course_d.szs").is_file()
    assert not any(i.code == "VALIDATE_PART_MISSING" for i in first.issues)
    assert json.loads((root / ISSUES_FILE).read_text(encoding="utf-8"))["issues"]
    again = build_project(plan_build(root, manifest, "test"), lambda _e: None, cancel=CancelToken())
    assert again.ran == () and len(again.skipped) == 8
    assert again.issues == first.issues, "found before, still true"
