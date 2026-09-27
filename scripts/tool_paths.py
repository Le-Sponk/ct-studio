"""Where bootstrap_tools.py (and the S3a recipe) put each tool, on Linux and Windows.

Shared by scripts/, spikes/ and tests/ so a tool path is spelled once. Windows
executables carry ``.exe``; checking ``Path("…/wszst").is_file()`` there is always
False, which silently skipped every integration test on the first Windows run.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".tools"


# How a tool's exit(-1) reaches the parent: POSIX keeps the low byte, Windows the full
# 32-bit value. rszst uses it for help, usage errors and real failures (P0-T13).
EXIT_MINUS_ONE = 0xFFFFFFFF if os.name == "nt" else 255


def exe(path: Path) -> Path:
    """Return path with the platform's executable suffix (``.exe`` on Windows only)."""
    return path.with_name(path.name + ".exe") if os.name == "nt" else path


def first_existing(*candidates: Path) -> Path:
    """The first candidate that exists, else the first one (so errors name a real path)."""
    return next((c for c in candidates if c.is_file()), candidates[0])


WIIMMS_BIN = TOOLS_DIR / "wiimms-szs-tools" / "bin"
WSZST = exe(WIIMMS_BIN / "wszst")
WKCLT = exe(WIIMMS_BIN / "wkclt")
WKMPT = exe(WIIMMS_BIN / "wkmpt")
WIMGT = exe(WIIMMS_BIN / "wimgt")
BLENDER = exe(TOOLS_DIR / "blender" / "blender")
ABMATT_BIN = TOOLS_DIR / "abmatt" / "bin"
ABMATT = exe(ABMATT_BIN / "abmatt")
# Linux: built from source with the S3a recipe. Windows: the official release zip,
# installed by `bootstrap_tools.py --only riistudio` (P0-T13).
RSZST = first_existing(
    exe(TOOLS_DIR / "riistudio-build-pinned" / "source" / "cli" / "rszst"),
    exe(TOOLS_DIR / "riistudio" / "rszst"),
)


def tools_env(*dirs: Path) -> dict[str, str]:
    """os.environ with dirs (default: the Wiimms bin) prepended to PATH.

    ABMatt shells out to wimgt and the Blender add-on to wkclt, so both need it there.
    """
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([*(str(d) for d in dirs or (WIIMMS_BIN,)), env.get("PATH", "")])
    return env


def resolve(argv: list[str], env: dict[str, str]) -> list[str]:
    """Make argv[0] absolute using env's PATH.

    Windows CreateProcess searches the *parent's* PATH, not the one passed in env, so a
    bare ["wszst", ...] that works on Linux fails there with FileNotFoundError.
    """
    found = shutil.which(argv[0], path=env.get("PATH"))
    return [found, *argv[1:]] if found else argv
