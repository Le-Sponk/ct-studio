"""Windows-native Wiimm 2.42a checks: fake replay cannot prove real findings."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from ctstudio.core.tools.wiimm import WiimmCheckError, check

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

FIXTURES = ROOT / "tests" / "fixtures" / "generated"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(120),
    pytest.mark.skipif(
        os.name != "nt" or not tp.WSZST.is_file() or not (FIXTURES / "course.kcl").is_file(),
        reason="Requires native Windows Wiimm 2.42a and generated fixtures",
    ),
]


@pytest.fixture
def real_sources(tmp_path: Path) -> tuple[Path, Path]:
    work = tmp_path / "check é"
    work.mkdir()
    stage = work / "stage"
    stage.mkdir()
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(FIXTURES / name, stage / name)
    archive = work / "t.szs"
    proc = subprocess.run(  # noqa: S603 - pinned native tool, no shell
        [str(tp.WSZST), "create", stage.name, "--dest", archive.name],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0 and archive.is_file(), proc.stdout + proc.stderr
    return stage, archive


@pytest.mark.parametrize("kind", ["stage", "archive"])
def test_real_check_reports_warnings_despite_exit_two(
    real_sources: tuple[Path, Path], kind: str
) -> None:
    source = real_sources[0] if kind == "stage" else real_sources[1]
    issues = check(source, executable=tp.WSZST)
    assert Counter(issue.severity for issue in issues) == {"warning": 5, "hint": 2, "info": 1}
    assert {issue.file for issue in issues if issue.code == "WSZST_MISSING_FILE"} == {
        Path("course_model.brres"),
        Path("map_model.brres"),
        Path("vrcorn_model.brres"),
    }


def test_real_empty_stage_and_archive_are_clean(tmp_path: Path) -> None:
    work = tmp_path / "empty é"
    work.mkdir()
    stage = work / "empty"
    stage.mkdir()
    assert check(stage, executable=tp.WSZST) == []
    archive = work / "empty.szs"
    proc = subprocess.run(  # noqa: S603 - pinned native tool, no shell
        [str(tp.WSZST), "create", stage.name, "--dest", archive.name],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0 and archive.is_file(), proc.stdout + proc.stderr
    assert check(archive, executable=tp.WSZST) == []


def test_real_check_corrupt_exit_zero_and_missing_exit_nonzero(tmp_path: Path) -> None:
    bad = tmp_path / "junk.szs"
    bad.write_bytes(b"not a track file\n" * 4)
    with pytest.raises(WiimmCheckError) as corrupt:
        check(bad, executable=tp.WSZST)
    assert (corrupt.value.error_code, corrupt.value.exit_code) == (39, 0)
    with pytest.raises(WiimmCheckError) as missing:
        check(tmp_path / "missing.szs", executable=tp.WSZST)
    assert (missing.value.error_code, missing.value.exit_code) == (78, 78)
