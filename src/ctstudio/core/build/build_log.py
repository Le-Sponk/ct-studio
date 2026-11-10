"""The per-build log: ``.ctstudio/logs/build-<UTC time>.log`` (ARCHITECTURE §14).

One readable line per build event, time-stamped in UTC, so a user can send the file when
asking for help. After each build only the newest ``KEEP`` logs are kept. The log is a help,
not part of the build: when it cannot be written, it says so in the app log and stops.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from ctstudio.core.build.events import (
    BuildEvent,
    BuildFinished,
    BuildStarted,
    BuildSummary,
    CommandRun,
    LogLine,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
)

LOG_DIR = ".ctstudio/logs"
KEEP = 20
_LOG = logging.getLogger(__name__)
_PATTERN = "build-*.log"


class BuildLog:
    def __init__(self, path: Path | None, stream: TextIO | None) -> None:
        self.path = path
        self._stream = stream

    @classmethod
    def open(cls, root: Path) -> BuildLog:
        folder = root / LOG_DIR
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for n in range(100):
                path = folder / f"build-{stamp}{f'-{n}' if n else ''}.log"
                try:
                    return cls(path, path.open("x", encoding="utf-8", newline="\n"))
                except FileExistsError:
                    continue
        except OSError as exc:
            _LOG.warning("could not write the build log in %s: %s", folder, exc)
        return cls(None, None)

    def write(self, event: BuildEvent) -> None:
        if self._stream is None:
            return
        try:
            for text in _lines(event):
                self._stream.write(f"{_now()} {text}\n")
            self._stream.flush()
        except OSError as exc:
            _LOG.warning("stopped writing the build log %s: %s", self.path, exc)
            self.close()

    def close(self) -> None:
        if self._stream is not None:
            stream, self._stream = self._stream, None
            try:
                stream.close()
            except OSError as exc:
                _LOG.warning("could not finish the build log %s: %s", self.path, exc)


def prune(root: Path, keep: int = KEEP) -> None:
    """Delete all but the newest ``keep`` build logs (names sort by time)."""
    folder = root / LOG_DIR
    try:
        old = sorted(folder.glob(_PATTERN))[:-keep]
        for path in old:
            path.unlink(missing_ok=True)
    except OSError as exc:
        _LOG.warning("could not remove old build logs in %s: %s", folder, exc)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _lines(event: BuildEvent) -> list[str]:
    match event:
        case BuildStarted(steps):
            return [f"Build started: {len(steps)} steps ({', '.join(steps)})"]
        case BuildFinished(summary):
            return [_summary(summary)]
        case _:
            return [f"[{event.node_id}] {text}" for text in _step_lines(event)]


def _step_lines(
    event: NodeStarted | LogLine | CommandRun | NodeSkipped | NodeFinished | NodeFailed,
) -> list[str]:
    match event:
        case NodeStarted():
            return ["started"]
        case LogLine(_, text):
            return text.splitlines() or [""]
        case CommandRun(_, _, text):
            return [f"command: {text}"]
        case NodeSkipped(_, issues):
            notes = [f"{i.severity}: {_join(i.message, i.hint)} (found before)" for i in issues]
            return ["skipped: nothing it uses changed", *notes]
        case NodeFinished(_, duration, issues):
            notes = [f"{i.severity}: {_join(i.message, i.hint)}" for i in issues]
            return [*notes, f"finished in {duration:.2f} s"]
        case NodeFailed(_, message, hint, cancelled, _issues, details):
            return _failed_lines(message, hint, cancelled, details)


def _failed_lines(
    message: str, hint: str | None, cancelled: bool, details: str | None
) -> list[str]:
    said = [f"tool output: {line}" for line in (details or "").splitlines()]
    return [f"{'cancelled' if cancelled else 'FAILED'}: {_join(message, hint)}", *said]


def _join(message: str, hint: str | None) -> str:
    return f"{message} {hint}" if hint else message


def _summary(s: BuildSummary) -> str:
    text = (
        f"Build {s.outcome}: {len(s.ran)} ran, {len(s.skipped)} skipped,"
        f" {len(s.failed)} failed, {len(s.not_run)} not run"
    )
    if s.cancelled:
        text += f" ({len(s.cancelled)} cancelled)"
    return text + f" in {s.duration:.1f} s"
