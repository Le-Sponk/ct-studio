"""Non-ASCII path contracts on native Windows (P0-T13); Linux is unmeasured (STATUS gaps).

rszst and RiiStudio read argv through the ANSI code page, so an absolute path with any
non-ASCII character (Latin-1 included, on a cp850/cp1252 system) is mangled before the
tool sees it. The adapter workaround measured here: run rszst with the file's directory
as cwd and pass bare file names. ABMatt writes its file but crashes printing a CJK path.
Evidence: docs/dev/SPIKES.md S7 "Native Windows".
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import tool_paths as tp

DAE = REPO / "spikes" / "out" / "s2" / "course_builtin.dae"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(120),
    pytest.mark.skipif(os.name != "nt", reason="native Windows contract; Linux is unmeasured"),
    pytest.mark.skipif(not DAE.is_file(), reason="S2 outputs missing; run spikes/s2_blender.py"),
]
needs_rszst = pytest.mark.skipif(not tp.RSZST.is_file(), reason="bootstrap --only riistudio")
needs_abmatt = pytest.mark.skipif(not tp.ABMATT.is_file(), reason="ABMatt missing; bootstrap")


def staged(tmp_path: Path, dirname: str) -> Path:
    folder = tmp_path / dirname
    folder.mkdir()
    for texture in DAE.parent.glob("*.png"):
        shutil.copyfile(texture, folder / texture.name)
    shutil.copyfile(DAE, folder / "course.dae")
    return folder


def run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = tp.tools_env(tp.WIIMMS_BIN, tp.ABMATT_BIN)
    return subprocess.run(  # noqa: S603 - local tool, argv list
        argv, cwd=cwd, env=env, capture_output=True, text=True, errors="replace",
        timeout=100, check=False,
    )  # fmt: skip


@needs_rszst
@pytest.mark.parametrize("dirname", ["latin é", "cjk 日本"])
def test_rszst_rejects_a_non_ascii_absolute_path(tmp_path: Path, dirname: str) -> None:
    folder = staged(tmp_path, dirname)
    out = folder / "out.brres"

    result = run([str(tp.RSZST), "import-brres", str(folder / "course.dae"), str(out)], folder)

    assert result.returncode == tp.EXIT_MINUS_ONE
    assert "FileNotExist" in result.stdout + result.stderr
    assert not out.exists()


@needs_rszst
@pytest.mark.parametrize("dirname", ["latin é", "cjk 日本"])
def test_rszst_accepts_bare_names_from_a_non_ascii_cwd(tmp_path: Path, dirname: str) -> None:
    """The adapter workaround: cwd carries the Unicode, argv stays ASCII."""
    folder = staged(tmp_path, dirname)

    result = run([str(tp.RSZST), "import-brres", "course.dae", "out.brres"], folder)

    assert result.returncode == 0, result.stdout[-500:]
    assert (folder / "out.brres").stat().st_size > 0


@needs_abmatt
def test_abmatt_writes_a_cjk_path_but_crashes_reporting_it(tmp_path: Path) -> None:
    """Exit 0 and a file on disk, yet a traceback: output is not a success signal."""
    folder = staged(tmp_path, "cjk 日本")
    out = folder / "course_model.brres"

    result = run([str(tp.ABMATT), "convert", str(folder / "course.dae"), "to", str(out)], folder)

    assert result.returncode == 0
    assert out.is_file()
    assert "UnicodeEncodeError" in result.stdout + result.stderr
