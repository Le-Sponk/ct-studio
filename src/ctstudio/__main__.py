"""`ctstudio` entry point.

With no arguments this will launch the GUI (P1-T06); with a subcommand it runs the CLI.
Only the stdlib is imported here so `ctstudio --version` stays fast and Qt-free.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from ctstudio import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ctstudio",
        description="Turn a Blender project into a finished Mario Kart Wii custom track (.szs).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` (default: ``sys.argv[1:]``) and return the process exit code."""
    parser = _build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
