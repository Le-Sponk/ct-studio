"""Command-line subcommands. Each module has ``add_parser(subparsers)`` and ``run(args)``.

None of them imports Qt (``tests/unit/test_cli_project.py`` checks).
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from typing import Protocol

from ctstudio.cli import doctor, new, open_file, setup, status


class Command(Protocol):
    def add_parser(
        self, subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
    ) -> None: ...

    def run(self, args: argparse.Namespace) -> int: ...


COMMANDS: Mapping[str, Command] = {
    "new": new,
    "status": status,
    "open": open_file,
    "doctor": doctor,
    "setup": setup,
}
