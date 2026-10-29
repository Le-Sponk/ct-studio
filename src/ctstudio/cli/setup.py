"""``ctstudio setup rszst``: get RiiStudio's CLI when it is not installed (P2-T06b).

Always user-initiated (ADR-004: RiiStudio is never bundled). Windows downloads the pinned
official release; Linux builds the pinned source, which takes about an hour and is shown
step by step. ``--dry-run`` explains the plan and checks the machine without changing it.
Exit 0 on success or when rszst is already installed, 1 on failure, 130 when cancelled.
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
from ctstudio.core.tools.rszst_install import build_linux, download_windows
from ctstudio.core.tools.rszst_setup import (
    BUILD_ESTIMATE,
    EXPECTED_TOOLCHAIN,
    PIN,
    Step,
    build_steps,
    managed_root,
    preflight,
)

CANCELLED = 130


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "setup",
        help="install a missing tool CT Studio can fetch for you",
        description="Get RiiStudio's command-line tool (rszst). Windows: download the "
        "official release. Linux: build it from source (about 1 hour).",
    )
    parser.add_argument("tool", choices=["rszst"], help="the tool to set up")
    parser.add_argument("--dry-run", action="store_true", help="explain and check, change nothing")
    parser.add_argument("--jobs", type=int, default=None, help="Linux build: parallel jobs")


def _data_dir() -> Path:
    return ct_platform.user_directories().data


def _existing() -> Path | None:
    """An rszst the user installed themselves (PATH, standard folders, setting)."""
    found = discover(TOOL_BY_ID["rszst"])
    return found.path if found is not None and found.source != "managed" else None


def run(args: argparse.Namespace) -> int:
    platform = current_os()
    if platform == "other":
        print("CT Studio can set up rszst on only Windows and Linux.", file=sys.stderr)
        return 1
    existing = _existing()
    if existing is not None:
        print(f"rszst is already installed: {existing.as_posix()}")
        return 0
    root = managed_root(_data_dir())
    token = CancelToken()
    try:
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


def _windows(root: Path, dry_run: bool, token: CancelToken) -> int:
    size = round(PIN.windows_zip_bytes / 1_000_000)
    print(f"RiiStudio {PIN.version} is downloaded from its official release ({size} MB):")
    print(f"  {PIN.windows_zip_url}")
    print("It is never bundled with CT Studio; its overall licence is unconfirmed.")
    print(f"The download is checked against SHA-256 {PIN.windows_zip_sha256}.")
    print(f"It goes into {root}")
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


def _step(number: int, total: int, step: Step) -> None:
    print(f"Step {number} of {total}: {step.name}", flush=True)


def _progress(done: int, total: int) -> None:
    end = "\n" if done >= total else ""
    print(f"\r  {done / 1e6:.1f} of {total / 1e6:.1f} MB", end=end, flush=True)
