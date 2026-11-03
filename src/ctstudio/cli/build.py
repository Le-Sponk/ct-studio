"""``ctstudio build``: build a project's track from the command line (P4-T07b).

The build runs on its own thread so Ctrl+C can cancel it: nothing new starts, running steps
finish (a running tool is stopped), and the last good track is kept. Text output prints one
line per step as it ends, with that step's log lines under it (steps run in parallel, so
lines are held until the step ends); ``--json-events`` prints each event as a JSON line
instead (schema in ``docs/dev/CLI.md``). Exit status: 0 built, 1 failed or could not start,
2 bad command line (argparse), 3 cancelled.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ctstudio.core.build.event_json import event_to_json
from ctstudio.core.build.events import (
    BuildEvent,
    BuildFinished,
    BuildStarted,
    BuildSummary,
    LogLine,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
)
from ctstudio.core.build.project_build import BuildPlan, build_project, plan_build
from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import settings
from ctstudio.core.project.project import Project
from ctstudio.core.project.settings import SettingsError, UserSettings
from ctstudio.core.project.slots import find
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.validation.issues import Issue

FAILED, CANCELLED = 1, 3
PARTS = [spec.id for spec in COMPONENTS if spec.outputs]
_EXIT = {"succeeded": 0, "failed": FAILED, "cancelled": CANCELLED}
_STEPS = {"assemble": "Pack the track", "validate": "Check the track"}
_WAIT = 0.1  # seconds between checks for Ctrl+C while the build runs


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "build",
        help="build the track",
        description="Build the project in FOLDER (default: this folder) into build/<slot>.szs. "
        "Exit status: 0 built, 1 failed or could not start, 2 bad command line, 3 cancelled.",
    )
    parser.add_argument("folder", nargs="?", type=Path, default=Path(), help="the project folder")
    parser.add_argument(
        "--release",
        action="store_true",
        help="release build: strongest compression, and an error found by the check fails it",
    )
    parser.add_argument("--force", action="store_true", help="rebuild every step")
    parser.add_argument(
        "--only", choices=PARTS, metavar="PART", help=f"build one part only: {', '.join(PARTS)}"
    )
    parser.add_argument(
        "--json-events", action="store_true", help="print each build event as a JSON line"
    )


def run(args: argparse.Namespace) -> int:
    root: Path = args.folder.resolve()
    user = _user_settings()
    cancel = CancelToken()
    try:
        with Project.open(root) as project:
            if project.read_only:
                raise ProjectError(
                    "This project is open in CT Studio, so it was not built.",
                    hint=f"{project.read_only_reason}. Close it there, or build from the app.",
                )
            plan = plan_build(
                root,
                project.manifest,
                "release" if args.release else "test",
                only=args.only,
                configured=user.configured(),
                library=user.auto_add_library(),
            )
            show = _json_printer(root) if args.json_events else _TextPrinter(root, plan)
            summary = _run(plan, show, cancel, force=args.force)
    except KeyboardInterrupt:
        print("\nBuild cancelled before it started.", file=sys.stderr)
        return CANCELLED
    return _EXIT[summary.outcome]


def _user_settings() -> UserSettings:
    """CT Studio's settings; a damaged file is reported, then left out."""
    try:
        return settings.load()
    except SettingsError as exc:
        print(
            f"Warning: {exc.user_message}\nPaths set in CT Studio are ignored for this build.",
            file=sys.stderr,
        )
        return UserSettings()


