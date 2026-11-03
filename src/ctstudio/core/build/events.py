"""What a build reports while it runs (ARCHITECTURE §4 "Event", §7).

Plain frozen dataclasses delivered one at a time through a callback on the thread that
called ``run_build``; the GUI turns them into Qt signals and the CLI prints them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ctstudio.core.validation.issues import Issue

Outcome = Literal["succeeded", "failed", "cancelled"]


@dataclass(frozen=True)
class BuildStarted:
    steps: tuple[str, ...]  # every step of the build, in build order


@dataclass(frozen=True)
class NodeStarted:
    node_id: str


@dataclass(frozen=True)
class LogLine:
    node_id: str
    text: str


@dataclass(frozen=True)
class NodeSkipped:
    """Nothing the step depends on changed since it last ran, so its files were kept."""

    node_id: str


@dataclass(frozen=True)
class NodeFinished:
    node_id: str
    duration: float  # seconds
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class NodeFailed:
    node_id: str
    message: str
    hint: str | None
    cancelled: bool  # stopped because the user cancelled, not because of a problem
    issues: tuple[Issue, ...] = ()  # what to fix, when the step said (``StepFailed``)


@dataclass(frozen=True)
class BuildSummary:
    """Step ids by what happened to them, each in build order."""

    outcome: Outcome
    ran: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]
    cancelled: tuple[str, ...]
    not_run: tuple[str, ...]  # never started because the build stopped first
    issues: tuple[Issue, ...]
    duration: float  # seconds
    log: Path | None  # this build's log file, None when it could not be written


@dataclass(frozen=True)
class BuildFinished:
    summary: BuildSummary


type BuildEvent = (
    BuildStarted | NodeStarted | LogLine | NodeSkipped | NodeFinished | NodeFailed | BuildFinished
)
