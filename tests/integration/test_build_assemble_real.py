"""P4-T05a with the real Wiimm 2.42a: assemble a synthetic stage into ``build/<slot>.szs``.

Fakes cannot prove that real ``wszst create`` output satisfies the ``wszst list`` post-check,
so this builds the generated fixture stage (KCL + KMP) plus a post-effect sub-folder with
each compression, and reads the result back with the real tool. No auto-add library.
"""

from __future__ import annotations

import dataclasses
import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.build.assemble import assemble_step
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.project.manifest import BuildSettings, Compression, Manifest, ProjectInfo
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.wiimm import list_files

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

FIXTURES = ROOT / "tests" / "fixtures" / "generated"
MAGIC = {"best": b"Yaz0", "fast": b"Yaz0", "none": bytes.fromhex("55aa382d")}
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(120),
    pytest.mark.skipif(
        not tp.WSZST.is_file() or not (FIXTURES / "course.kcl").is_file(),
        reason="Requires Wiimm 2.42a and generated fixtures",
    ),
]


@pytest.mark.parametrize("compression", ["best", "fast", "none"])
def test_real_assemble_packs_every_staged_file(tmp_path: Path, compression: Compression) -> None:
    root = tmp_path / "Pistë 日本"
    stage = root / ".ctstudio" / "stage"
    (stage / "posteffect").mkdir(parents=True)
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(FIXTURES / name, stage / name)
    (stage / "posteffect" / "posteffect.bfg").write_bytes(b"synthetic fog settings")
    settings = dataclasses.replace(BuildSettings(), release_compression=compression)
    manifest = Manifest(project=ProjectInfo(name="T", slot="castle_course"), build=settings)
    tools = {"wszst": ToolLocation(tp.WSZST, "2.42a", "dev", "direct")}
    summary = run_build(
        BuildGraph(root, [assemble_step(root, manifest, "release")]),
        BuildCache.load(root),
        BuildRequest(manifest, "release", tools, {"wszst": "2.42a"}),
        lambda _event: None,
        cancel=CancelToken(),
    )
    assert summary.outcome == "succeeded", summary
    szs = root / "build" / "castle_course.szs"
    assert szs.read_bytes()[:4] == MAGIC[compression]
    assert (root / "build" / "castle_course_d.szs").read_bytes() == szs.read_bytes()
    assert list_files(szs, executable=tp.WSZST) == (
        "course.kcl",
        "course.kmp",
        "posteffect/posteffect.bfg",
    )
    assert sorted(p.name for p in (root / "build").iterdir()) == [
        "castle_course.szs",
        "castle_course_d.szs",
    ]
