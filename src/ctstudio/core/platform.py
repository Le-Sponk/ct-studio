"""OS, user-directory and Linux sandbox probes; no GUI or subprocess work."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import platformdirs

_FLATPAK_INFO = Path("/.flatpak-info")


@dataclass(frozen=True)
class UserDirectories:
    """Per-user locations; querying them does not create directories."""

    config: Path
    data: Path
    cache: Path
    logs: Path


def current_os() -> Literal["windows", "linux", "other"]:
    """Return a stable application-facing OS label."""
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Linux":
        return "linux"
    return "other"


def user_directories() -> UserDirectories:
    """Resolve config/data/cache/log dirs using platformdirs' XDG/Windows conventions."""
    return UserDirectories(
        config=Path(platformdirs.user_config_dir("ctstudio")),
        data=Path(platformdirs.user_data_dir("ctstudio")),
        cache=Path(platformdirs.user_cache_dir("ctstudio")),
        logs=Path(platformdirs.user_log_dir("ctstudio")),
    )


def sandbox_kind() -> Literal["flatpak", "snap"] | None:
    """Detect this process's sandbox, not a separately installed Blender's sandbox."""
    if current_os() != "linux":
        return None
    if _FLATPAK_INFO.exists() or os.environ.get("FLATPAK_ID"):
        return "flatpak"
    if os.environ.get("SNAP") or os.environ.get("SNAP_NAME"):
        return "snap"
    return None
