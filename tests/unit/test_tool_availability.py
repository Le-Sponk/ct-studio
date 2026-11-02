"""P3-T07: which tools a status check may count on (``availability.available_tools``).

A part's status needs only "is this tool there", not its version, so this is discovery
alone: no program is started. A path set in CT Studio that is not a program, a tool this
OS never uses, and a sandboxed (Flatpak) Blender all count as not available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ctstudio.core.tools.availability import available_tools
from ctstudio.core.tools.discovery import DiscoveryEnvironment
from ctstudio.core.tools.registry import TOOL_BY_ID


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake binary", encoding="utf-8")
    path.chmod(0o755)
    return path


def environment(
    tmp_path: Path, platform: Literal["windows", "linux"], path: Path | None = None
) -> DiscoveryEnvironment:
    return DiscoveryEnvironment(
        platform=platform,
        root=tmp_path / "system",
        home=tmp_path / "home",
        variables={"PATH": str(path or ""), "ProgramFiles": str(tmp_path / "Program Files")},
        sandbox=None,
    )


def test_tools_on_path_are_available_and_nothing_else(tmp_path: Path) -> None:
    folder = tmp_path / "bin é"
    for name in ("wszst.exe", "wkclt.exe", "blender.exe"):
        executable(folder / name)
    env = environment(tmp_path, "windows", folder)

    found = available_tools(environment=env, dev_root=tmp_path / "no dev tools")

    assert found == frozenset({"wszst", "wkclt", "blender"})


def test_a_path_set_in_ct_studio_counts_and_a_broken_one_does_not(tmp_path: Path) -> None:
    folder = tmp_path / "bin"
    executable(folder / "wszst.exe")
    chosen = executable(tmp_path / "chosen" / "my-wkclt.exe")
    env = environment(tmp_path, "windows", folder)
    configured = {"wkclt": chosen, "wszst": tmp_path / "gone" / "wszst.exe"}

    found = available_tools(environment=env, dev_root=tmp_path / "none", configured=configured)

    assert found == frozenset({"wkclt"}), "a broken setting hides the copy on PATH"


def test_a_saved_path_for_a_tool_this_os_never_uses_is_ignored(tmp_path: Path) -> None:
    stray = executable(tmp_path / "copied settings" / "wine.exe")
    env = environment(tmp_path, "windows")

    found = available_tools(environment=env, dev_root=tmp_path / "none", configured={"wine": stray})

    assert found == frozenset(), "Wine is never used on Windows, even when a path is saved"


def test_tools_this_os_never_uses_are_not_available(tmp_path: Path) -> None:
    folder = tmp_path / "bin"
    executable(folder / "wine")
    windows = environment(tmp_path, "windows", folder)
    linux = environment(tmp_path, "linux", folder)

    assert "wine" not in available_tools(environment=windows, dev_root=tmp_path / "none")
    assert "wine" in available_tools(environment=linux, dev_root=tmp_path / "none")


def test_a_windows_program_for_wine_counts_on_linux_only_when_wine_is_there(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "bin"
    executable(folder / TOOL_BY_ID["brawlcrate"].exe_names["linux"][0])
    env = environment(tmp_path, "linux", folder)

    assert "brawlcrate" not in available_tools(environment=env, dev_root=tmp_path / "none")
    executable(folder / "wine")
    assert "brawlcrate" in available_tools(environment=env, dev_root=tmp_path / "none")


def test_a_flatpak_blender_is_not_available(tmp_path: Path) -> None:
    folder = tmp_path / "bin"
    executable(folder / "flatpak")
    env = environment(tmp_path, "linux", folder)
    desktop = env.home / ".local/share/flatpak/exports/share/applications"
    executable(desktop / "org.blender.Blender.desktop")

    assert "blender" not in available_tools(environment=env, dev_root=tmp_path / "none")
    executable(folder / "blender")
    assert "blender" in available_tools(environment=env, dev_root=tmp_path / "none")


def test_developer_tools_count_in_a_checkout(tmp_path: Path) -> None:
    dev = tmp_path / "dev tools"
    executable(dev / "wiimms-szs-tools" / "bin" / "wszst.exe")
    env = environment(tmp_path, "windows")

    assert "wszst" in available_tools(environment=env, dev_root=dev)
