"""Set up the official Windows ``rszst.exe`` to run through Wine on Linux (P2-T06d).

The quick Linux alternative to the hour-long source build. Measured in P2-T06c on Mint 22.3
with wine-9.0: 48 of the 49 recorded Windows cases gave the same result (the other differs
only in a path separator in an error message); the Windows build's path bugs come along,
which the adapter avoids by staging under ASCII names. Steps: make CT Studio's own quiet
win64 prefix, download the pinned release (``rszst_install.download_windows``) with its
banner read through Wine, then write ``setup.json`` (route ``wine``) last.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from ctstudio.core.errors import ToolFailed, ToolNotFound, ToolTimedOut
from ctstudio.core.tools import process
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.rszst_install import (
    BANNER_TIMEOUT,
    Opener,
    Progress,
    Runner,
    SetupFailed,
    Which,
    download_windows,
    open_url,
)
from ctstudio.core.tools.rszst_setup import (
    PIN,
    SetupRecord,
    wine_environment,
    wine_executable,
    write_record,
)
from ctstudio.core.tools.wine import WineError, prefix_arch

PREFIX_TIMEOUT = 600.0
INSTALL_WINE = "sudo apt install -y wine"
_WINE_BROKE = (ToolFailed, ToolTimedOut, ToolNotFound)
# Where distributions put wineserver relative to the prefix that holds bin/wine: beside wine
# (Ubuntu 24.04, WineHQ), or only in the library folder (Ubuntu 26.04 / Debian, Wine 10).
_SERVER_PLACES = ("bin", "lib/x86_64-linux-gnu/wine", "lib/wine")


def install_wine(
    root: Path,
    *,
    wine: Path,
    runner: Runner = process.run,
    opener: Opener = open_url,
    which: Which = shutil.which,
    cancel: CancelToken | None = None,
    on_progress: Progress | None = None,
) -> Path:
    """Prefix, download and check into ``root``; return the managed ``rszst.exe``.

    Each step skips work already done (an existing prefix, a checked download), so running
    it again after an interruption, or after it finished, is cheap and repairs the record.
    """
    exe = wine_executable(root)
    record = SetupRecord("wine", PIN.version, exe.relative_to(root).as_posix())
    if not wine.is_file():
        raise SetupFailed(
            "Wine is not installed, so rszst.exe cannot run.",
            hint=f"Install it with:\n  {INSTALL_WINE}",
        )
    root.mkdir(parents=True, exist_ok=True)
    _prepare_prefix(root, wine, runner, which)
    download_windows(
        exe.parent,
        opener=opener,
        banner=_through_wine(root, wine, runner),
        cancel=cancel,
        on_progress=on_progress,
    )
    write_record(root, record)
    return exe


def _wineserver(wine: Path, which: Which) -> Path:
    """The ``wineserver`` that goes with ``wine``: on PATH, else where its package put it."""
    found = which("wineserver")
    if found:
        return Path(found)
    for place in _SERVER_PLACES:
        server = wine.parent.parent / place / "wineserver"
        if server.is_file():
            return server
    raise SetupFailed(
        f"Wine's wineserver program was not found next to {wine} or in its library folder.",
        hint=f"Reinstall Wine with:\n  {INSTALL_WINE}",
    )


def _prepare_prefix(root: Path, wine: Path, runner: Runner, which: Which) -> None:
    prefix = root / "prefix"
    if not (prefix / "system.reg").is_file():
        env = {**wine_environment(root), "WINEARCH": "win64"}
        server = _wineserver(wine, which)
        try:
            for argv in ([wine, "wineboot", "-u"], [server, "-w"]):
                runner(argv, cwd=root, env=env, timeout=PREFIX_TIMEOUT, check=False)
        except _WINE_BROKE as exc:
            raise _no_prefix(exc.details) from exc
    try:
        arch = prefix_arch(prefix)
    except WineError as exc:
        raise _no_prefix(str(exc)) from exc
    if arch != "win64":
        raise SetupFailed(
            f"CT Studio's Wine folder {prefix} is 32-bit, but rszst.exe is a 64-bit program.",
            hint=f"Delete {root} and run the setup again.",
        )


def _no_prefix(details: str | None) -> SetupFailed:
    return SetupFailed(
        "Wine could not prepare its folder for rszst.",
        hint="Check that Wine works: run `wine --version` in a terminal.",
        details=details,
    )


def _through_wine(root: Path, wine: Path, runner: Runner) -> Callable[[Path], str]:
    """``rszst.exe --version`` read through Wine; the .exe cannot run directly on Linux."""

    def banner(exe: Path) -> str:
        try:
            result = runner(
                [wine, exe, "--version"],
                cwd=exe.parent,
                env=wine_environment(root),
                timeout=BANNER_TIMEOUT,
                check=False,
            )
        except _WINE_BROKE as exc:
            return exc.details or ""
        return f"{result.stdout_tail}\n{result.stderr_tail}"

    return banner
