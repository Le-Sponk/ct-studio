"""Native Windows editor launches through P2-T05g ``open_in``, from a ``dossier é 日本`` folder.

Each installed editor is started on a self-made document; the test then reads Windows'
own view (EnumWindows / tasklist) and kills only the processes it started. Editors that
name the document in their title are checked for it; RiiStudio and KMP Cloud never do,
so only "one new window" is checked there (TOOLS.md "Launch contracts").
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "spikes"))
import s7_native_windows as s7  # type: ignore[reportMissingImports] - spikes path inserted above

from ctstudio.core.tools.editors import open_in

REC = ROOT / "tests" / "fakes" / "recordings"
TOOLS = ROOT / ".tools"
BRAWLCRATE = Path(
    os.environ.get("BRAWLCRATE_EXE", Path.home() / "Desktop" / "BrawlCrate" / "BrawlCrate.exe")
)
EDITORS = [
    ("brawlcrate", BRAWLCRATE, REC / "wszst/2.42a/inputs/map_model.brres", True),
    (
        "riistudio",
        TOOLS / "riistudio" / "RiiStudio.exe",
        REC / "wszst/2.42a/inputs/map_model.brres",
        False,
    ),
    (
        "kmp_editor_lorenzi",
        TOOLS / "s7-lorenzi-win" / "Lorenzi's KMP Editor.exe",
        REC / "wkmpt/2.42a/inputs/course.kmp",
        True,
    ),
    (
        "kmp_cloud",
        TOOLS / "s7-kmp-cloud" / "KMP Cloud.exe",
        REC / "wkmpt/2.42a/inputs/course.kmp",
        False,
    ),
    ("blender", TOOLS / "blender" / "blender.exe", REC / "blender/5.2.2/inputs/good.blend", True),
]
SETTLE_S = 15.0
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(120),
    pytest.mark.skipif(os.name != "nt", reason="native Windows contract; Wine is P2-T05g2"),
]


@pytest.mark.parametrize(
    ("tool", "exe", "source", "names_file"), EDITORS, ids=[e[0] for e in EDITORS]
)
def test_open_in_starts_one_window_for_the_document(
    tool: str, exe: Path, source: Path, names_file: bool, tmp_path: Path
) -> None:
    if not exe.is_file():
        pytest.skip(f"{exe.name} not installed locally")
    folder = tmp_path / "dossier é 日本"
    folder.mkdir()
    document = folder / f"pièce {source.name}"
    shutil.copyfile(source, document)
    before_pids, before_windows = s7.image_pids(exe.name), s7.visible_windows()
    launched = open_in(tool, document, executable=exe)
    try:
        deadline = time.monotonic() + SETTLE_S
        titles: list[str] = []
        mine: set[int] = set()
        while time.monotonic() < deadline:
            mine = s7.image_pids(exe.name) - before_pids
            titles = [
                t
                for h, (pid, t) in s7.visible_windows().items()
                if h not in before_windows and pid in mine
            ]
            if titles and (not names_file or any(document.name in t for t in titles)):
                break
            time.sleep(0.5)
        assert launched.pid in mine
        assert titles, f"{tool} showed no window"
        if names_file:
            assert any(document.name in t.replace("/", "\\") for t in titles), titles
        # The folder is non-ASCII, so only RiiStudio (which cannot load such paths) warns.
        assert len(launched.warnings) == (1 if tool == "riistudio" else 0)
    finally:
        s7.kill_pids((s7.image_pids(exe.name) - before_pids) | {launched.pid})
