"""Run a Windows editor on Linux through Wine (P2-T05g2).

Measured on Linux Mint 22.3 with Wine 9.0 (Ubuntu) and winetricks 20240105 by
``spikes/p2t05g2_wine_probe.py``; see docs/reference/TOOLS.md "Wine / winetricks":

* The program's PE header fixes the prefix: BrawlCrate and KMP Cloud are PE32 i386, RiiStudio
  and Lorenzi's KMP Editor PE32+ x86-64. A 64-bit program in a win32 prefix fails with
  ``ShellExecuteEx failed: Bad EXE format``; it is refused here before anything starts.
  A win64 prefix also runs 32-bit programs (it has ``syswow64``).
* A prefix records its architecture as ``#arch=win32|win64`` in the header of ``system.reg``.
* ``winepath.exe -w`` converts any absolute path (Unicode, missing files, a prefix in a
  non-ASCII folder) to ``Z:\\…``, round-trip safe.
* Wrong-architecture and missing-.NET launches exit within 0.5 s with the reason on their
  output, so the launch is watched for ``WATCH_SECONDS``; good launches keep running.
"""

from __future__ import annotations

import stat
import struct
from pathlib import Path
from typing import Literal

from ctstudio.core.errors import CTStudioError, ToolFailed, ToolNotFound
from ctstudio.core.tools.process import launch_detached, run

Arch = Literal["win32", "win64"]
WATCH_SECONDS = 3.0
WINEPATH_TIMEOUT = 60.0
_PE_KINDS: dict[tuple[int, int], Arch] = {(0x14C, 0x10B): "win32", (0x8664, 0x20B): "win64"}
_HEADER_BYTES = 4096
_BAD_FORMAT = "Bad EXE format"
_NO_DOTNET = "Wine Mono is not installed"


class WineError(CTStudioError):
    """A Windows program cannot be started in this Wine prefix."""


def _not_windows(exe: Path) -> WineError:
    return WineError(
        f"{exe.name} is not a Windows program.",
        hint="Choose the editor's .exe file.",
    )


def exe_arch(exe: Path) -> Arch:
    """The prefix architecture a Windows program needs, from its PE header."""
    with exe.open("rb") as handle:
        head = handle.read(_HEADER_BYTES)
        if head[:2] != b"MZ" or len(head) < 0x40:
            raise _not_windows(exe)
        offset = struct.unpack_from("<I", head, 0x3C)[0]
        handle.seek(offset)
        pe = handle.read(26)
    if len(pe) < 26 or pe[:4] != b"PE\0\0":
        raise _not_windows(exe)
    machine, magic = struct.unpack_from("<H", pe, 4)[0], struct.unpack_from("<H", pe, 24)[0]
    arch = _PE_KINDS.get((machine, magic))
    if arch is None:
        raise WineError(
            f"{exe.name} is not a 32- or 64-bit x86 Windows program.",
            hint="Download the editor's x86 or x64 Windows build.",
        )
    return arch


def prefix_arch(prefix: Path) -> Arch:
    """The architecture recorded in the prefix's ``system.reg`` header."""
    registry = prefix / "system.reg"
    try:
        if not stat.S_ISREG(registry.stat().st_mode):
            raise ValueError("the prefix registry is not a regular file")
    except (OSError, ValueError, RuntimeError) as error:
        raise WineError(
            f"{prefix} is not a Wine prefix.",
            hint=f'Create it with: WINEPREFIX="{prefix}" wineboot -u',
        ) from error
    with registry.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("#arch="):
                value = line.removeprefix("#arch=").strip()
                if value in ("win32", "win64"):
                    return "win32" if value == "win32" else "win64"
                break
            if line.startswith("["):  # header over; keys start here
                break
    raise WineError(
        f"The architecture of the Wine prefix {prefix} is unknown.",
        hint="Use a prefix created by wineboot with WINEARCH=win32 or win64.",
    )


def _env(prefix: Path) -> dict[str, str]:
    return {"WINEPREFIX": str(prefix)}


def windows_path(path: Path, *, wine: Path, prefix: Path) -> str:
    """``path`` as the Windows program in ``prefix`` sees it (``winepath.exe -w``)."""
    result = run(
        [wine, "winepath.exe", "-w", path],
        cwd=path.parent,
        env=_env(prefix),
        timeout=WINEPATH_TIMEOUT,
    )
    lines = result.stdout_tail.strip().splitlines()
    answer = lines[-1].strip() if lines else ""
    if len(answer) < 4 or answer[1:3] != ":\\" or not answer[0].isalpha():
        raise WineError(
            f"winepath could not convert {path.name} for Wine.",
            hint="Check that Wine works: run `wine winecfg` once in this prefix.",
            details=f"winepath stdout: {result.stdout_tail!r}",
        )
    return answer