def _run(
    plan: BuildPlan, show: Callable[[BuildEvent], None], cancel: CancelToken, *, force: bool
) -> BuildSummary:
    """Run the build on its own thread; Ctrl+C (KeyboardInterrupt here) cancels it."""
    result: list[BuildSummary] = []
    failure: list[BaseException] = []

    def work() -> None:
        try:
            result.append(build_project(plan, show, cancel=cancel, force=force))
        except BaseException as exc:  # handed to the main thread and raised there
            failure.append(exc)

    worker = threading.Thread(target=work, name="ctstudio-build", daemon=True)
    while True:
        try:  # Ctrl+C can land anywhere here, even while the thread is starting
            if worker.ident is None:  # not started yet (a Ctrl+C came before it was)
                worker.start()
            while worker.is_alive():
                worker.join(_WAIT)
            break
        except KeyboardInterrupt:
            cancel.cancel()
            print("\nCancelling: running steps finish first.", file=sys.stderr, flush=True)
    if failure:
        raise failure[0]
    return result[0]


def _json_printer(root: Path) -> Callable[[BuildEvent], None]:
    def show(event: BuildEvent) -> None:
        print(json.dumps(event_to_json(event, root), ensure_ascii=False), flush=True)

    return show


def step_name(step: str) -> str:
    """The step in plain words: "Copy Collision", "Pack the track"."""
    if step.startswith("stage:"):
        return f"Copy {COMPONENT_BY_ID[step.removeprefix('stage:')].name}"
    return _STEPS.get(step, step)


@dataclass
class _TextPrinter:
    root: Path
    plan: BuildPlan
    held: defaultdict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    told: set[str] = field(default_factory=lambda: set())  # failure messages already printed

    def __call__(self, event: BuildEvent) -> None:
        if isinstance(event, LogLine):
            self.held[event.node_id].append(event.text)
            return
        lines = self._lines(event)
        if lines:
            print("\n".join(lines), flush=True)

    def _lines(self, event: BuildEvent) -> list[str]:
        match event:
            case BuildStarted(steps):
                return [self._header(len(steps))]
            case NodeFinished(step, duration):
                return [f"  done       {step_name(step)} ({duration:.2f} s)", *self._log(step)]
            case NodeSkipped(step):
                return [f"  unchanged  {step_name(step)}"]
            case NodeFailed():
                return self._failed(event)
            case BuildFinished(summary):
                return self._end(summary)
            case _:
                return []

    def _failed(self, event: NodeFailed) -> list[str]:
        self.told.add(event.message)
        word = "cancelled" if event.cancelled else "FAILED   "
        lines = [f"  {word}  {step_name(event.node_id)}", *self._log(event.node_id)]
        lines.append(f"             {event.message}")
        if event.hint and not event.cancelled:
            lines.append(f"             {event.hint}")
        return lines

    def _log(self, step: str) -> list[str]:
        return [f"             {text}" for text in self.held.pop(step, [])]

    def _header(self, count: int) -> str:
        manifest = self.plan.request.manifest
        slot = find(manifest.project.slot).label
        steps = f"{count} step{'s' if count != 1 else ''}"
        kind = f"{self.plan.request.profile} build"
        return f"Building {manifest.project.name}, replacing {slot}: {kind}, {steps}"

    def _end(self, summary: BuildSummary) -> list[str]:
        found = [issue for issue in summary.issues if issue.message not in self.told]
        lines = [""]
        if found:
            lines += ["Found while building:", *(_issue_lines(i) for i in found), ""]
        counts = [
            f"{len(steps)} {word}"
            for steps, word in (
                (summary.ran, "done"),
                (summary.skipped, "unchanged"),
                (summary.failed, "failed"),
                (summary.cancelled, "cancelled"),
                (summary.not_run, "not run"),
            )
            if steps
        ]
        lines.append(f"Build {summary.outcome}: {', '.join(counts)} in {summary.duration:.1f} s.")
        if summary.outcome == "succeeded" and "assemble" in summary.ran + summary.skipped:
            lines.append(f"Track: build/{self.plan.request.manifest.project.slot}.szs")
        if summary.log is not None:
            lines.append(f"Log: {_shown(summary.log, self.root)}")
        return lines


def _issue_lines(issue: Issue) -> str:
    lines = [f"  {issue.severity:<8} {issue.message}"]
    if issue.hint:
        lines.append(f"           {issue.hint}")
    return "\n".join(lines)


def _shown(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
