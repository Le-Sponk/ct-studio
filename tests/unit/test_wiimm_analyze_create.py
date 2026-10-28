"""P2-T05b: Wiimm analyze/create judge output and files, never the exit status alone."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ctstudio.core.errors import ParseError
from ctstudio.core.tools.process import RunResult

RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a"


def _stage(root: Path) -> Path:
    stage = root / "stage"
    stage.mkdir()
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(RECORDINGS / "inputs" / name, stage / name)
    return stage


def test_analyze_directory_returns_recorded_json(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import analyze

    report = analyze(_stage(tmp_path))
    assert (report["file"], report["file_type"], report["valid"]) == ("stage", "U8", 1)
    assert report["valid_track"] == 0  # analyzable is not the same as a complete track
    assert report["sha1_course"] == ""  # missing course model is visible as an empty hash
    assert fake_tools_path.calls() == [
        {"tool": "wszst", "argv": ["analyze", "--json", "stage"], "cwd": str(tmp_path)}
    ]


def test_analyze_unsupported_file_exit_zero_raises(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError, analyze

    junk = tmp_path / "junk.szs"
    junk.write_bytes(b"not a track file\n" * 4)
    with pytest.raises(WiimmError, match="File format not supported") as caught:
        analyze(junk)
    assert caught.value.exit_code == 0


def test_analyze_unrecorded_stage_is_refused(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError, analyze

    stage = _stage(tmp_path)
    kcl = stage / "course.kcl"
    data = bytearray(kcl.read_bytes())
    data[-1] ^= 1  # the fake must not replay analysis of different bytes
    kcl.write_bytes(data)
    with pytest.raises(WiimmError, match="not modelled") as caught:
        analyze(stage)
    assert caught.value.exit_code == 121


def test_analyze_missing_file_raises_with_error_code(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError, analyze

    with pytest.raises(WiimmError) as caught:
        analyze(tmp_path / "missing.szs")
    assert (caught.value.error_code, caught.value.exit_code) == (78, 78)


def test_analyze_rejects_non_json_output(monkeypatch, tmp_path: Path) -> None:
    import ctstudio.core.tools.wiimm as wiimm

    def fake_run(cmd, *, on_line, **_kwargs) -> RunResult:
        on_line("stdout", "")
        on_line("stdout", "not json")
        return RunResult(0, 0.0, "not json", "", None)

    monkeypatch.setattr(wiimm, "run", fake_run)
    with pytest.raises(ParseError, match="JSON"):
        wiimm.analyze(tmp_path / "t.szs", executable=tmp_path / "wszst")


@pytest.mark.parametrize(
    ("compression", "flags", "magic"),
    [
        ("best", [], b"Yaz0"),
        ("fast", ["--fast"], b"Yaz0"),
        ("none", ["--no-compress"], bytes.fromhex("55aa382d")),
    ],
)
def test_create_maps_compression_to_recorded_flags(
    fake_tools_path, tmp_path: Path, compression: str, flags: list[str], magic: bytes
) -> None:
    from ctstudio.core.tools.wiimm import create_szs

    stage = _stage(tmp_path)
    dest = tmp_path / "out.szs"
    assert create_szs(stage, dest, compression=compression) == dest  # type: ignore[arg-type]
    assert dest.read_bytes().startswith(magic)
    assert fake_tools_path.calls() == [
        {
            "tool": "wszst",
            "argv": ["create", "stage", "--dest", str(dest), *flags],
            "cwd": str(tmp_path),
        }
    ]


def test_create_existing_dest_exit_zero_is_failure(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError, create_szs

    stage = _stage(tmp_path)
    dest = tmp_path / "out.szs"
    dest.write_bytes(b"keep me")
    with pytest.raises(WiimmError, match="FILE ALREADY EXISTS") as caught:
        create_szs(stage, dest)
    assert (caught.value.error_code, caught.value.exit_code) == (64, 0)
    assert dest.read_bytes() == b"keep me"
    create_szs(stage, dest, overwrite=True)
    assert dest.read_bytes().startswith(b"Yaz0")
    assert fake_tools_path.calls()[-1]["argv"][-1] == "--overwrite"


def test_create_missing_parent_exit_zero_is_failure(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError, create_szs

    with pytest.raises(WiimmError, match="CAN'T CREATE FILE") as caught:
        create_szs(_stage(tmp_path), tmp_path / "sub" / "out.szs")
    assert (caught.value.error_code, caught.value.exit_code) == (82, 0)


def test_create_missing_stage_raises(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError, create_szs

    with pytest.raises(WiimmError) as caught:
        create_szs(tmp_path / "nodir", tmp_path / "out.szs")
    assert (caught.value.error_code, caught.value.exit_code) == (78, 78)


def test_create_auto_add_is_refused_before_running(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import AutoAddUnavailable, create_szs

    with pytest.raises(AutoAddUnavailable, match="auto-add"):
        create_szs(_stage(tmp_path), tmp_path / "out.szs", auto_add=True)
    assert fake_tools_path.calls() == []


def test_create_silent_exit_zero_without_file_is_failure(monkeypatch, tmp_path: Path) -> None:
    import ctstudio.core.tools.wiimm as wiimm

    def fake_run(cmd, **_kwargs) -> RunResult:
        return RunResult(0, 0.0, "", "", None)

    monkeypatch.setattr(wiimm, "run", fake_run)
    stage = tmp_path / "stage"
    stage.mkdir()
    with pytest.raises(wiimm.WiimmError, match="no SZS"):
        wiimm.create_szs(stage, tmp_path / "out.szs", executable=tmp_path / "wszst")


def test_create_wrong_archive_format_is_failure(monkeypatch, tmp_path: Path) -> None:
    import ctstudio.core.tools.wiimm as wiimm

    dest = tmp_path / "out.szs"

    def fake_run(cmd, **_kwargs) -> RunResult:
        dest.write_bytes(bytes.fromhex("55aa382d"))  # uncompressed where Yaz0 was asked for
        return RunResult(0, 0.0, "", "", None)

    monkeypatch.setattr(wiimm, "run", fake_run)
    stage = tmp_path / "stage"
    stage.mkdir()
    with pytest.raises(wiimm.WiimmError, match="no SZS"):
        wiimm.create_szs(stage, dest, executable=tmp_path / "wszst")
