"""Python-interpreter fake tools shared by the P2-T03 process-runner tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Fake tools are this interpreter running inline code (portable-spawning rule: no .sh fakes).
PRELUDE = r"""
import os, pathlib, subprocess, sys, time
def out(text, stream=sys.stdout):
    stream.buffer.write(text.encode("utf-8") + b"\n")
    stream.buffer.flush()
def err(text):
    out(text, sys.stderr)
def wait_for(path):
    target = pathlib.Path(path)
    for _ in range(500):
        if target.exists():
            return
        time.sleep(0.01)
    raise SystemExit("handshake timed out: " + path)
"""


def fake(code: str, *args: str | Path) -> list[str | Path]:
    """Argv for a fake tool whose body is ``code``; helpers ``out``/``err``/``wait_for``."""
    return [sys.executable, "-c", PRELUDE + code, *args]