def _check_prefix(exe: Path, prefix: Path) -> None:
    program_arch = exe_arch(exe)
    installed_arch = prefix_arch(prefix)
    if program_arch == "win64" and installed_arch == "win32":
        raise WineError(
            f"{exe.name} is a 64-bit program and cannot run in the 32-bit Wine prefix {prefix}.",
            hint='Use a 64-bit prefix: WINEARCH=win64 WINEPREFIX="<new folder>" wineboot -u',
        )


def _explained(error: ToolFailed, exe: Path, prefix: Path) -> CTStudioError:
    if _NO_DOTNET in error.stderr_tail:
        return WineError(
            f"{exe.name} needs Microsoft .NET, which this Wine prefix does not have.",
            hint=f'Run: WINEPREFIX="{prefix}" winetricks -q dotnet48 win10',
            details=error.details,
        )
    if _BAD_FORMAT in error.stderr_tail:
        return WineError(
            f"Wine could not start {exe.name}: wrong architecture for the prefix {prefix}.",
            hint="Use a win64 prefix for 64-bit editors and a win32 prefix for 32-bit ones.",
            details=error.details,
        )
    return error


def _safe_text(text: str) -> None:
    text.encode("utf-8")
    if "\0" in text:
        raise ValueError("text contains NUL")


def _runtime_path(path: Path, role: str, *, directory: bool = False) -> Path:
    try:
        _safe_text(str(path))
        resolved = path.resolve(strict=True)
        mode = resolved.stat().st_mode
        if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
            raise ValueError("not a directory" if directory else "not a regular file")
        return resolved
    except (OSError, ValueError, RuntimeError) as error:
        hint = f"Choose an existing, readable {role} {'directory' if directory else 'file'}."
        if role == "Wine":
            raise ToolNotFound("Wine", hint="Install Wine or choose its executable.") from error
        raise WineError(
            f"Could not inspect the {role} path.", hint=hint, details=str(error)
        ) from error


def validate_runtime(exe: Path, *, wine: Path, prefix: Path) -> tuple[Path, Path, Path]:
    """Return canonical program/Wine/prefix paths; freshly inspect both PE/prefix headers."""
    wine = _runtime_path(wine, "Wine")
    exe = _runtime_path(exe, "Windows program")
    prefix = _runtime_path(prefix, "Wine prefix", directory=True)
    try:
        _check_prefix(exe, prefix)
    except (OSError, ValueError, RuntimeError) as error:
        raise WineError(
            "Could not read the Windows program or Wine prefix.",
            hint="Check the program and prefix permissions, or select them again.",
            details=str(error),
        ) from error
    return exe, wine, prefix


def _start(exe: Path, arguments: tuple[str, ...], *, cwd: Path, wine: Path, prefix: Path) -> int:
    try:
        for token in arguments:
            _safe_text(token)
    except ValueError as error:
        raise WineError(
            "The Wine arguments contain unsafe text.",
            hint="Remove NUL or invalid Unicode from the editor arguments.",
        ) from error
    try:
        return launch_detached(
            [wine, exe, *arguments], cwd=cwd, env=_env(prefix), watch=WATCH_SECONDS
        )
    except ToolFailed as error:
        explained = _explained(error, exe, prefix)
        if explained is error:
            raise
        raise explained from error


def launch_argv(
    exe: Path, arguments: tuple[str, ...], *, cwd: Path, wine: Path, prefix: Path
) -> int:
    """Start complete opaque argument tokens; conversion belongs to the caller."""
    exe, wine, prefix = validate_runtime(exe, wine=wine, prefix=prefix)
    cwd = _runtime_path(cwd, "working", directory=True)
    return _start(exe, arguments, cwd=cwd, wine=wine, prefix=prefix)


def launch(exe: Path, document: Path, options: tuple[str, ...], *, wine: Path, prefix: Path) -> int:
    """Start ``exe`` on ``document`` in ``prefix``; raise if Wine gives up at once."""
    exe, wine, prefix = validate_runtime(exe, wine=wine, prefix=prefix)
    target = windows_path(document, wine=wine, prefix=prefix)
    return _start(exe, (target, *options), cwd=document.parent, wine=wine, prefix=prefix)
