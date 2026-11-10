"""Coordinate dashboard presentation through the existing application build owner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject

from ctstudio.core.build.events import (
    BuildEvent,
    BuildStarted,
    BuildSummary,
    CommandRun,
    LogLine,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
)
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.gui.views.build_controls import BuildControls
from ctstudio.gui.views.build_log import BuildLogPanel
from ctstudio.gui.views.dashboard_follow import DashboardFollower

if TYPE_CHECKING:
    from ctstudio.gui.views.dashboard import Dashboard


@dataclass(frozen=True)
class _Run:
    project: Project
    root: Path
    manifest: Manifest


class DashboardBuilds(QObject):
    """No work or project ownership: just requests and matching run presentation."""

    def __init__(self, page: Dashboard) -> None:
        super().__init__(page)
        self.page = page
        self._services = page.services
        self.log = BuildLogPanel(page)
        self.controls = BuildControls(page)
        self.follow = DashboardFollower(self)
        self.can_start: Callable[[], bool] = lambda: True
        self._run: _Run | None = None
        self._steps: set[str] = set()
        self._terminal: set[str] = set()
        self._working: set[str] = set()
        self._cancelled = False
        self.controls.build_requested.connect(self.start)
        self.controls.cancel_requested.connect(self.cancel)
        controller = page.services.build
        controller.build_event.connect(self._event)
        controller.finished.connect(self._finished)
        controller.failed.connect(self._failed)
        controller.notice.connect(self._notice)
        controller.running_changed.connect(self.sync)

    def sync(self, _running: bool = False) -> None:
        self.controls.set_state(
            enabled=self._eligible(), running=self._matches() and self.page.services.build.running
        )

    def _eligible(self) -> bool:
        project = self.page._project
        return (
            self.page.services is self._services
            and self.page._idle()
            and project is not None
            and not project.read_only
            and not self.page.services.status.busy
        )

    def _matches(self) -> bool:
        run = self._run
        return (
            run is not None
            and self.page.services is self._services
            and self.page._current()
            and self.page._project is run.project
            and run.project.root == run.root
            and run.project.manifest is run.manifest
        )

    def start(self, release: bool = False) -> None:
        project = self.page._project
        if not self._eligible() or project is None or not self.can_start():
            return
        self._run = _Run(project, project.root, project.manifest)
        self.log.clear()
        self.controls.clear()
        self._clear_cards()
        self.controls.begin(release)
        self.follow.start()
        try:
            started = self.page.services.start_build(release=release)
        except CTStudioError as exc:
            self._failed(exc)
        else:
            if not started and not self.page.services.build.running and self._matches():
                self._failed(RuntimeError("The build did not start. Try again."))
        self.sync()

    def cancel(self) -> None:
        """Cancellation is a request, never a shutdown or project release."""
        if self._matches() and self.page.services.build.running and not self._cancelled:
            self._cancelled = True
            self.page.services.build.cancel()

    def _notice(self, text: str) -> None:
        if self._matches():
            self.controls.show_notice(text)

    def _failed(self, payload: object) -> None:
        if self._matches() and isinstance(payload, BaseException):
            text = "failed" if isinstance(payload, Exception) else "cancelled"
            self._end_unfinished(text)
            self.controls.show_error(payload)
        self._run = None
        self.sync()

    def _end_unfinished(self, text: str) -> None:
        for step in self._steps - self._terminal:
            self._show_step(step, text if step in self._working else "not run")
        self._working.clear()

    def _event(self, payload: object) -> None:
        if self._matches():
            self.controls.show_event(cast(BuildEvent, payload))
            self._card_event(payload)
            if isinstance(payload, (LogLine, CommandRun)):
                self.log.append(payload)

    def _card_event(self, event: object) -> None:
        if isinstance(event, BuildStarted):
            self._steps = set(event.steps)
            return
        if not isinstance(event, (NodeStarted, NodeFinished, NodeSkipped, NodeFailed)):
            return
        if event.node_id not in self._steps or event.node_id in self._terminal:
            return
        text = "working"
        if isinstance(event, NodeFinished):
            text = "done"
        elif isinstance(event, NodeSkipped):
            text = "unchanged"
        elif isinstance(event, NodeFailed):
            text = "cancelled" if event.cancelled else "failed"
        if not isinstance(event, NodeStarted):
            self._terminal.add(event.node_id)
            self._working.discard(event.node_id)
        else:
            self._working.add(event.node_id)
        self._show_step(event.node_id, text)

    def _show_step(self, step: str, text: str) -> None:
        prefix, _, component = step.partition(":")
        if prefix == "stage" and component in self.page.cards:
            self.page.cards[component].show_build_state(f"Build: {text}")

    def _clear_cards(self) -> None:
        self._steps.clear()
        self._terminal.clear()
        self._working.clear()
        self._cancelled = False
        for card in self.page.cards.values():
            card.show_build_state("")

    def clear(self) -> None:
        """Rebinding forgets presentation, never cancels/releases a build owner."""
        self._run = None
        self.follow.stop()
        self.log.clear(collapse=True)
        self.controls.clear()
        self._clear_cards()

    def _finished(self, payload: object) -> None:
        if self._matches() and isinstance(payload, BuildSummary):
            for steps, text in (
                (payload.ran, "done"),
                (payload.skipped, "unchanged"),
                (payload.failed, "failed"),
                (payload.cancelled, "cancelled"),
                (payload.not_run, "not run"),
            ):
                for step in steps:
                    self._show_step(step, text)
                    self._terminal.add(step)
            self._end_unfinished("cancelled" if payload.outcome == "cancelled" else "failed")
            self.controls.show_summary(payload)
            self._run = None
            self.sync()
