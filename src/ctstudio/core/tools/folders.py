"""Dispatch an existing directory to the desktop's folder opener, never an association.

A receipt records dispatch only, not that a window appeared or selected the directory.
Callers must run this blocking adapter off the UI thread and retain project ownership.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ctstudio.core import platform
from ctstudio.core.errors import CTStudioError, ProjectError, ToolNotFound
from ctstudio.core.tools import process


@dataclass(frozen=True)
class OpenedFolder:
    """The resolved folder and dispatch PID; no claim of successful desktop display."""

    folder: Path
    pid: int


def _explorer() -> Path:
    root = Path(os.environ.get("WINDIR", ""))
    exe = root / "explorer.exe"
    if not root.is_absolute() or not exe.is_file():
        raise ToolNotFound(
            "Windows Explorer",
            hint="Check that WINDIR names an absolute Windows folder containing explorer.exe.",
        )
    return exe.resolve()


def _opener() -> tuple[Path, float]:
    system = platform.current_os()
    if system == "windows":
        return _explorer(), 0.0
    if system == "linux":
        found = shutil.which("xdg-open")
        if found is None or not Path(found).is_file():
            raise ToolNotFound(
                "xdg-open", hint="Install xdg-utils and make xdg-open available on PATH."
            )
        return Path(found).resolve(), 0.4
    raise ProjectError(
        "Opening folders is not supported on this operating system.",
        hint="Open the folder manually in your file manager; use Windows or Linux for dispatch.",
    )


def open_folder(folder: Path) -> OpenedFolder:
    """Dispatch one existing directory without creating or changing any user files."""
    try:
        folder = folder.resolve()
        if not folder.is_dir():
            raise ProjectError(
                f"Cannot open folder: {folder} is not an existing directory.",
                hint="Choose an existing folder; generate missing outputs first if needed.",
            )
        exe, watch = _opener()
        pid = process.launch_detached([exe, str(folder)], cwd=folder, watch=watch)
        return OpenedFolder(folder, pid)
    except CTStudioError:
        raise
    except (OSError, ValueError, RuntimeError) as exc:
        raise ProjectError(
            f"Cannot open folder {folder}: {exc}",
            hint="Check the folder's permissions and desktop folder opener, then try again.",
        ) from exc
