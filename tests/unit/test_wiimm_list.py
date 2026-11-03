"""P4-T05a: ``wiimm.list_files`` reads ``wszst list`` (measured on 2.42a, 2026-11-03).

The header gives the counts (``1 directory``/``1 file`` are singular); each entry is one
line, folders end in ``/``, and an empty archive lists nothing. Counts that disagree with
the lines mean the report was cut short, so it is refused rather than half-believed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ctstudio.core.errors import ParseError
from ctstudio.core.tools.wiimm import WiimmError, create_szs, list_files, parse_list

RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a"
# Real 2.42a output for synthetic stages (wszst list t.szs), measured 2026-11-03.
NESTED = (
    "\n> 1 directory + 4 files of YAZ0.U8:n.szs \n\ncourse.kcl\ncourse.kmp\n"
    "my file é.bin\nposteffect/\nposteffect/posteffect.bfg\n\n"
)
ONE = "\n> 0 directories + 1 file of YAZ0.U8:one.szs \n\ncourse.kmp\n"
EMPTY = "\n> 0 directories + 0 files of YAZ0.U8:e.szs \n\n\n"
UNCOMPRESSED = "\n> 0 directories + 2 files of U8:u.szs \n\ncourse.kcl\ncourse.kmp\n\n"


@pytest.mark.parametrize(
    ("text", "files"),
    [
        (NESTED, ("course.kcl", "course.kmp", "my file é.bin", "posteffect/posteffect.bfg")),
        (ONE, ("course.kmp",)),
        (EMPTY, ()),
        (UNCOMPRESSED, ("course.kcl", "course.kmp")),
    ],
)
def test_parse_list(text: str, files: tuple[str, ...]) -> None:
    assert parse_list(text, Path("t.szs")) == files


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\ncourse.kcl\n",  # no header
        NESTED.replace("4 files", "5 files"),  # cut short
        NESTED.replace("1 directory", "2 directories"),
        ONE + "extra.bin\n",
    ],
)
def test_a_report_that_does_not_add_up_is_refused(text: str) -> None:
    with pytest.raises(ParseError, match="wszst list"):
        parse_list(text, Path("t.szs"))


def test_list_files_runs_wszst_list_on_the_archive(fake_tools_path, tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(RECORDINGS / "inputs" / name, stage / name)
    archive = create_szs(stage, tmp_path / "t é.szs")
    assert list_files(archive) == ("course.kcl", "course.kmp")
    assert fake_tools_path.calls()[-1] == {
        "tool": "wszst",
        "argv": ["list", "t é.szs"],
        "cwd": str(tmp_path),
    }


def test_list_of_a_missing_archive_raises(fake_tools_path, tmp_path: Path) -> None:
    with pytest.raises(WiimmError) as caught:
        list_files(tmp_path / "missing.szs")
    assert caught.value.exit_code == 78
