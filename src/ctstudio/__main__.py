"""`ctstudio` entry point.

No arguments launch the GUI; `--offscreen-smoke` captures a headless PNG; `doctor` checks
the external tools (P2-T06); `setup rszst` fetches or builds RiiStudio's CLI (P2-T06b);
`new`, `status` and `open` make, check and edit projects (P3-T07).
Only the stdlib is imported until a path is selected (the version on `--version` only), and CLI
subcommands never import Qt.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from collections.abc import Sequence
from pathlib import Path


class _ShowVersion(argparse.Action):
    """``--version``, reading the version only when asked (argparse's action needs it up front)."""

    def __init__(self, option_strings: Sequence[str], dest: str, **_: object) -> None:
        super().__init__(
            option_strings,
            dest,
            nargs=0,
            default=argparse.SUPPRESS,
            help="show program's version number and exit",
        )

    def __call__(self, parser: argparse.ArgumentParser, *_: object) -> None:
        from ctstudio import version

        sys.stdout.write(f"{parser.prog} {version()}\n")
        parser.exit()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ctstudio",
        description="Turn a Blender project into a finished Mario Kart Wii custom track (.szs).",
    )
    parser.add_argument("--version", action=_ShowVersion)
    parser.add_argument(
        "--offscreen-smoke",
        type=Path,
        metavar="PNG",
        help="render the dashboard to a PNG without opening a display, then exit",
    )
    from ctstudio.cli import COMMANDS

    subcommands = parser.add_subparsers(dest="command", metavar="COMMAND")
    for command in COMMANDS.values():
        command.add_parser(subcommands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` (default: ``sys.argv[1:]``) and return the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is not None:
        return _cli(args)
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


def _cli(args: argparse.Namespace) -> int:
    from ctstudio.cli import COMMANDS
    from ctstudio.core.errors import CTStudioError
    from ctstudio.core.logging import configure_logging

    _utf8_output()
    try:
        configure_logging()
        return COMMANDS[args.command].run(args)
    except CTStudioError as exc:
        print(exc, file=sys.stderr)
        return 1


def _utf8_output() -> None:
    """Command output is UTF-8 everywhere (CLI.md). Windows otherwise writes redirected
    output in the ANSI code page, where a name such as "Pistë" or "日本" cannot be written."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    sys.exit(main())
