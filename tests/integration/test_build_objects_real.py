"""P4-T05b with the real Wiimm 2.42a tools and no auto-add library (synthetic files only).

The KMP is made here from the committed synthetic ``objects.kmp`` (one itembox): decoded
with the real wkmpt, its object row repeated with other ids, and encoded again. Then the real
assemble step must name each object the track lacks, using Wiimm's own object list.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ctstudio.core.build.assemble import assemble_step
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.project.manifest import Manifest, ProjectInfo
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
ROW = "   o0   0x65 "


def _wkmpt(*args: str, cwd: Path) -> None:
    subprocess.run([str(tp.WKMPT), *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


def _kmp_with(folder: Path, ids: list[str]) -> Path:
    """objects.kmp with its one itembox row repeated once per id, as course.kmp."""
    shutil.copyfile(KEPT / "objects.kmp", folder / "objects.kmp")
    _wkmpt("decode", "objects.kmp", "--dest", "objects.txt", cwd=folder)
    text = (folder / "objects.txt").read_text(encoding="utf-8")
    start = text.index(ROW)
    end = text.index("\n", text.index("\n", text.index("\n", start) + 1) + 1) + 1
    row = text[start:end]
    rows = "".join(row.replace("o0   0x65", f"o{i}   {oid}", 1) for i, oid in enumerate(ids))
    (folder / "objects.txt").write_text(text[:start] + rows + text[end:], encoding="utf-8")
    _wkmpt("encode", "objects.txt", "--dest", "course.kmp", "--overwrite", cwd=folder)
    return folder / "course.kmp"


def test_real_tools_name_every_object_the_track_lacks(tmp_path: Path) -> None:
    root = tmp_path / "Pistë 日本"
    stage = root / ".ctstudio" / "stage"
    stage.mkdir(parents=True)
    work = tmp_path / "kmp"
    work.mkdir()
    shutil.copyfile(KEPT / "course.kcl", stage / "course.kcl")
    shutil.copyfile(
        _kmp_with(work, ["0x65", "0x7", "0x65", "0x12d", "0x3ff"]), stage / "course.kmp"
    )
    (stage / "pocha.brres").write_bytes(b"synthetic, supplied by the user")
    manifest = Manifest(project=ProjectInfo(name="T", slot="castle_course"))
    tools = {
        "wszst": ToolLocation(tp.WSZST, "2.42a", "dev", "direct"),
        "wkmpt": ToolLocation(tp.WKMPT, "2.42a", "dev", "direct"),
    }
    summary = run_build(
        BuildGraph(root, [assemble_step(root, manifest, "test")]),
        BuildCache.load(root),
        BuildRequest(manifest, "test", tools, {"wszst": "2.42a", "wkmpt": "2.42a"}),
        lambda _event: None,
        cancel=CancelToken(),
    )
    assert summary.outcome == "succeeded", summary
    assert [i.message for i in summary.issues] == [
        "pocha (object 0x7) needs effect/pocha/rk_pocha.breff, effect/pocha/rk_pocha.breft,"
        " which are not in the track, and no auto-add library is set up.",
        "itembox (object 0x65, placed 2 times) needs itembox.brres, which is not in the track,"
        " and no auto-add library is set up.",
        "The course places object 0x3ff, which is not in Wiimm's object list.",
    ]
    assert (root / "build" / "castle_course.szs").read_bytes()[:4] == b"Yaz0"
