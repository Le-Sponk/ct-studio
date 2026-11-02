"""P2-T07a: paths set in CT Studio settings, as ``ctstudio.core.tools.doctor`` reports them."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from doctor_helpers import _check, _env, _exe, _run, stub_probes

from ctstudio.core.tools.doctor import diagnose
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.versions import VersionCache

pytestmark = pytest.mark.timeout(60)


@pytest.fixture
def probes(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    return stub_probes(monkeypatch)


def test_a_set_path_wins_over_path_and_is_probed(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    on_path = tmp_path / "on path"
    _exe(on_path / "wszst.exe")
    chosen = _exe(tmp_path / "chosen é" / "wszst-2.42a.exe")
    report = _run(tmp_path, _env(tmp_path, "windows", str(on_path)), configured={"wszst": chosen})
    check = _check(report, "wszst")
    assert (check.status, check.path, check.source, check.version) == (
        "found",
        chosen.resolve(),
        "setting",
        "9.9",
    )
    assert check.fix is None
    assert "wszst" in probes[1]["ids"]  # type: ignore[operator]


def test_a_set_path_that_is_not_a_program_is_missing_with_a_fix(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    on_path = tmp_path / "on path"
    _exe(on_path / "wszst.exe")
    gone = tmp_path / "moved away" / "wszst.exe"
    report = _run(tmp_path, _env(tmp_path, "windows", str(on_path)), configured={"wszst": gone})
    check = _check(report, "wszst")
    assert (check.status, check.path, check.source) == ("missing", gone, "setting")
    assert check.fix == (
        f"The path set in CT Studio for Wiimms SZS Tool is not a program: {gone}. "
        "Choose another, or clear it to search PATH and the usual folders again."
    )
    assert not report.ok  # the one the user chose is what would run, so no silent fallback


def test_a_set_path_for_a_windows_editor_on_linux_runs_through_wine(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    _exe(tmp_path / "home" / "bin" / "wine")
    exe = _exe(tmp_path / "Games" / "BrawlCrate.exe")
    report = _run(tmp_path, _env(tmp_path, "linux"), configured={"brawlcrate": exe})
    check = _check(report, "brawlcrate")
    assert (check.status, check.launcher, check.source) == ("found", "wine", "setting")


def test_a_set_path_for_a_tool_this_os_does_not_use_is_ignored(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    wine = _exe(tmp_path / "wine.exe")
    report = _run(tmp_path, _env(tmp_path, "windows"), configured={"wine": wine})
    assert _check(report, "wine").status == "not_needed"


def test_a_set_rszst_is_the_existing_route(probes: list[dict[str, object]], tmp_path: Path) -> None:
    exe = _exe(tmp_path / "Rii" / "rszst.exe")
    check = _check(_run(tmp_path, _env(tmp_path, "windows"), configured={"rszst": exe}), "rszst")
    assert (check.status, check.source, check.route) == ("found", "setting", "existing")


def test_no_settings_means_discovery_alone(probes: list[dict[str, object]], tmp_path: Path) -> None:
    folder = tmp_path / "bin"
    _exe(folder / "wszst.exe")
    for configured in (None, {}):
        report = _run(tmp_path, _env(tmp_path, "windows", str(folder)), configured=configured)
        assert _check(report, "wszst").source == "path"


def _text_file_named_like_a_program(folder: Path, name: str) -> Path:
    """Exists and is executable, but the OS cannot start it (WinError 193/216 or ENOEXEC)."""
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("notes, not a program\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_a_set_path_the_os_cannot_run_is_not_working_with_a_fix(tmp_path: Path) -> None:
    """Real probe, no stub: the reviewer's doctor traceback (P2-GATE Must fix 1)."""
    name = "blender.exe" if sys.platform == "win32" else "blender"
    chosen = _text_file_named_like_a_program(tmp_path / "chosen é", name)
    report = diagnose(
        environment=_env(tmp_path, "windows" if sys.platform == "win32" else "linux"),
        dev_root=tmp_path / "no-dev-tools",
        cache=VersionCache(tmp_path / "cache.json"),
        specs=(TOOL_BY_ID["blender"],),
        configured={"blender": chosen},
    )
    [check] = report.tools
    assert (check.status, check.source) == ("not_working", "setting")
    assert check.note is not None and "not a program this system can run" in check.note
    assert check.fix is not None


def test_a_broken_setting_uses_the_callers_required_set(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    gone = tmp_path / "moved away" / "BrawlCrate.exe"
    report = _run(
        tmp_path,
        _env(tmp_path, "windows"),
        configured={"brawlcrate": gone},
        required=frozenset({"brawlcrate"}),
    )
    check = _check(report, "brawlcrate")
    assert (check.status, check.required) == ("missing", True)
    assert not report.ok


def test_a_tool_the_os_refuses_for_another_reason_is_not_working_with_that_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2-GATE verification: e.g. needs administrator rights; doctor still finishes."""
    from ctstudio.core.tools import process

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError(22, "The requested operation requires elevation", None, 740)

    name = "blender.exe" if sys.platform == "win32" else "blender"
    chosen = _exe(tmp_path / "chosen" / name)
    monkeypatch.setattr(process.subprocess, "Popen", refuse)
    report = diagnose(
        environment=_env(tmp_path, "windows" if sys.platform == "win32" else "linux"),
        dev_root=tmp_path / "no-dev-tools",
        cache=VersionCache(tmp_path / "cache.json"),
        specs=(TOOL_BY_ID["blender"],),
        configured={"blender": chosen},
    )
    [check] = report.tools
    assert check.status == "not_working"
    assert (
        check.note == f"{name} could not be started (The requested operation requires elevation)."
    )
