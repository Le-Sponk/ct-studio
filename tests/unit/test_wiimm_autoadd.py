"""P2-T05d: Wiimm auto-add status/build/verify and the ``create --auto-add`` guard.

Every recording here uses synthetic inputs: the fixture stage, a KMP with one itembox
object and a synthetic BRRES under the itembox name. No game content is involved.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ctstudio.core.errors import ParseError

ROOT = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a"
INPUTS = ROOT / "inputs"


def _stdout(case: str) -> str:
    rows = json.loads((ROOT / "windows-ops.json").read_text(encoding="utf-8"))
    return next(str(row["stdout"]) for row in rows if row["case"] == case)


def _synthetic_library(tmp_path: Path) -> Path:
    lib = tmp_path / "lib"
    lib.mkdir()
    shutil.copyfile(INPUTS / "map_model.brres", lib / "itembox.brres")
    return lib


def _object_stage(tmp_path: Path) -> Path:
    stage = tmp_path / "stage"
    stage.mkdir()
    shutil.copyfile(INPUTS / "course.kcl", stage / "course.kcl")
    shutil.copyfile(INPUTS / "objects.kmp", stage / "course.kmp")
    return stage


# --- parsers on the real recorded output --------------------------------------------------


def test_parse_status_paths() -> None:
    from ctstudio.core.tools.wiimm_autoadd import parse_autoadd_status

    status = parse_autoadd_status(_stdout("autoadd status"))
    assert status.current == "/usr/bin/auto-add"
    assert status.search_paths == ("/usr/bin/auto-add",)


@pytest.mark.parametrize(
    "text",
    [
        "\nSEARCH PATH[0]: lib\n",  # no current path
        "\nCURRENT AUTO-ADD PATH: lib\n  SEARCH PATH[1]: lib\n",  # index gap
    ],
)
def test_parse_status_refuses_malformed(text: str) -> None:
    from ctstudio.core.tools.wiimm_autoadd import parse_autoadd_status

    with pytest.raises(ParseError):
        parse_autoadd_status(text)


def test_parse_build_lists_analyzed_archives_and_added_files() -> None:
    from ctstudio.core.tools.wiimm_autoadd import parse_autoadd_build

    build = parse_autoadd_build(_stdout("autoadd build"))
    assert build.library == "newlib"
    assert build.analyzed == ("Course/beginner_course.szs",)
    assert build.added == ("newlib/itembox.brres",)
    again = parse_autoadd_build(_stdout("autoadd build again"))
    assert (again.analyzed, again.added) == (("Course/beginner_course.szs",), ())
    unreadable = parse_autoadd_build(_stdout("autoadd build missing source"))
    assert (unreadable.analyzed, unreadable.added) == ((), ())


def test_parse_verify_of_a_library_with_an_invalid_file() -> None:
    from ctstudio.core.tools.wiimm_autoadd import parse_autoadd_verify

    lib = parse_autoadd_verify(_stdout("autoadd verify synthetic"), Path("lib"))
    assert lib.found == ("BRRES itembox.brres",)
    assert lib.invalid == ("BRRES itembox.brres",)
    assert len(lib.missed) == 476
    assert "itembox.brres" in str(lib.unusable_reason())


def test_parse_verify_of_an_empty_library() -> None:
    from ctstudio.core.tools.wiimm_autoadd import parse_autoadd_verify

    lib = parse_autoadd_verify(_stdout("autoadd verify empty"), Path("empty"))
    assert (lib.found, lib.invalid, len(lib.missed)) == ((), (), 477)
    assert "none" in str(lib.unusable_reason())


def test_a_library_with_valid_files_and_no_invalid_ones_is_usable() -> None:
    from ctstudio.core.tools.wiimm import AutoAddLibrary

    lib = AutoAddLibrary(Path("lib"), found=("BRRES a.brres",), missed=("KCL b.kcl",), invalid=())
    assert lib.unusable_reason() is None


@pytest.mark.parametrize(
    "mangle",
    [
        lambda text: text.replace("=> 476 of 496 files missed.", "=> 475 of 496 files missed."),
        lambda text: text.replace("LIST OF MISSED FILES IN lib", "LIST OF MISSING FILES IN lib"),
        lambda text: text.replace("=> 1 of 496 files found.", "=> 2 of 496 files found."),
        lambda text: text.replace("  => 1 of 496 files invalid.\n", ""),
        lambda text: text.replace("=> 1 of 496 files invalid.", "=> 1 of 495 files invalid."),
        lambda text: text.replace("\nLIST OF FILES IN lib", "\nunexpected\nLIST OF FILES IN lib"),
        lambda text: text.replace("  => 476 of 496", "unexpected\n  => 476 of 496"),
    ],
    ids=[
        "missed count",
        "missed header",
        "found count",
        "invalid count missing",
        "totals",
        "preamble",
        "in section",
    ],
)
def test_parse_verify_refuses_inconsistent_reports(mangle) -> None:
    from ctstudio.core.tools.wiimm_autoadd import parse_autoadd_verify

    text = mangle(_stdout("autoadd verify synthetic"))
    with pytest.raises(ParseError):
        parse_autoadd_verify(text, Path("lib"))


# --- adapters through the fakes -----------------------------------------------------------


def test_status_via_fake(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm_autoadd import autoadd_status

    lib = _synthetic_library(tmp_path)
    status = autoadd_status(lib)
    assert (status.current, status.search_paths) == ("lib", ("lib",))
    assert fake_tools_path.calls()[0]["argv"] == ["autoadd", "--dest", "lib"]


def test_verify_via_fake_and_missing_library(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError
    from ctstudio.core.tools.wiimm_autoadd import autoadd_verify

    lib = autoadd_verify(_synthetic_library(tmp_path))
    assert lib.path == tmp_path / "lib" and lib.invalid == ("BRRES itembox.brres",)
    assert fake_tools_path.calls()[0]["argv"] == ["autoadd", "--dest", "lib", "-vv"]
    with pytest.raises(WiimmError) as caught:
        autoadd_verify(tmp_path / "nolib")
    assert (caught.value.error_code, caught.value.exit_code) == (84, 84)


def test_autoadd_create_builds_then_reports_nothing_new(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import create_szs
    from ctstudio.core.tools.wiimm_autoadd import autoadd_create

    stage = _object_stage(tmp_path)
    shutil.copyfile(INPUTS / "map_model.brres", stage / "itembox.brres")
    course = tmp_path / "Course"
    course.mkdir()
    create_szs(stage, course / "beginner_course.szs")
    build = autoadd_create(course, tmp_path / "newlib")
    assert build.analyzed == ("Course/beginner_course.szs",)
    assert build.added == ((tmp_path / "newlib" / "itembox.brres").as_posix(),)
    assert (tmp_path / "newlib" / "itembox.brres").read_bytes()[:4] == b"bres"
    again = autoadd_create(course, tmp_path / "newlib")
    assert again.added == ()
    assert fake_tools_path.calls()[-1]["argv"] == [
        "autoadd",
        "Course",
        "--DEST",
        str(tmp_path / "newlib"),
    ]


def test_autoadd_create_without_track_archives_is_failure(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError
    from ctstudio.core.tools.wiimm_autoadd import autoadd_create

    (tmp_path / "empty").mkdir()
    with pytest.raises(WiimmError, match="no track archives"):
        autoadd_create(tmp_path / "empty", tmp_path / "newlib")
    with pytest.raises(WiimmError) as caught:
        autoadd_create(tmp_path / "NoSuch", tmp_path / "newlib")
    assert caught.value.error_code == 78


def test_create_refuses_an_unusable_library_before_running(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import AutoAddUnavailable, create_szs
    from ctstudio.core.tools.wiimm_autoadd import autoadd_verify

    lib = autoadd_verify(_synthetic_library(tmp_path))
    calls = len(fake_tools_path.calls())
    with pytest.raises(AutoAddUnavailable, match=r"itembox\.brres"):
        create_szs(_object_stage(tmp_path), tmp_path / "a.szs", auto_add=lib)
    assert len(fake_tools_path.calls()) == calls
    assert not (tmp_path / "a.szs").exists()


def test_create_with_a_usable_library_passes_its_path(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import AutoAddLibrary, create_szs

    lib_path = _synthetic_library(tmp_path)
    # A stand-in proof object: the fake library's content is synthetic, not usable in game.
    lib = AutoAddLibrary(lib_path, found=("BRRES itembox.brres",), missed=(), invalid=())
    out = create_szs(_object_stage(tmp_path), tmp_path / "a.szs", auto_add=lib)
    assert out.read_bytes()[:4] == b"Yaz0"
    argv = fake_tools_path.calls()[0]["argv"]
    assert argv[-3:] == ["--auto-add", "--autoadd-path", str(lib_path)]


# --- the fake replays only the recorded synthetic world -----------------------------------


def _run_fake(fake_tools_path, cwd: Path, *argv: str) -> subprocess.CompletedProcess[bytes]:
    exe = fake_tools_path.resolve("wszst")
    # argv list of our own installed fake
    return subprocess.run([str(exe), *argv], cwd=cwd, capture_output=True, check=False)  # noqa: S603


def test_fake_refuses_an_unrecorded_library(fake_tools_path, tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "itembox.brres").write_bytes(b"bres" + b"\0" * 60)
    result = _run_fake(fake_tools_path, tmp_path, "autoadd", "--dest", "lib", "-vv")
    assert (result.returncode, result.stdout) == (121, b"")


def test_fake_refuses_auto_add_with_an_unrecorded_stage(fake_tools_path, tmp_path: Path) -> None:
    _synthetic_library(tmp_path)
    stage = _object_stage(tmp_path)
    shutil.copyfile(INPUTS / "course.kmp", stage / "course.kmp")  # committed, no objects
    argv = ("create", "stage", "--dest", "a.szs", "--auto-add", "--autoadd-path", "lib")
    result = _run_fake(fake_tools_path, tmp_path, *argv)
    assert (result.returncode, result.stdout) == (121, b"")
    assert not (tmp_path / "a.szs").exists()
