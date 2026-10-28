"""Windows-native Wiimm 2.42a auto-add against the real tool, with synthetic inputs only.

The library here is a synthetic BRRES under the itembox name, so Wiimm must call it
invalid and the guard must refuse it. Proof with a real library lives in
``tests/realdata/test_wiimm_autoadd_library.py`` (the user's own files, never committed).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.tools.wiimm import AutoAddUnavailable, WiimmError, create_szs
from ctstudio.core.tools.wiimm_autoadd import autoadd_create, autoadd_status, autoadd_verify

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

KEPT = ROOT / "tests" / "fakes" / "recordings" / "wszst" / "2.42a" / "inputs"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(120),
    pytest.mark.skipif(
        os.name != "nt" or not tp.WSZST.is_file(),
        reason="Requires native Windows Wiimm 2.42a",
    ),
]


@pytest.fixture
def work(tmp_path: Path) -> Path:
    folder = tmp_path / "auto add é"
    folder.mkdir()
    stage = folder / "stage"
    stage.mkdir()
    shutil.copyfile(KEPT / "course.kcl", stage / "course.kcl")
    shutil.copyfile(KEPT / "objects.kmp", stage / "course.kmp")
    return folder


def test_real_status_names_the_given_library(work: Path) -> None:
    (work / "lib").mkdir()
    status = autoadd_status(work / "lib", executable=tp.WSZST)
    assert (status.current, status.search_paths) == ("lib", ("lib",))


def test_real_build_verify_and_refuse_a_synthetic_library(work: Path) -> None:
    shutil.copyfile(KEPT / "map_model.brres", work / "stage" / "itembox.brres")
    course = work / "Course"
    course.mkdir()
    create_szs(work / "stage", course / "beginner_course.szs", executable=tp.WSZST)
    (work / "stage" / "itembox.brres").unlink()
    build = autoadd_create(course, work / "newlib", executable=tp.WSZST)
    assert build.analyzed == ("Course/beginner_course.szs",) and len(build.added) == 1
    assert autoadd_create(course, work / "newlib", executable=tp.WSZST).added == ()
    library = autoadd_verify(work / "newlib", executable=tp.WSZST)
    assert library.invalid == ("BRRES itembox.brres",)
    with pytest.raises(AutoAddUnavailable, match="not the originals"):
        create_szs(work / "stage", work / "a.szs", executable=tp.WSZST, auto_add=library)
    assert not (work / "a.szs").exists()


def test_real_build_from_names_wiimm_skips_is_failure(work: Path) -> None:
    (work / "Course").mkdir()
    shutil.copyfile(KEPT / "course.kcl", work / "Course" / "my_track.szs")
    with pytest.raises(WiimmError, match="no track archives"):
        autoadd_create(work / "Course", work / "newlib", executable=tp.WSZST)
    assert not (work / "newlib").exists()


def test_real_empty_library_is_refused(work: Path) -> None:
    (work / "empty").mkdir()
    library = autoadd_verify(work / "empty", executable=tp.WSZST)
    assert library.found == () and len(library.missed) == 477
    with pytest.raises(AutoAddUnavailable, match="none of the auto-add files"):
        create_szs(work / "stage", work / "a.szs", executable=tp.WSZST, auto_add=library)
