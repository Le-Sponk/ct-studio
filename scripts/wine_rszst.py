"""Set the pinned rszst.exe up through Wine in .tools/ for Linux tests (P2-T08d).

Uses CT Studio's own Wine route (``ctstudio setup rszst --wine``, P2-T06d): a quiet win64
prefix, the official release checked against its pinned SHA-256, and the banner read
through Wine. It then writes ``.tools/riistudio-wine/bin/rszst``, a shell launcher, so
``scripts/tool_paths.py`` and every test that runs ``rszst ...`` work unchanged.

    uv run python scripts/wine_rszst.py

Linux only (Windows runs the release directly: ``bootstrap_tools.py --only riistudio``).
Needs Wine (``sudo apt install -y wine``) and the network. Nothing goes into the repo.
"""

from __future__ import annotations

import json
import shlex
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import tool_paths as tp

from ctstudio.core.tools.rszst_setup import PIN, wine_environment, wine_executable
from ctstudio.core.tools.rszst_wine import INSTALL_WINE, install_wine

ROOT = tp.TOOLS_DIR / "riistudio-wine"
STATE = tp.TOOLS_DIR / "installed.json"  # what bootstrap_tools.py writes


class Install(Protocol):
    def __call__(self, root: Path, *, wine: Path) -> Path: ...


def launcher_path(root: Path) -> Path:
    """``bin/rszst``: ``root/rszst/`` is the release folder holding rszst.exe."""
    return root / "bin" / "rszst"


def launcher_text(wine: Path, root: Path) -> str:
    """A POSIX ``rszst`` that runs ``wine rszst.exe "$@"`` in the managed prefix."""
    # wine_environment(root) with a POSIX prefix path: the launcher is a Linux script.
    env = {**wine_environment(root), "WINEPREFIX": (root / "prefix").as_posix()}
    exports = [f"export {name}={shlex.quote(value)}" for name, value in sorted(env.items())]
    exe = shlex.quote(wine_executable(root).as_posix())
    command = f'exec {shlex.quote(wine.as_posix())} {exe} "$@"'
    return "\n".join(["#!/bin/sh", *exports, command]) + "\n"


def setup(root: Path, *, wine: Path, state: Path, install: Install = install_wine) -> Path:
    """Install (or repair) rszst.exe under ``root``, write its launcher, then record it.

    ``state`` is ``installed.json``: the recorders read the riistudio pin from it, as they
    do after ``bootstrap_tools.py --only riistudio`` on Windows.
    """
    install(root, wine=wine)
    launcher = launcher_path(root)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(launcher_text(wine, root), encoding="utf-8", newline="\n")
    launcher.chmod(0o755)
    record_installed(state)
    return launcher


def record_installed(state: Path) -> None:
    """Add the pinned release (run through Wine) to ``installed.json``, keeping the rest."""
    saved = json.loads(state.read_text(encoding="utf-8")) if state.is_file() else {}
    saved["riistudio"] = {
        "platform": "linux-x86_64-wine",
        "sha256": PIN.windows_zip_sha256,
        "url": PIN.windows_zip_url,
        "verify": PIN.banner,
        "version": PIN.version,
    }
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(saved, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(*, platform: str = sys.platform, which: Callable[[str], str | None] = shutil.which) -> int:
    if platform == "win32":
        print("Windows runs rszst.exe directly:")
        print("  uv run python scripts/bootstrap_tools.py --only riistudio")
        return 2
    wine = which("wine")
    if wine is None:
        print(f"Wine is not installed. Install it with:\n  {INSTALL_WINE}")
        return 1
    launcher = setup(ROOT, wine=Path(wine), state=STATE)
    print(f"rszst through Wine: {launcher}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
