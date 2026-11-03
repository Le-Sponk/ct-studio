"""Auto-add with a library built from the user's own game files (``realdata``, HC1).

Needs ``local_fixtures/auto-add/`` built with
``wszst autoadd <your Race/Course folder> --DEST local_fixtures/auto-add`` (see
``local_fixtures/README.md``). Skips when it is absent, so CI never needs, sees or
uploads game content. Nothing read here is written into the repository.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.build.assemble import assemble_step
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import LogLine
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.wiimm import create_szs, list_files
from ctstudio.core.tools.wiimm_autoadd import autoadd_verify

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

LIBRARY = ROOT / "local_fixtures" / "auto-add"
KEPT = ROOT / "tests" / "fakes" / "recordings" / "wszst" / "2.42a" / "inputs"
pytestmark = [
    pytest.mark.realdata,
    pytest.mark.integration,
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        os.name != "nt" or not tp.WSZST.is_file() or not LIBRARY.is_dir(),
        reason="Requires native Windows Wiimm 2.42a and local_fixtures/auto-add/",
    ),
]


def test_own_library_is_usable_and_supplies_the_missing_object(tmp_path: Path) -> None:
    library = autoadd_verify(LIBRARY, executable=tp.WSZST)
    assert library.unusable_reason() is None, library.unusable_reason()
    assert "BRRES itembox.brres" in library.found
    stage = tmp_path / "stage"
    stage.mkdir()
    shutil.copyfile(KEPT / "course.kcl", stage / "course.kcl")
    shutil.copyfile(KEPT / "objects.kmp", stage / "course.kmp")
    plain = create_szs(stage, tmp_path / "plain.szs", executable=tp.WSZST)
    added = create_szs(stage, tmp_path / "added.szs", executable=tp.WSZST, auto_add=library)
    assert added.stat().st_size > plain.stat().st_size


def test_the_build_auto_adds_from_the_own_library_and_warns_about_nothing(tmp_path: Path) -> None:
    """P4-T05b at HC1: the assemble step checks the library, passes --auto-add, no warnings."""
    root = tmp_path / "project"
    stage = root / ".ctstudio" / "stage"
    stage.mkdir(parents=True)
    shutil.copyfile(KEPT / "course.kcl", stage / "course.kcl")
    shutil.copyfile(KEPT / "objects.kmp", stage / "course.kmp")
    manifest = Manifest(project=ProjectInfo(name="T", slot="castle_course"))
    tools = {
        "wszst": ToolLocation(tp.WSZST, "2.42a", "dev", "direct"),
        "wkmpt": ToolLocation(tp.WKMPT, "2.42a", "dev", "direct"),
    }
    lines: list[str] = []
    summary = run_build(
        BuildGraph(root, [assemble_step(root, manifest, "test", LIBRARY)]),
        BuildCache.load(root),
        BuildRequest(manifest, "test", tools, {"wszst": "2.42a", "wkmpt": "2.42a"}),
        lambda event: lines.append(event.text) if isinstance(event, LogLine) else None,
        cancel=CancelToken(),
    )
    assert summary.outcome == "succeeded" and summary.issues == (), summary
    assert any("with auto-add" in line for line in lines), lines
    szs = root / "build" / "castle_course.szs"
    assert "itembox.brres" in list_files(szs, executable=tp.WSZST)
