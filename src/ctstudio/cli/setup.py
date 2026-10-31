"""``ctstudio setup rszst``: get RiiStudio's CLI when it is not installed (P2-T06b).

Always user-initiated (ADR-004: RiiStudio is never bundled). Windows downloads the pinned
official release; Linux builds the pinned source, which takes about an hour and is shown
step by step, or with ``--wine`` (P2-T06e) sets up the Windows release to run through Wine
in about a minute. ``--dry-run`` explains the plan and checks the machine without changing
it. Exit 0 on success or when rszst is already installed, 1 on failure, 130 when cancelled.
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path

from ctstudio.core import platform as ct_platform
from ctstudio.core.errors import Cancelled, CTStudioError
from ctstudio.core.platform import current_os
from ctstudio.core.tools.discovery import discover
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.rszst_install import SetupFailed, build_linux, download_windows
from ctstudio.core.tools.rszst_setup import (
    BUILD_ESTIMATE,
    EXPECTED_TOOLCHAIN,
    PIN,
    Step,
    build_steps,
    managed_root,
    preflight,
    wine_environment,
    wine_root,
)
from ctstudio.core.tools.rszst_wine import INSTALL_WINE, install_wine

CANCELLED = 130


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "setup",
        help="install a missing tool CT Studio can fetch for you",
        description="Get RiiStudio's command-line tool (rszst). Windows: download the "
        "official release. Linux: build it from source (about 1 hour), or with --wine run "
        "the official Windows release through Wine (about 1 minute).",
    )
    parser.add_argument("tool", choices=["rszst"], help="the tool to set up")
    parser.add_argument("--dry-run", action="store_true", help="explain and check, change nothing")
    parser.add_argument("--jobs", type=int, default=None, help="Linux build: parallel jobs")
    parser.add_argument(
        "--wine", action="store_true", help="Linux: use the Windows rszst.exe through Wine"
    )


def _data_dir() -> Path:
    return ct_platform.user_directories().data


def _existing() -> Path | None:
    """An rszst the user installed themselves (PATH, standard folders, setting)."""
    found = discover(TOOL_BY_ID["rszst"])
    return found.path if found is not None and found.source != "managed" else None


def _wine() -> Path | None:
    found = discover(TOOL_BY_ID["wine"])
    return found.path if found is not None else None


def run(args: argparse.Namespace) -> int:
    platform = current_os()
    if platform == "other":
        print("CT Studio can set up rszst on only Windows and Linux.", file=sys.stderr)
        return 1
    if args.wine and platform != "linux":
        print("--wine is for Linux; on Windows rszst runs directly.", file=sys.stderr)
        return 1
    existing = _existing()
    if existing is not None:
        print(f"rszst is already installed: {existing.as_posix()}")
        return 0
    token = CancelToken()
    try:
        if args.wine:
            return _through_wine(wine_root(_data_dir()), args.dry_run, token)
        root = managed_root(_data_dir())
        if platform == "windows":
            return _windows(root, args.dry_run, token)
        return _linux(root, args, token)
    except KeyboardInterrupt:
        token.cancel()
        print("\nSetup cancelled; nothing half-finished will be used.", file=sys.stderr)
        return CANCELLED
    except Cancelled as exc:
        print(exc, file=sys.stderr)
        return CANCELLED
    except CTStudioError as exc:
        print(exc, file=sys.stderr)
        return 1


def _about_download(root: Path) -> None:
    size = round(PIN.windows_zip_bytes / 1_000_000)
    print(f"RiiStudio {PIN.version} is downloaded from its official release ({size} MB):")
    print(f"  {PIN.windows_zip_url}")
    print("It is never bundled with CT Studio; its overall licence is unconfirmed.")
    print(f"The download is checked against SHA-256 {PIN.windows_zip_sha256}.")
    print(f"It goes into {root}")


def _windows(root: Path, dry_run: bool, token: CancelToken) -> int:
    _about_download(root)
    if dry_run:
        print("Nothing was changed (dry run).")
        return 0
    exe = download_windows(root, cancel=token, on_progress=_progress)
    print(f"Installed: {exe}")
    return 0


def _linux(root: Path, args: argparse.Namespace, token: CancelToken) -> int:
    jobs = args.jobs if args.jobs is not None else max(1, (os.cpu_count() or 2) // 2)
    print(f"RiiStudio has no Linux download, so CT Studio builds {PIN.version} from source.")
    print(f"Source: {PIN.source_url} at {PIN.source_tag} (commit {PIN.source_commit}).")
    print(f"This takes {BUILD_ESTIMATE} with {jobs} parallel jobs. Ctrl+C cancels at any time.")
    print(f"Everything goes into {root}; the full output is logged to {root / 'build.log'}")
    print("Quicker: `ctstudio setup rszst --wine` runs the Windows rszst.exe through Wine.")
    checked = preflight(root)
    for line in checked.lines():
        print(line)
    if args.dry_run:
        print("Commands that will run:")
        toolchain = checked.toolchain or EXPECTED_TOOLCHAIN
        for step in build_steps(root, jobs=jobs, toolchain=toolchain):
            print(f"  {shlex.join(step.argv)}")
        print("Nothing was changed (dry run).")
        return 0 if checked.ok else 1
    exe = build_linux(
        root,
        jobs=jobs,
        preflight_result=checked,
        cancel=token,
        on_step=_step,
        on_line=lambda _stream, line: print(f"    {line}"),
    )
    print(f"Installed: {exe}")
    return 0


def _through_wine(root: Path, dry_run: bool, token: CancelToken) -> int:
    print(f"CT Studio sets up the official Windows rszst.exe {PIN.version} to run through Wine.")
    print("Measured on Linux Mint: 48 of 49 checks gave the same result as on Windows. It")
    print("shares the Windows program's trouble with some file paths, which CT Studio works")
    print("around; the native program from `ctstudio setup rszst` does not need that.")
    _about_download(root / "rszst")
    wine = _wine()
    if wine is None:
        raise SetupFailed(
            "Wine is not installed, so rszst.exe cannot run.",
            hint=f"Install it with:\n  {INSTALL_WINE}",
        )
    print(f"Wine: {wine}")
    if dry_run:
        env = {**wine_environment(root), "WINEARCH": "win64"}
        print("Commands that will run:")
        print(
            f"  {shlex.join([f'{k}={v}' for k, v in env.items()] + [str(wine), 'wineboot', '-u'])}"
        )
        print("  wineserver -w")
        print(f"  {shlex.join([str(wine), str(root / 'rszst' / 'rszst.exe'), '--version'])}")
        print("Nothing was changed (dry run).")
        return 0
    exe = install_wine(root, wine=wine, cancel=token, on_progress=_progress)
    print(f"Installed: {exe} (runs through Wine)")
    return 0


def _step(number: int, total: int, step: Step) -> None:
    print(f"Step {number} of {total}: {step.name}", flush=True)


def _progress(done: int, total: int) -> None:
    end = "\n" if done >= total else ""
    print(f"\r  {done / 1e6:.1f} of {total / 1e6:.1f} MB", end=end, flush=True)
