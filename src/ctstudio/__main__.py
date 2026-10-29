"""`ctstudio` entry point.

No arguments launch the GUI; `--offscreen-smoke` captures a headless PNG; `doctor` checks
the external tools (P2-T06). Only the stdlib and package metadata are imported until a path
is selected, and CLI subcommands never import Qt.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ctstudio import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ctstudio",
        description="Turn a Blender project into a finished Mario Kart Wii custom track (.szs).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--offscreen-smoke",
        type=Path,
        metavar="PNG",
        help="render the dashboard to a PNG without opening a display, then exit",
    )
    from ctstudio.cli import doctor

    subcommands = parser.add_subparsers(dest="command", metavar="COMMAND")
    doctor.add_parser(subcommands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` (default: ``sys.argv[1:]``) and return the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return _doctor(args)
    if args.offscreen_smoke is not None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from ctstudio.core.errors import CTStudioError
    from ctstudio.core.logging import configure_logging
    from ctstudio.gui.app import run_gui

    try:
        configure_logging()
        return run_gui(args.offscreen_smoke)
    except CTStudioError as exc:
        print(exc, file=sys.stderr)
        return 1


def _doctor(args: argparse.Namespace) -> int:
    from ctstudio.cli import doctor
    from ctstudio.core.errors import CTStudioError
    from ctstudio.core.logging import configure_logging

    try:
        configure_logging()
        return doctor.run(args)
    except CTStudioError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
