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
import threading
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from ctstudio.core.components import status
from ctstudio.core.components.status import ComponentStatus, ProjectLike
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project import settings
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.settings import SettingsError
from ctstudio.core.tools.availability import available_tools
from ctstudio.core.validation.report import IssueReport, load_report

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


@dataclass(frozen=True)
class _Snapshot:
    """What one evaluation looks at, taken on the UI thread."""

    root: Path
    manifest: Manifest


class _Relay(QObject):
    """Sends from the status thread; not a child of the service, so it outlives it."""

    done = Signal(int, object)  # generation, StatusResult or exception


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
        self._relay = _Relay()
        self._relay.done.connect(self._done)
        self._project: ProjectLike | None = None
        self._thread: threading.Thread | None = None
        self._generation = 0
        self._pending = False

    @property
    def pending(self) -> bool:
        """A run is waiting for the running one to end."""
        return self._pending

    @property
    def busy(self) -> bool:
        """A result is still to come (delay, run, or a run waiting)."""
        return self._timer.isActive() or self._thread is not None or self._pending

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
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                return False
        self._thread = None
        return True

    def _delay_over(self) -> None:
        if self._thread is not None:
            self._pending = True
        else:
            self._run()

    def _run(self) -> None:
        project = self._project
        if project is None:  # for the type checker: a run is only ever asked after a request
            return
        work = _Work(
            self._generation, self._relay, self._evaluate, self._find_tools, self._load_issues
        )
        snapshot = _Snapshot(project.root, project.manifest)
        self._thread = threading.Thread(
            target=work.run, args=(snapshot, self._settings_path), name=STATUS_THREAD, daemon=True
        )
        self._thread.start()

    def _done(self, generation: int, payload: object) -> None:
        self._thread = None
        if self._pending:
            self._pending = False
            self._run()
        if generation != self._generation:
            return  # cleared while it ran
        if isinstance(payload, StatusResult):
            self.updated.emit(payload)
        else:
            self.failed.emit(payload)


@dataclass(frozen=True)
class _Work:
    """One evaluation, as run on the status thread."""

    generation: int
    relay: _Relay
    evaluate: Evaluate
    find_tools: FindTools
    load_issues: LoadIssues

    def run(self, project: _Snapshot, settings_path: Path | None) -> None:
        payload: StatusResult | Exception
        try:
            try:
                configured, problem = settings.load(settings_path).configured(), None
            except SettingsError as exc:
                configured, problem = {}, exc.user_message
            tools = self.find_tools(configured=configured)
            statuses = dict(self.evaluate(project, tools))
            issues, issues_problem = self._issues(project.root)
            payload = StatusResult(project.root, statuses, problem, issues, issues_problem)
        except Exception as exc:  # any failure must reach the window, not end with the thread
            _LOG.exception("Working out the part statuses failed")
            payload = exc
        self.relay.done.emit(self.generation, payload)

    def _issues(self, root: Path) -> tuple[IssueReport | None, str | None]:
        """The saved findings, or why they could not be read; never hides the statuses."""
        try:
            return self.load_issues(root), None
        except CTStudioError as exc:
            return None, str(exc)
        except Exception as exc:
            _LOG.exception("Reading the saved check results failed")
            return None, f"The saved check results could not be read: {exc or type(exc).__name__}"
