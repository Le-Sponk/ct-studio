"""P2-T06: ``ctstudio.core.tools.doctor`` — what is installed, and what to do about the rest.

Fake filesystem trees stand in for both operating systems; version probes are replaced by a
recording stub except in one end-to-end test that runs a real fake executable.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest
from version_fakes import fake_executable, spec_running

from ctstudio.core.tools import doctor
from ctstudio.core.tools.discovery import DiscoveryEnvironment, ToolLocation
from ctstudio.core.tools.doctor import REQUIRED, ToolCheck, diagnose, version_key
from ctstudio.core.tools.registry import TOOL_BY_ID, TOOL_SPECS
from ctstudio.core.tools.spec import ToolSpec
from ctstudio.core.tools.versions import VersionCache, VersionResult

pytestmark = pytest.mark.timeout(60)


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake binary", encoding="utf-8")
    path.chmod(0o755)
    return path


def _env(
    tmp_path: Path, platform: Literal["windows", "linux"], path: str = ""
) -> DiscoveryEnvironment:
    return DiscoveryEnvironment(
        platform=platform,
        root=tmp_path / "system",
        home=tmp_path / "home",
        variables={"PATH": path, "ProgramFiles": str(tmp_path / "Program Files")},
        sandbox=None,
    )


@pytest.fixture
def probes(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Answer every probe with version 9.9 (or what ``versions`` maps a tool id to)."""
    calls: list[dict[str, object]] = []
    versions: dict[str, VersionResult | str] = {}

    def fake_probe(
        items: list[tuple[ToolSpec, ToolLocation]], **kwargs: object
    ) -> list[VersionResult]:
        calls.append({"ids": [spec.id for spec, _ in items], **kwargs})
        out = []
        for spec, location in items:
            answer = versions.get(spec.id, "9.9")
            if isinstance(answer, VersionResult):
                out.append(replace(answer, location=location))
            else:
                out.append(VersionResult(spec.id, replace(location, version=answer), "probed"))
        return out

    monkeypatch.setattr(doctor, "probe_versions", fake_probe)
    calls.append({"versions": versions})
    return calls


def _versions(probes: list[dict[str, object]]) -> dict[str, VersionResult | str]:
    return probes[0]["versions"]  # type: ignore[return-value]


def _check(report: doctor.Report, tool_id: str) -> ToolCheck:
    [check] = [c for c in report.tools if c.tool_id == tool_id]
    return check


def _run(tmp_path: Path, env: DiscoveryEnvironment, **kwargs: object) -> doctor.Report:
    return diagnose(
        environment=env,
        dev_root=tmp_path / "no-dev-tools",
        cache=VersionCache(tmp_path / "cache.json"),
        **kwargs,  # type: ignore[arg-type]
    )


# --- every tool is listed once, in registry order ----------------------------------------------


