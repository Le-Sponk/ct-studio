"""Locate installed tools without spawning a subprocess or importing GUI modules."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ctstudio.core import platform as ct_platform
from ctstudio.core.errors import ToolNotFound
from ctstudio.core.tools.spec import ToolSpec

Launcher = Literal["direct", "wine", "flatpak"]


@dataclass(frozen=True)
class ToolLocation:
    """A visible executable; flatpak targets an app ID via the flatpak executable."""

    path: Path
    version: str | None
    source: Literal["setting", "path", "standard", "flatpak", "dev"]
    launcher: Launcher
    app_id: str | None = None


@dataclass(frozen=True)
class DiscoveryEnvironment:
    """Snapshot of OS/visible filesystem inputs for deterministic cross-platform tests."""

    platform: Literal["windows", "linux", "other"]
    root: Path
    home: Path
    variables: Mapping[str, str]
    sandbox: Literal["flatpak", "snap"] | None

    @classmethod
    def from_system(cls) -> DiscoveryEnvironment:
        return cls(
            platform=ct_platform.current_os(),
            root=Path("/"),
            home=Path.home(),
            variables=dict(os.environ),
            sandbox=ct_platform.sandbox_kind(),
        )


def _executable(candidate: Path, platform: str) -> bool:
    return candidate.is_file() and (platform != "linux" or os.access(candidate, os.X_OK))


def _location(
    spec: ToolSpec,
    path: Path,
    source: Literal["setting", "path", "standard", "flatpak", "dev"],
    platform: str,
) -> ToolLocation:
    launcher: Launcher = (
        "wine"
        if platform == "linux" and spec.kind == "gui" and path.suffix.lower() == ".exe"
        else "direct"
    )
    return ToolLocation(path.resolve(), None, source, launcher)


def _standard_directories(spec: ToolSpec, env: DiscoveryEnvironment) -> tuple[Path, ...]:
    if env.platform == "windows":
        installations: list[Path] = []
        for key in ("ProgramFiles", "ProgramFiles(x86)"):
            base = env.variables.get(key)
            if not base:
                continue
            if spec.id in {"wszst", "wkclt", "wkmpt", "wimgt"}:
                installations.extend(
                    (Path(base) / "Wiimm" / "SZS", Path(base) / "Wiimm" / "SZS" / "bin")
                )
            if spec.id == "blender":
                installations.extend(
                    sorted((Path(base) / "Blender Foundation").glob("Blender *"), reverse=True)
                )
        return tuple(installations)
    if env.platform != "linux":
        return ()
    directories = [] if env.sandbox else [env.root / "usr/local/bin", env.root / "usr/bin"]
    directories.append(env.home / "bin")
    if spec.id == "blender":
        if not env.sandbox:
            directories.extend(sorted((env.root / "opt").glob("blender*"), reverse=True))
        directories.append(env.home / "Applications")
        directories.extend(sorted(env.home.glob("Applications/blender*"), reverse=True))
    return tuple(directories)


def _find_in_directories(
    spec: ToolSpec,
    env: DiscoveryEnvironment,
    directories: Iterable[Path],
    source: Literal["path", "standard"],
) -> ToolLocation | None:
    for folder in directories:
        for name in spec.exe_names.get(env.platform, ()):
            candidate = folder / name
            if _executable(candidate, env.platform):
                return _location(spec, candidate, source, env.platform)
    return None


_DEV_PATHS: dict[str, dict[str, tuple[str, ...]]] = {
    "rszst": {
        "windows": ("riistudio/rszst.exe",),
        "linux": ("riistudio-build-pinned/source/cli/rszst", "riistudio/rszst"),
    },
    "abmatt": {"windows": ("abmatt/bin/abmatt.exe",), "linux": ("abmatt/bin/abmatt",)},
    "blender": {"windows": ("blender/blender.exe",), "linux": ("blender/blender",)},
    "brawlcrate": {
        "windows": ("s7-brawlcrate-bin/BrawlCrate.exe",),
        "linux": ("s7-brawlcrate-bin/BrawlCrate.exe",),
    },
    "riistudio": {
        "windows": ("s7-riistudio-win/RiiStudio.exe",),
        "linux": ("s7-riistudio-win/RiiStudio.exe",),
    },
    "kmp_editor_lorenzi": {
        "windows": ("s7-lorenzi-win/Lorenzi's KMP Editor.exe",),
        "linux": (
            "s7-lorenzi-src/dist/linux-unpacked/hlorenzi-kmp-editor",
            "s7-lorenzi-win/Lorenzi's KMP Editor.exe",
        ),
    },
    "kmp_cloud": {
        "windows": ("s7-kmp-cloud/KMP Cloud.exe",),
        "linux": ("s7-kmp-cloud/KMP Cloud.exe",),
    },
}


def _dev_paths(spec: ToolSpec, env: DiscoveryEnvironment, root: Path) -> tuple[Path, ...]:
    if spec.id in {"wszst", "wkclt", "wkmpt", "wimgt"}:
        return tuple(
            root / "wiimms-szs-tools" / "bin" / name
            for name in spec.exe_names.get(env.platform, ())
        )
    return tuple(root / relative for relative in _DEV_PATHS.get(spec.id, {}).get(env.platform, ()))


def _flatpak_blender(env: DiscoveryEnvironment) -> ToolLocation | None:
    if env.platform != "linux" or env.sandbox is not None:
        return None
    app_id = "org.blender.Blender"
    data_home = Path(env.variables.get("XDG_DATA_HOME", str(env.home / ".local/share")))
    exported = (
        data_home / "flatpak/exports/share/applications" / f"{app_id}.desktop",
        env.root / "var/lib/flatpak/exports/share/applications" / f"{app_id}.desktop",
    )
    if not any(desktop.is_file() for desktop in exported):
        return None
    path_folders = (Path(entry) for entry in env.variables.get("PATH", "").split(":") if entry)
    for folder in (*path_folders, env.root / "usr/bin", env.root / "usr/local/bin"):
        launcher = folder / "flatpak"
        if _executable(launcher, env.platform):
            return ToolLocation(launcher.resolve(), None, "flatpak", "flatpak", app_id)
    return None


def _direct_location(spec: ToolSpec, env: DiscoveryEnvironment) -> ToolLocation | None:
    separator = ";" if env.platform == "windows" else ":"
    path_dirs = (Path(entry) for entry in env.variables.get("PATH", "").split(separator) if entry)
    path_location = _find_in_directories(spec, env, path_dirs, "path")
    if path_location is not None:
        return path_location
    return _find_in_directories(spec, env, _standard_directories(spec, env), "standard")


def _dev_location(
    spec: ToolSpec, env: DiscoveryEnvironment, dev_root: Path | None
) -> ToolLocation | None:
    root = dev_root if dev_root is not None else Path(__file__).resolve().parents[4] / ".tools"
    for candidate in _dev_paths(spec, env, root):
        if _executable(candidate, env.platform):
            return _location(spec, candidate, "dev", env.platform)
    return None


def discover(
    spec: ToolSpec,
    *,
    configured: Path | None = None,
    environment: DiscoveryEnvironment | None = None,
    include_dev: bool = False,
    dev_root: Path | None = None,
) -> ToolLocation | None:
    """Return the first visible tool, or None when no executable is installed."""
    env = environment if environment is not None else DiscoveryEnvironment.from_system()
    if configured is not None:
        if not _executable(configured, env.platform):
            raise ToolNotFound(
                f"Configured {spec.name}",
                hint="Choose an existing executable path in CT Studio settings.",
            )
        return _location(spec, configured, "setting", env.platform)
    local = _direct_location(spec, env)
    if local is not None:
        return local
    if spec.id == "blender":
        flatpak_location = _flatpak_blender(env)
        if flatpak_location is not None:
            return flatpak_location
    if include_dev:
        return _dev_location(spec, env, dev_root)
    return None
