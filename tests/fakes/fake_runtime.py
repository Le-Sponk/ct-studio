"""Shared runtime for the fake external tools (P2-T04b).

A fake never pretends: anything its recordings do not pin down raises ``Unmodelled``, which
exits ``UNMODELLED_EXIT`` (121, a code no real tool here uses) before any output or file
write, so a test that strays outside what was measured fails loudly instead of passing on
invented behaviour. Commands build an ``Outcome`` first; ``finish`` applies it.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOG_ENV = "CT_STUDIO_FAKE_TOOL_LOG"
UNMODELLED_EXIT = 121
RECORDINGS = Path(__file__).resolve().parent / "recordings"


class Unmodelled(Exception):
    """The recordings do not say what the real tool does here."""


@dataclass
class Outcome:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    writes: list[tuple[Path, bytes]] = field(default_factory=list)
    make_parents: bool = False  # create missing folders for ``writes`` (Wiimm ``--DEST``)


class Refused(Exception):
    """The real tool stops with this outcome (its own error); nothing is written."""

    def __init__(self, outcome: Outcome) -> None:
        super().__init__(outcome.stderr)
        self.outcome = outcome


def recordings(tool: str, version: str, kind: str) -> Any:
    """``<os>-<kind>.json`` for this OS, falling back to the Windows recording."""
    folder = RECORDINGS / tool / version
    mine = folder / f"{'windows' if os.name == 'nt' else 'linux'}-{kind}.json"
    path = mine if mine.exists() else folder / f"windows-{kind}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def log_call(tool: str, argv: Sequence[str]) -> None:
    """One file per call in the ``LOG_ENV`` folder.

    A shared append-only file loses lines on Windows when probes run in parallel: the C
    runtime emulates ``O_APPEND`` with a seek before each write, which is not atomic across
    processes. Names start with a nanosecond clock, so sorting them gives call order.
    """
    folder = os.environ.get(LOG_ENV)
    if not folder:
        return
    record = {"tool": tool, "argv": list(argv), "cwd": os.getcwd()}
    name = f"{time.time_ns():020d}-{os.getpid()}.json"
    Path(folder, name).write_text(json.dumps(record), encoding="utf-8")


def finish(tool: str, argv: Sequence[str], run: Callable[[], Outcome]) -> int:
    log_call(tool, argv)
    try:
        outcome = run()
    except Refused as refused:
        outcome = refused.outcome
    except Unmodelled as exc:
        _emit(sys.stderr, f"fake {tool}: not modelled: {exc}\n")
        return UNMODELLED_EXIT
    for path, data in outcome.writes:
        if outcome.make_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    _emit(sys.stdout, outcome.stdout)
    _emit(sys.stderr, outcome.stderr)
    return outcome.exit_code


def _emit(stream: object, text: str) -> None:
    # Bytes, so Windows text mode cannot turn "\n" into "\r\n": the real tools print "\n".
    buffer = stream.buffer  # type: ignore[attr-defined]
    buffer.write(text.encode("utf-8"))
    buffer.flush()