def test_every_registry_tool_is_reported_in_order(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    report = _run(tmp_path, _env(tmp_path, "windows"))
    assert [c.tool_id for c in report.tools] == [spec.id for spec in TOOL_SPECS]
    assert report.platform == "windows"
    assert REQUIRED == frozenset({"wszst"})
    assert [c.tool_id for c in report.tools if c.required] == ["wszst"]
    for check in report.tools:
        spec = TOOL_BY_ID[check.tool_id]
        assert (check.name, check.used_for) == (spec.name, spec.used_for)


# --- missing ---------------------------------------------------------------------------------


def test_an_empty_machine_reports_missing_tools_with_download_pages(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    report = _run(tmp_path, _env(tmp_path, "windows"))
    wszst = _check(report, "wszst")
    assert (wszst.status, wszst.path, wszst.version, wszst.launcher) == (
        "missing",
        None,
        None,
        None,
    )
    assert wszst.fix is not None and "https://szs.wiimm.de/download/" in wszst.fix
    assert not report.ok
    blender = _check(report, "blender")
    assert blender.status == "missing" and blender.fix is not None
    assert "blender" in blender.fix.lower()


# --- found, with versions from the probe -------------------------------------------------------


def test_found_tools_carry_path_launcher_source_and_probed_version(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    folder = tmp_path / "Wiimm é 日本"
    wszst = _exe(folder / "wszst.exe")
    _versions(probes)["wszst"] = "2.42a"
    report = _run(tmp_path, _env(tmp_path, "windows", str(folder)))
    check = _check(report, "wszst")
    assert check.status == "found"
    assert (check.path, check.launcher, check.source, check.version) == (
        wszst.resolve(),
        "direct",
        "path",
        "2.42a",
    )
    assert check.fix is None
    assert report.ok


def test_only_found_direct_tools_are_probed_and_cache_options_pass_through(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    folder = tmp_path / "bin"
    for name in ("wszst.exe", "blender.exe", "BrawlCrate.exe"):
        _exe(folder / name)
    cache = VersionCache(tmp_path / "c.json")
    diagnose(
        environment=_env(tmp_path, "windows", str(folder)),
        dev_root=tmp_path / "none",
        cache=cache,
        force=True,
    )
    [call] = probes[1:]
    assert call["ids"] == ["wszst", "blender", "brawlcrate"]
    assert call["cache"] is cache and call["force"] is True


def test_nothing_is_probed_when_nothing_is_found(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    _run(tmp_path, _env(tmp_path, "windows"))
    assert probes[1:] == []


def test_developer_copies_are_found_and_labelled(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    dev = tmp_path / "dev tools"
    _exe(dev / "wiimms-szs-tools" / "bin" / "wszst.exe")
    report = diagnose(
        environment=_env(tmp_path, "windows"),
        dev_root=dev,
        cache=VersionCache(tmp_path / "c.json"),
    )
    assert _check(report, "wszst").source == "dev"
    assert report.ok


# --- not working / unrecognised ----------------------------------------------------------------


@pytest.mark.parametrize("outcome", ["failed", "timeout"])
def test_a_tool_that_does_not_run_is_not_working(
    outcome: Literal["failed", "timeout"], probes: list[dict[str, object]], tmp_path: Path
) -> None:
    folder = tmp_path / "bin"
    _exe(folder / "wszst.exe")
    placeholder = ToolLocation(folder, None, "path", "direct")
    _versions(probes)["wszst"] = VersionResult("wszst", placeholder, outcome, "it crashed")
    report = _run(tmp_path, _env(tmp_path, "windows", str(folder)))
    check = _check(report, "wszst")
    assert check.status == "not_working" and check.version is None
    assert check.note == "it crashed"
    assert check.fix is not None and "Reinstall" in check.fix
    assert not report.ok


def test_unrecognised_version_output_is_found_with_a_note(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    folder = tmp_path / "bin"
    _exe(folder / "wszst.exe")
    placeholder = ToolLocation(folder, None, "path", "direct")
    _versions(probes)["wszst"] = VersionResult("wszst", placeholder, "unrecognised", "odd banner")
    check = _check(_run(tmp_path, _env(tmp_path, "windows", str(folder))), "wszst")
    assert (check.status, check.version, check.fix) == ("found", None, None)
    assert check.note is not None and "not recognised" in check.note


def test_gui_editors_have_no_version_and_that_is_fine(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    folder = tmp_path / "bin"
    _exe(folder / "BrawlCrate.exe")
    placeholder = ToolLocation(folder, None, "path", "direct")
    _versions(probes)["brawlcrate"] = VersionResult("brawlcrate", placeholder, "unprobed", "x")
    check = _check(_run(tmp_path, _env(tmp_path, "windows", str(folder))), "brawlcrate")
    assert (check.status, check.version, check.fix, check.note) == ("found", None, None, None)


# --- too old -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "minimum", "old"),
    [
        ("2.42a", "2.42a", False),
        ("2.42", "2.42a", True),
        ("2.42b", "2.42a", False),
        ("2.9", "2.42a", True),
        ("10.0", "9.9.9", False),
        ("5.11.5", "5.11", False),
        ("4.5", "5.2.2", True),
    ],
)
def test_versions_compare_numerically_with_letter_suffixes(
    version: str, minimum: str, old: bool
) -> None:
    assert (version_key(version) < version_key(minimum)) is old


def test_a_version_below_the_minimum_is_too_old(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    folder = tmp_path / "bin"
    _exe(folder / "wszst.exe")
    floor = replace(TOOL_BY_ID["wszst"], min_version="2.42a")
    specs = tuple(floor if s.id == "wszst" else s for s in TOOL_SPECS)
    _versions(probes)["wszst"] = "2.40"
    report = _run(tmp_path, _env(tmp_path, "windows", str(folder)), specs=specs)
    check = _check(report, "wszst")
    assert (check.status, check.version) == ("too_old", "2.40")
    assert check.fix is not None and "2.42a" in check.fix and "szs.wiimm.de" in check.fix
    assert not report.ok


def test_exactly_the_minimum_version_is_found(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    folder = tmp_path / "bin"
    _exe(folder / "wszst.exe")
    floor = replace(TOOL_BY_ID["wszst"], min_version="2.42a")
    specs = tuple(floor if s.id == "wszst" else s for s in TOOL_SPECS)
    _versions(probes)["wszst"] = "2.42a"
    report = _run(tmp_path, _env(tmp_path, "windows", str(folder)), specs=specs)
    assert (_check(report, "wszst").status, report.ok) == ("found", True)


def test_an_unknown_version_is_not_called_too_old(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    folder = tmp_path / "bin"
    _exe(folder / "wszst.exe")
    floor = replace(TOOL_BY_ID["wszst"], min_version="2.42a")
    specs = tuple(floor if s.id == "wszst" else s for s in TOOL_SPECS)
    placeholder = ToolLocation(folder, None, "path", "direct")
    _versions(probes)["wszst"] = VersionResult("wszst", placeholder, "unrecognised", None)
    report = _run(tmp_path, _env(tmp_path, "windows", str(folder)), specs=specs)
    assert _check(report, "wszst").status == "found"


# --- platform-specific: Wine, Flatpak, not needed -----------------------------------------------


def test_wine_and_winetricks_are_not_needed_on_windows(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    report = _run(tmp_path, _env(tmp_path, "windows"))
    for tool in ("wine", "winetricks"):
        check = _check(report, tool)
        assert (check.status, check.fix) == ("not_needed", None)
        assert check.note is not None and "Linux" in check.note


def test_linux_windows_editor_without_wine_needs_wine(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    folder = tmp_path / "home" / "bin"
    _exe(folder / "BrawlCrate.exe")
    check = _check(_run(tmp_path, _env(tmp_path, "linux")), "brawlcrate")
    assert (check.status, check.launcher) == ("needs_wine", "wine")
    assert check.fix is not None and "Wine" in check.fix and "winehq" in check.fix


def test_linux_windows_editor_with_wine_is_found_with_its_prefix_recipe(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    _exe(tmp_path / "home" / "bin" / "BrawlCrate.exe")
    _exe(tmp_path / "home" / "bin" / "wine")
    _exe(tmp_path / "home" / "bin" / "Lorenzi's KMP Editor.exe")
    report = _run(tmp_path, _env(tmp_path, "linux"))
    brawl = _check(report, "brawlcrate")
    assert (brawl.status, brawl.launcher, brawl.version, brawl.fix) == ("found", "wine", None, None)
    assert brawl.note is not None and "win32" in brawl.note and "dotnet48" in brawl.note
    lorenzi = _check(report, "kmp_editor_lorenzi")
    assert lorenzi.note is not None and "win64" in lorenzi.note and "dotnet48" not in lorenzi.note
    assert _check(report, "wine").status == "found"
    assert "brawlcrate" not in probes[1]["ids"]  # type: ignore[operator] - never started for a version


def test_flatpak_blender_is_sandboxed_and_not_probed(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    env = _env(tmp_path, "linux")
    _exe(env.root / "usr" / "bin" / "flatpak")
    desktop = (
        env.home / ".local/share/flatpak/exports/share/applications/org.blender.Blender.desktop"
    )
    desktop.parent.mkdir(parents=True)
    desktop.write_text("[Desktop Entry]\n", encoding="utf-8")
    report = _run(tmp_path, env)
    check = _check(report, "blender")
    assert (check.status, check.launcher) == ("sandboxed", "flatpak")
    assert check.fix is not None and "Flatpak" in check.fix
    assert all("blender" not in call.get("ids", []) for call in probes[1:])  # type: ignore[operator]


def test_linux_required_tool_found_by_its_linux_name(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    _exe(tmp_path / "system" / "usr" / "bin" / "wszst")
    report = _run(tmp_path, _env(tmp_path, "linux"))
    assert _check(report, "wszst").status == "found"
    assert _check(report, "wine").status == "missing"
    assert report.ok  # Wine is optional


# --- JSON ---------------------------------------------------------------------------------------


def test_json_is_plain_data_with_every_field(
    probes: list[dict[str, object]], tmp_path: Path
) -> None:
    folder = tmp_path / "é 日本"
    _exe(folder / "wszst.exe")
    data = _run(tmp_path, _env(tmp_path, "windows", str(folder))).to_json()
    assert set(data) == {"format", "platform", "ok", "tools"}
    assert (data["format"], data["platform"], data["ok"]) == (1, "windows", True)
    first = data["tools"][0]  # type: ignore[index]
    assert first == {
        "id": "wszst",
        "name": "Wiimms SZS Tool",
        "status": "found",
        "required": True,
        "version": "9.9",
        "path": str((folder / "wszst.exe").resolve()),
        "launcher": "direct",
        "source": "path",
        "used_for": "SZS assembly, validation and analysis",
        "fix": None,
        "note": None,
        "route": None,
    }


# --- end to end with a real (fake) executable ---------------------------------------------------


def test_a_real_probe_reads_the_version_and_caches_it(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "tool é")
    spec = spec_running('print("fake v1.5")')
    env = _env(tmp_path, "windows" if exe.suffix == ".exe" else "linux", str(exe.parent))
    cache_file = tmp_path / "cache.json"
    report = diagnose(
        environment=env,
        dev_root=tmp_path / "none",
        cache=VersionCache(cache_file),
        specs=(replace(spec, exe_names={env.platform: (exe.name,)}),),
        required=frozenset({"fake"}),
    )
    [check] = report.tools
    assert (check.status, check.version, check.required) == ("found", "1.5", True)
    assert report.ok
    assert "1.5" in cache_file.read_text(encoding="utf-8")
