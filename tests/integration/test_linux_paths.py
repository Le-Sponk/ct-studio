"""Non-ASCII path behaviour on Linux (P2-T08f): the Linux twin of test_windows_paths.py.

Same probe folders (``latin é`` and ``cjk 日本``) and the same tools as the Windows
measurement: the pinned rszst.exe through Wine (P2-T08d), ABMatt's Linux build and
Wiimm's Linux wszst. Measured on GitHub's ubuntu-latest (UTF-8 locale, wine from apt);
docs/reference/TOOLS.md "Non-ASCII paths on Linux" records the results.
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
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

DAE = REPO / "spikes" / "out" / "s2" / "course_builtin.dae"
GENERATED = REPO / "tests" / "fixtures" / "generated"
FOLDERS = ["latin é", "cjk 日本"]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(180),
    pytest.mark.skipif(os.name == "nt", reason="Linux contract; Windows is test_windows_paths"),
    pytest.mark.skipif(not DAE.is_file(), reason="S2 outputs missing; run spikes/s2_blender.py"),
]
# Each needs_* checks the OS too: pytest reports the nearest mark's reason, so on Windows
# every test skips with the module's "Linux contract" reason.
needs_wine_rszst = pytest.mark.skipif(
    os.name != "nt" and not (tp.RSZST.is_file() and tp.through_wine(tp.RSZST)),
    reason="rszst through Wine missing; run scripts/wine_rszst.py",
)
needs_abmatt = pytest.mark.skipif(
    os.name != "nt" and not tp.ABMATT.is_file(), reason="ABMatt missing; bootstrap"
)
needs_wszst = pytest.mark.skipif(
    os.name != "nt" and not tp.WSZST.is_file(), reason="wszst missing; bootstrap"
)


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
        timeout=150, check=False,
    )  # fmt: skip


def evidence(result: subprocess.CompletedProcess[str]) -> str:
    tail = f"--- stdout\n{result.stdout[-800:]}\n--- stderr\n{result.stderr[-800:]}"
    return f"exit {result.returncode}\n{tail}"


@needs_wine_rszst
@pytest.mark.parametrize("dirname", FOLDERS)
def test_rszst_through_wine_rejects_a_non_ascii_absolute_path(tmp_path: Path, dirname: str) -> None:
    """Wine passes the exe its argv through the Windows ANSI code page, as Windows does."""
    folder = staged(tmp_path, dirname)
    out = folder / "out.brres"

    result = run([str(tp.RSZST), "import-brres", str(folder / "course.dae"), str(out)], folder)

    assert result.returncode == 255, evidence(result)
    assert "FileNotExist" in result.stdout + result.stderr, evidence(result)
    assert not out.exists()


@needs_wine_rszst
@pytest.mark.parametrize("dirname", FOLDERS)
def test_rszst_through_wine_accepts_bare_names_from_a_non_ascii_cwd(
    tmp_path: Path, dirname: str
) -> None:
    """The adapter's workaround holds under Wine: cwd carries the Unicode, argv stays ASCII."""
    folder = staged(tmp_path, dirname)

    result = run([str(tp.RSZST), "import-brres", "course.dae", "out.brres"], folder)

    assert result.returncode == 0, evidence(result)
    assert (folder / "out.brres").read_bytes()[:4] == b"bres"


@needs_abmatt
@pytest.mark.parametrize("dirname", FOLDERS)
def test_abmatt_converts_a_non_ascii_path_cleanly(tmp_path: Path, dirname: str) -> None:
    """Unlike Windows (CJK: file written, then a UnicodeEncodeError), Linux prints UTF-8."""
    folder = staged(tmp_path, dirname)
    out = folder / "course_model.brres"

    result = run([str(tp.ABMATT), "convert", str(folder / "course.dae"), "to", str(out)], folder)

    assert result.returncode == 0, evidence(result)
    assert out.read_bytes()[:4] == b"bres"
    assert "Traceback" not in result.stdout + result.stderr, evidence(result)
    assert str(out) in result.stdout, evidence(result)


@needs_wszst
@pytest.mark.parametrize("dirname", FOLDERS)
def test_wszst_creates_and_checks_an_archive_in_a_non_ascii_folder(
    tmp_path: Path, dirname: str
) -> None:
    folder = tmp_path / dirname / "stage"
    folder.mkdir(parents=True)
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(GENERATED / name, folder / name)
    archive = folder.parent / "track.szs"

    created = run([str(tp.WSZST), "create", str(folder), "--dest", str(archive)], folder.parent)
    assert created.returncode == 0, evidence(created)
    assert archive.read_bytes()[:4] == b"Yaz0"

    listed = run([str(tp.WSZST), "list", str(archive)], folder.parent)
    assert listed.returncode == 0, evidence(listed)
    assert "course.kmp" in listed.stdout, evidence(listed)
    assert dirname in listed.stdout + listed.stderr, evidence(listed)
