"""Scrub per-run noise from recorded tool output (split from ``record_tool_outputs.py``).

Only values that change on every run are replaced (durations, PyInstaller PIDs, elapsed time);
diagnostics stay byte-for-byte, so the fakes replay what the real tools print.
"""

from __future__ import annotations

import re


def normalize_abmatt(record: dict[str, object]) -> dict[str, object]:
    """Scrub ABMatt's process-specific seconds and PyInstaller PID, not diagnostics."""
    stdout = re.sub(
        r"(?<=\.\.\. finished in )\d+(?:\.\d+)?(?= secs)", "<duration>", str(record["stdout"])
    )
    stderr = re.sub(
        r"\[\d+\](?= Failed to execute script '?__main__)", "[<pid>]", str(record["stderr"])
    )
    return {**record, "stdout": stdout, "stderr": stderr}


def normalize_wszst(record: dict[str, object]) -> dict[str, object]:
    """Scrub only ``analyze --json``'s per-run ``duration_usec`` value."""
    stdout = re.sub(r'(?<="duration_usec":)\d+(?=})', '"<usec>"', str(record["stdout"]))
    return {**record, "stdout": stdout}


def normalize_blender(record: dict[str, object]) -> dict[str, object]:
    """Only scrub Blender's variable report-time prefix, not its build time."""
    stdout = re.sub(
        r"(?m)^\d\d:\d\d\.\d{3}(?=  (?:reports|blend)\s+\|)", "<elapsed>", str(record["stdout"])
    )
    return {**record, "stdout": stdout}
