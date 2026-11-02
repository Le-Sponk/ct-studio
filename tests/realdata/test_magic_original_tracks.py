"""P3-T05 on the user's own game files (``realdata``; local only, never on CI).

Needs ``local_fixtures/mkwii/files/Race/Course/`` (the user's own disc copy, git-ignored)
and Wiimm's tools. Extracts every track into a temporary folder, checks that each file kind
CT Studio sniffs is recognised, and deletes the copies. Nothing is written into the repo.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

import pytest

from ctstudio.core.formats.magic import FileKind, identify
from ctstudio.core.tools.process import run

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

COURSES = ROOT / "local_fixtures" / "mkwii" / "files" / "Race" / "Course"
EXPECTED = {
    ".brres": FileKind.BRRES,
    ".kcl": FileKind.KCL,
    ".kmp": FileKind.KMP,
    ".bblm": FileKind.BBLM,
    ".bdof": FileKind.BDOF,
    ".blight": FileKind.BLIGHT,
    ".blmap": FileKind.BLMAP,
}
pytestmark = [
    pytest.mark.realdata,
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.timeout(900),
    pytest.mark.skipif(
        os.name != "nt" or not tp.WSZST.is_file() or not COURSES.is_dir(),
        reason="Requires native Windows Wiimm 2.42a and local_fixtures/mkwii/",
    ),
]


def test_every_original_track_and_its_files_are_recognised(tmp_path: Path) -> None:
    tracks = sorted(COURSES.glob("*.szs"))
    assert len(tracks) >= 42
    assert {identify(track) for track in tracks} == {FileKind.YAZ0}
    wrong: list[str] = []
    seen: Counter[str] = Counter()
    for track in tracks:
        out = tmp_path / track.stem
        argv = [str(tp.WSZST), "extract", "-q", str(track), "-d", str(out)]
        run(argv, cwd=tmp_path, timeout=120)
        for path in out.rglob("*"):
            want = EXPECTED.get(path.suffix.lower())
            if want is not None and path.is_file():
                seen[path.suffix.lower()] += 1
                if identify(path) is not want:
                    wrong.append(f"{track.stem}/{path.relative_to(out).as_posix()}")
    assert not wrong, wrong
    assert set(seen) == set(EXPECTED), seen
