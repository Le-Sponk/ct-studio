"""P2-T05a: Wiimm check uses the runner, not the deceptive process status."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ctstudio.core.errors import ParseError

RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a"


def test_corrupt_exit_zero_raises_typed_error(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmCheckError, check

    bad = tmp_path / "junk.szs"
    bad.write_bytes(b"not a track file\n" * 4)
    with pytest.raises(WiimmCheckError, match="INVALID FILE FORMAT") as caught:
        check(bad)
    assert (caught.value.error_code, caught.value.exit_code) == (39, 0)
    assert fake_tools_path.calls() == [
        {"tool": "wszst", "argv": ["check", bad.name], "cwd": str(tmp_path)}
    ]


def test_missing_exit_nonzero_raises_typed_error(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmCheckError, check

    missing = tmp_path / "missing.szs"
    with pytest.raises(WiimmCheckError, match="CAN'T OPEN FILE") as caught:
        check(missing)
    assert (caught.value.error_code, caught.value.exit_code) == (78, 78)
    assert fake_tools_path.calls()[0]["argv"] == ["check", "missing.szs"]


def test_prefix_only_check_is_never_reported_clean(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import check

    stage = tmp_path / "stage"
    stage.mkdir()
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(RECORDINGS / "inputs" / name, stage / name)
    with pytest.raises(ParseError, match="summary"):
        check(stage)
    assert fake_tools_path.calls()[0]["argv"] == ["check", "stage"]


def test_empty_fake_prefix_is_incomplete_not_clean(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import check

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ParseError, match="summary"):
        check(empty)
    assert fake_tools_path.calls()[0]["argv"] == ["check", "empty"]


def test_unrecorded_stage_refused_without_success(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmCheckError, check

    stage = tmp_path / "stage"
    stage.mkdir()
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(RECORDINGS / "inputs" / name, stage / name)
    kcl = stage / "course.kcl"
    data = bytearray(kcl.read_bytes())
    data[-1] ^= 1  # the fake must check the full digest, not just the header
    kcl.write_bytes(data)
    with pytest.raises(WiimmCheckError, match="not modelled") as caught:
        check(stage)
    assert caught.value.exit_code == 121
    assert fake_tools_path.calls()[0]["argv"] == ["check", "stage"]
