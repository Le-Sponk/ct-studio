"""Each part's status, worked out off the UI thread a burst of requests at a time (P5-T01b).

``StatusService.request(project)`` (re)starts a short delay; when it ends, one evaluation
runs on its own named thread (``ctstudio-status``): the user's settings, which tools are
there (discovery only) and ``components.status.evaluate``. Asking again while one runs gives
exactly one more run, of the newest project, after it. The same run reads the last check's
issue report (``.ctstudio/issues.json``, P5-T05b), so it is fresh on open, on Refresh and
after every build. ``updated`` carries a ``StatusResult``
and ``failed`` the exception; both arrive on the UI thread. ``clear`` drops what was asked
and what is running (a closed project); ``shutdown`` also waits for the thread.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, QTimer, Signal

from ctstudio.core.components import status
from ctstudio.core.components.status import ComponentStatus, ProjectLike
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project import settings
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.settings import SettingsError
from ctstudio.core.tools.availability import available_tools
from ctstudio.core.validation.report import IssueReport, load_report
from ctstudio.gui.joined_worker import JoinedWorker

_LOG = logging.getLogger(__name__)
STATUS_THREAD = "ctstudio-status"
DELAY_MS = 300  # file changes come in bursts (a save writes several files)

Evaluate = Callable[[ProjectLike, Collection[str]], Mapping[str, ComponentStatus]]
FindTools = Callable[..., Collection[str]]
LoadIssues = Callable[[Path], IssueReport | None]


@dataclass(frozen=True)
class StatusResult:
    root: Path
    statuses: Mapping[str, ComponentStatus]
    settings_problem: str | None = None  # the settings file could not be used
    issues: IssueReport | None = None  # the last check's findings; None: none saved yet
    issues_problem: str | None = None  # the saved findings could not be read
    settings_details: str | None = None  # why the settings file failed: Copy details (P5-T10f)


@dataclass(frozen=True)
class _Snapshot:
    """What one evaluation looks at, taken on the UI thread."""

    root: Path
    manifest: Manifest


class StatusService(QObject):
    updated = Signal(object)  # StatusResult
    failed = Signal(object)  # the exception

    def __init__(
        self,
        *,
        evaluate: Evaluate = status.evaluate,
        find_tools: FindTools = available_tools,
        load_issues: LoadIssues = load_report,
        settings_path: Path | None = None,
        delay_ms: int = DELAY_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._evaluate, self._find_tools, self._load_issues = evaluate, find_tools, load_issues
        self._settings_path = settings_path
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._delay_over)
        # No parent: the relay outlives the service, for a result sent during shutdown.
        self._worker = JoinedWorker(
            STATUS_THREAD,
            self._delivered,
            logger=_LOG,
            failure="Working out the part statuses failed",
        )
        self._project: ProjectLike | None = None
        self._generation = 0
        self._pending = False

    @property
    def pending(self) -> bool:
        """A run is waiting for the running one to end."""
        return self._pending

    @property
    def busy(self) -> bool:
        """A result is still to come (delay, run, or a run waiting)."""
        return self._timer.isActive() or self._worker.busy or self._pending

    def request(self, project: ProjectLike) -> None:
        """Work the statuses of ``project`` out soon; a burst of requests gives one run."""
        self._project = project
        self._timer.start()

    def clear(self) -> None:
        """Forget what was asked; a running evaluation's result is dropped."""
        self._timer.stop()
        self._pending = False
        self._generation += 1

    def shutdown(self, timeout: float) -> bool:
        """``clear``, then wait up to ``timeout`` s; True when no status thread is left."""
        self.clear()
        return self._worker.shutdown(timeout)

    def _delay_over(self) -> None:
        if self._worker.busy:
            self._pending = True
        else:
            self._run()

    def _run(self) -> None:
        project = self._project
        if project is None:  # for the type checker: a run is only ever asked after a request
            return
        work = _Work(self._generation, self._evaluate, self._find_tools, self._load_issues)
        snapshot, settings_path = _Snapshot(project.root, project.manifest), self._settings_path
        self._worker.start(lambda: work.run(snapshot, settings_path))

    def _delivered(self, payload: object) -> None:
        if isinstance(payload, tuple):  # (generation, result) from the thread
            generation, result = cast("tuple[int, object]", payload)
            self._done(generation, result)
        else:  # the thread did not start
            self._done(self._generation, payload)

    def _done(self, generation: int, payload: object) -> None:
        # This run's news first (busy stays on while a re-run is pending), then the re-run:
        # its own failure to start must be the last word, not hidden by an older result.
        if generation == self._generation:  # else cleared while it ran
            if isinstance(payload, StatusResult):
                self.updated.emit(payload)
            else:
                self.failed.emit(payload)
        if self._pending:
            self._pending = False
            self._run()


@dataclass(frozen=True)
class _Work:
    """One evaluation, as run on the status thread."""

    generation: int
    evaluate: Evaluate
    find_tools: FindTools
    load_issues: LoadIssues

    def run(self, project: _Snapshot, settings_path: Path | None) -> tuple[int, object]:
        payload: StatusResult | Exception
        try:
            try:
                configured, problem = settings.load(settings_path).configured(), None
                problem_details = None
            except SettingsError as exc:
                configured, problem, problem_details = {}, exc.user_message, exc.details
            tools = self.find_tools(configured=configured)
            statuses = dict(self.evaluate(project, tools))
            issues, issues_problem = self._issues(project.root)
            payload = StatusResult(
                project.root, statuses, problem, issues, issues_problem, problem_details
            )
        except Exception as exc:  # any failure must reach the window, not end with the thread
            _LOG.exception("Working out the part statuses failed")
            payload = exc
        return self.generation, payload

    def _issues(self, root: Path) -> tuple[IssueReport | None, str | None]:
        """The saved findings, or why they could not be read; never hides the statuses."""
        try:
            return self.load_issues(root), None
        except CTStudioError as exc:
            return None, str(exc)
        except Exception as exc:
            _LOG.exception("Reading the saved check results failed")
            return None, f"The saved check results could not be read: {exc or type(exc).__name__}"
