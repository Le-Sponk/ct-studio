"""Pure filesystem discovery with fake tools on both target OS branches."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import pytest

from ctstudio.core import platform as ct_platform
from ctstudio.core.errors import ToolNotFound
from ctstudio.core.tools.discovery import DiscoveryEnvironment, discover
from ctstudio.core.tools.registry import TOOL_BY_ID


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake binary", encoding="utf-8")
    path.chmod(0o755)
    return path


def environment(
    tmp_path: Path, platform: Literal["windows", "linux"], *, path: str = ""
) -> DiscoveryEnvironment:
    return DiscoveryEnvironment(
        platform=platform,
        root=tmp_path / "system",
        home=tmp_path / "home",
        variables={"PATH": path, "ProgramFiles": str(tmp_path / "Program Files")},
        sandbox=None,
    )


def test_configured_path_wins_over_path_on_windows(tmp_path: Path) -> None:
    found = executable(tmp_path / "Track é 日本" / "wszst.exe")
    executable(tmp_path / "PATH" / "wszst.exe")
    env = environment(tmp_path, "windows", path=str(tmp_path / "PATH"))

    location = discover(TOOL_BY_ID["wszst"], configured=found, environment=env)

    assert location is not None
    assert location.path == found.resolve()
    assert location.source == "setting"
    assert location.launcher == "direct"
    assert location.version is None


def test_path_finds_each_os_executable_with_spaces_and_unicode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for platform, filename, separator in (
        ("windows", "wkclt.exe", ";"),
        ("linux", "wkclt", ":"),
    ):
        folder = tmp_path / "é 日本" / platform
        found = executable(folder / filename)
        path_entry = str(folder) if platform == "windows" else str(folder.relative_to(tmp_path))
        env = environment(
            tmp_path,
            "windows" if platform == "windows" else "linux",
            path=f"missing{separator}{path_entry}",
        )
        location = discover(TOOL_BY_ID["wkclt"], environment=env)
        assert location is not None
        assert location.path == found.resolve()
        assert location.source == "path"
        assert location.launcher == "direct"


def test_windows_path_ignores_empty_segments_and_wrong_suffix(tmp_path: Path) -> None:
    directory = tmp_path / "tools"
    executable(directory / "wszst")
    env = environment(tmp_path, "windows", path=f";{directory};;")
    assert discover(TOOL_BY_ID["wszst"], environment=env) is None


@pytest.mark.parametrize("platform,name", [("windows", "wszst.exe"), ("linux", "wszst")])
def test_path_precedes_standard_wiimm_install(
    tmp_path: Path, platform: Literal["windows", "linux"], name: str
) -> None:
    env = environment(tmp_path, platform)
    standard = (
        tmp_path / "Program Files" / "Wiimm" / "SZS" / name
        if platform == "windows"
        else env.root / "usr" / "local" / "bin" / name
    )
    executable(standard)
    path_exe = executable(tmp_path / "override" / name)
    env = environment(tmp_path, platform, path=str(path_exe.parent))
    location = discover(TOOL_BY_ID["wszst"], environment=env)
    assert location is not None
    assert location.path == path_exe.resolve()
    assert location.source == "path"


def test_standard_windows_wiimm_and_blender_when_path_empty(tmp_path: Path) -> None:
    env = environment(tmp_path, "windows")
    wiimm = executable(tmp_path / "Program Files" / "Wiimm" / "SZS" / "bin" / "wszst.exe")
    executable(tmp_path / "Program Files" / "Blender Foundation" / "Blender 4.5" / "blender.exe")
    latest = executable(
        tmp_path / "Program Files" / "Blender Foundation" / "Blender 5.2" / "blender.exe"
    )
    wiimm_location = discover(TOOL_BY_ID["wszst"], environment=env)
    assert wiimm_location is not None
    assert wiimm_location.path == wiimm.resolve()
    result = discover(TOOL_BY_ID["blender"], environment=env)
    assert result is not None
    assert result.path == latest.resolve()
    assert result.source == "standard"


@pytest.mark.parametrize("relative", ["usr/local/bin", "usr/bin", "home/bin"])
def test_standard_linux_wiimm_when_path_empty(tmp_path: Path, relative: str) -> None:
    env = environment(tmp_path, "linux")
    base = env.home if relative == "home/bin" else env.root
    directory = base / ("bin" if relative == "home/bin" else relative)
    found = executable(directory / "wimgt")
    location = discover(TOOL_BY_ID["wimgt"], environment=env)
    assert location is not None
    assert location.path == found.resolve()
    assert location.source == "standard"


def test_linux_blender_opt_and_home_applications(tmp_path: Path) -> None:
    env = environment(tmp_path, "linux")
    opt = executable(env.root / "opt" / "blender-5.2" / "blender")
    executable(env.home / "Applications" / "blender")
    result = discover(TOOL_BY_ID["blender"], environment=env)
    assert result is not None
    assert result.path == opt.resolve()
    assert result.source == "standard"


def test_linux_gui_editor_requires_wine_launcher(tmp_path: Path) -> None:
    exe = executable(tmp_path / "editors" / "BrawlCrate.exe")
    env = environment(tmp_path, "linux", path="editors")
    # Use an explicit setting; a .exe is not made Linux-native by an absolute path.
    location = discover(TOOL_BY_ID["brawlcrate"], configured=exe, environment=env)
    assert location is not None
    assert location.launcher == "wine"
    assert location.app_id is None


@pytest.mark.parametrize(
    "platform,tool,relative",
    [
        ("windows", "wkclt", "wiimms-szs-tools/bin/wkclt.exe"),
        ("linux", "wkclt", "wiimms-szs-tools/bin/wkclt"),
        ("windows", "rszst", "riistudio/rszst.exe"),
        ("linux", "rszst", "riistudio-build-pinned/source/cli/rszst"),
        ("windows", "kmp_cloud", "s7-kmp-cloud/KMP Cloud.exe"),
        ("linux", "brawlcrate", "s7-brawlcrate-bin/BrawlCrate.exe"),
    ],
)
def test_developer_tools_are_opt_in(
    tmp_path: Path, platform: Literal["windows", "linux"], tool: str, relative: str
) -> None:
    env = environment(tmp_path, platform)
    dev = tmp_path / ".tools"
    found = executable(dev / relative)
    assert discover(TOOL_BY_ID[tool], environment=env, dev_root=dev) is None
    location = discover(TOOL_BY_ID[tool], environment=env, include_dev=True, dev_root=dev)
    assert location is not None
    assert location.path == found.resolve()
    assert location.source == "dev"
    assert location.launcher == (
        "wine" if platform == "linux" and tool == "brawlcrate" else "direct"
    )


def test_standard_precedes_developer_tools(tmp_path: Path) -> None:
    env = environment(tmp_path, "linux")
    standard = executable(env.root / "usr/bin" / "blender")
    executable(tmp_path / ".tools" / "blender" / "blender")
    location = discover(
        TOOL_BY_ID["blender"], environment=env, include_dev=True, dev_root=tmp_path / ".tools"
    )
    assert location is not None
    assert location.path == standard.resolve()
    assert location.source == "standard"


def test_flatpak_blender_has_real_launcher_and_app_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    env = environment(tmp_path, "linux", path="executables")
    flatpak = executable(tmp_path / "executables" / "flatpak")
    desktop = (
        env.home / ".local/share/flatpak/exports/share/applications/org.blender.Blender.desktop"
    )
    desktop.parent.mkdir(parents=True)
    desktop.write_text("[Desktop Entry]\n", encoding="utf-8")
    location = discover(TOOL_BY_ID["blender"], environment=env)
    assert location is not None
    assert location.path == flatpak.resolve()
    assert location.source == "flatpak"
    assert location.launcher == "flatpak"
    assert location.app_id == "org.blender.Blender"
    assert location.version is None


def test_flatpak_needs_an_exported_app_and_a_visible_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    env = environment(tmp_path, "linux", path="executables")
    executable(tmp_path / "executables" / "flatpak")
    assert discover(TOOL_BY_ID["blender"], environment=env) is None
    (env.root / "var/lib/flatpak/exports/share/applications").mkdir(parents=True)
    (env.root / "var/lib/flatpak/exports/share/applications/org.blender.Blender.desktop").touch()
    flatpak_location = discover(TOOL_BY_ID["blender"], environment=env)
    assert flatpak_location is not None
    assert flatpak_location.launcher == "flatpak"
    (tmp_path / "executables" / "flatpak").unlink()
    assert discover(TOOL_BY_ID["blender"], environment=env) is None


@pytest.mark.parametrize("sandbox", ["flatpak", "snap"])
def test_sandbox_does_not_report_host_installations(tmp_path: Path, sandbox: str) -> None:
    from dataclasses import replace

    env = replace(environment(tmp_path, "linux"), sandbox=sandbox)
    executable(env.root / "usr/local/bin" / "wszst")
    executable(env.root / "usr/bin" / "wszst")
    executable(env.root / "opt" / "blender-5.2" / "blender")
    assert discover(TOOL_BY_ID["wszst"], environment=env) is None
    assert discover(TOOL_BY_ID["blender"], environment=env) is None
    visible = executable(env.home / "bin" / "wszst")
    found = discover(TOOL_BY_ID["wszst"], environment=env)
    assert found is not None
    assert found.path == visible.resolve()


def test_system_environment_uses_platform_probes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ct_platform, "current_os", lambda: "linux")
    monkeypatch.setattr(ct_platform, "sandbox_kind", lambda: "flatpak")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setenv("PATH", "")
    found = DiscoveryEnvironment.from_system()
    assert found.platform == "linux"
    assert found.home == tmp_path / "home"
    assert found.sandbox == "flatpak"
    assert found.variables["PATH"] == ""
    monkeypatch.setenv("PATH", "changed after discovery")
    assert found.variables["PATH"] == ""


def test_linux_path_ignores_unexecutable_file_even_when_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ctstudio.core.tools import discovery

    env = environment(tmp_path, "linux")
    executable(env.home / "bin" / "wimgt")
    monkeypatch.setattr(discovery.os, "access", lambda path, mode: False)
    assert discover(TOOL_BY_ID["wimgt"], environment=env) is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX execute permissions only")
def test_linux_ignores_nonexecutable_files(tmp_path: Path) -> None:
    env = environment(tmp_path, "linux")
    file = executable(env.home / "bin" / "wimgt")
    file.chmod(0o644)
    assert discover(TOOL_BY_ID["wimgt"], environment=env) is None


def test_flatpak_honours_xdg_data_home(tmp_path: Path) -> None:
    from dataclasses import replace

    env = environment(tmp_path, "linux")
    env = replace(env, variables={**env.variables, "XDG_DATA_HOME": str(tmp_path / "xdg")})
    desktop = tmp_path / "xdg/flatpak/exports/share/applications/org.blender.Blender.desktop"
    desktop.parent.mkdir(parents=True)
    desktop.touch()
    flatpak = executable(env.root / "usr/bin" / "flatpak")
    found = discover(TOOL_BY_ID["blender"], environment=env)
    assert found is not None
    assert found.path == flatpak.resolve()
    assert found.app_id == "org.blender.Blender"


def test_missing_configured_path_is_actionable(tmp_path: Path) -> None:
    env = environment(tmp_path, "windows")
    with pytest.raises(ToolNotFound, match=r"Configured.*not found") as error:
        discover(TOOL_BY_ID["wszst"], configured=tmp_path / "missing.exe", environment=env)
    assert error.value.hint is not None
    assert "Choose" in error.value.hint
