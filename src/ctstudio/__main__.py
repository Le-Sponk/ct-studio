"""`ctstudio` entry point.

No arguments launch the GUI; `--offscreen-smoke` captures a headless PNG.
Only the stdlib and package metadata are imported until a GUI path is selected.
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` (default: ``sys.argv[1:]``) and return the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
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


if __name__ == "__main__":
    sys.exit(main())
