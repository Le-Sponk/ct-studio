"""Build events as plain JSON objects, one per line of ``ctstudio build --json-events`` (P4-T07b).

The schema is in ``docs/dev/CLI.md`` and the tests check every line against it. Each object
has ``format`` and ``event``; issues are written as in ``issues.json`` (a file inside the
project is relative to it, with "/"). Step ids are the build's own (``stage:kcl``,
``assemble``, ``validate``).
"""

from __future__ import annotations

from pathlib import Path

from ctstudio.core.build.events import (
    BuildEvent,
    BuildFinished,
    BuildStarted,
    CommandRun,
    LogLine,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
)
from ctstudio.core.validation.issues import Issue, issue_to_json

FORMAT = 1


def event_to_json(event: BuildEvent, root: Path) -> dict[str, object]:
    """``event`` as JSON; ``root`` is the project folder that paths are made relative to."""
    return {"format": FORMAT, **_fields(event, root)}


def _fields(event: BuildEvent, root: Path) -> dict[str, object]:
    match event:
        case BuildStarted(steps):
            return {"event": "build_started", "steps": list(steps)}
        case NodeStarted(step):
            return {"event": "step_started", "step": step}
        case LogLine(step, text):
            return {"event": "log", "step": step, "text": text}
        case CommandRun(step, argv, text):
            return {"event": "command", "step": step, "argv": list(argv), "text": text}
        case NodeSkipped(step, issues):
            return {"event": "step_skipped", "step": step, "issues": _issues(issues, root)}
        case NodeFinished(step, duration, issues):
            return {
                "event": "step_finished",
                "step": step,
                "duration": round(duration, 3),
                "issues": _issues(issues, root),
            }
        case NodeFailed(step, message, hint, cancelled, issues):
            return {
                "event": "step_failed",
                "step": step,
                "message": message,
                "hint": hint,
                "cancelled": cancelled,
                "issues": _issues(issues, root),
            }
        case BuildFinished(summary):
            log = summary.log
            return {
                "event": "build_finished",
                "outcome": summary.outcome,
                "ran": list(summary.ran),
                "skipped": list(summary.skipped),
                "failed": list(summary.failed),
                "cancelled": list(summary.cancelled),
                "not_run": list(summary.not_run),
                "issues": _issues(summary.issues, root),
                "duration": round(summary.duration, 3),
                "log": None if log is None else _relative(log, root),
            }


def _issues(issues: tuple[Issue, ...], root: Path) -> list[dict[str, object]]:
    return [issue_to_json(issue, root) for issue in issues]


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
