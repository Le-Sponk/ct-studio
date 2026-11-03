"""Run a project's build off the UI thread and report it as Qt signals (P5-T01a, §10).

``BuildController.start`` plans and runs one build on its own named thread
(``ctstudio-build``): reading the user's settings, finding the tools and probing their
versions happen there too, so the UI thread never waits on the disk or a tool. Every core
event comes back as ``build_event`` on the UI thread, in order; then ``finished`` (the summary) or
``failed`` (the exception: a typed error when the build could not start, or a crash). A second
build while one runs, and a read-only project, are refused. ``cancel`` asks the running
build to stop; ``shutdown`` cancels and waits, so no build thread outlives the window.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ctstudio.core.build.events import BuildEvent, BuildSummary
from ctstudio.core.build.project_build import (
    BuildPlan,
    build_project,
    check_buildable,
    plan_build,
)
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project import settings
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.project.settings import SettingsError, UserSettings
from ctstudio.core.tools.process import CancelToken

_LOG = logging.getLogger(__name__)
THREAD_NAME = "ctstudio-build"

Plan = Callable[..., BuildPlan]
Build = Callable[..., BuildSummary]


@dataclass(frozen=True)
class _Options:
    profile: str
    only: str | None
    force: bool


class _Relay(QObject):
    """Sends from the build thread; not a child of the controller, so it outlives it."""

    build_event = Signal(int, object)
    notice = Signal(int, str)
    done = Signal(int, object, object)  # generation, summary or None, exception or None


class _Cancels:
    """The running build's cancel token, reachable when the controller itself is gone."""

    def __init__(self) -> None:
        self.current = CancelToken()

    def cancel(self) -> None:
        self.current.cancel()


class BuildController(QObject):
    build_event = Signal(object)  # each core BuildEvent, in order
    finished = Signal(object)  # the BuildSummary: the build ran (whatever its outcome)
    failed = Signal(object)  # the exception: it could not start, or it crashed
    notice = Signal(str)  # something the user should know that did not stop the build
    running_changed = Signal(bool)

    def __init__(
        self,
        *,
        plan: Plan = plan_build,
        build: Build = build_project,
        settings_path: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._plan, self._build, self._settings_path = plan, build, settings_path
        self._relay = _Relay()
        self._relay.build_event.connect(self._on_event)
        self._relay.notice.connect(self._on_notice)
        self._relay.done.connect(self._on_done)
        self._cancels = _Cancels()
        self.destroyed.connect(self._cancels.cancel)  # a window closed mid-build stops it
        self._thread: threading.Thread | None = None
        self._generation = 0
        self._running = False

    @property
    def running(self) -> bool:
        """True from ``start`` until its ``finished`` or ``failed`` was emitted."""
        return self._running

    def start(
        self,
        project: Project,
        *,
        release: bool = False,
        force: bool = False,
        only: str | None = None,
    ) -> bool:
        """Start a build of ``project``; False (and nothing started) when it cannot."""
        if self._running:
            return False
        try:
            check_buildable(project)
        except CTStudioError as exc:
            self.failed.emit(exc)
            return False
        self._generation += 1
        self._cancels.current = CancelToken()
        options = _Options("release" if release else "test", only, force)
        work = _Work(self._generation, self._relay, self._plan, self._build, self._settings_path)
        self._thread = threading.Thread(
            target=work.run,
            args=(project.root, project.manifest, options, self._cancels.current),
            name=THREAD_NAME,
            daemon=True,
        )
        self._set_running(True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        """Ask the running build to stop; steps already running finish first."""
        self._cancels.cancel()

    def shutdown(self, timeout: float) -> bool:
        """Cancel, then wait up to ``timeout`` s; True when no build thread is left."""
        self.cancel()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                return False
        self._thread = None
        self._generation += 1  # what the ended build still has queued is not shown
        self._set_running(False)
        return True

    def _set_running(self, running: bool) -> None:
        if running != self._running:
            self._running = running
            self.running_changed.emit(running)

    def _on_event(self, generation: int, event: object) -> None:
        if generation == self._generation:
            self.build_event.emit(event)

    def _on_notice(self, generation: int, text: str) -> None:
        if generation == self._generation:
            self.notice.emit(text)

    def _on_done(self, generation: int, summary: object, error: object) -> None:
        if generation != self._generation:
            return
        self._thread = None
        self._set_running(False)
        if error is not None:
            self.failed.emit(error)
        else:
            self.finished.emit(summary)


@dataclass(frozen=True)
class _Work:
    """One build, as run on the build thread."""

    generation: int
    relay: _Relay
    plan: Plan
    build: Build
    settings_path: Path | None

    def run(self, root: Path, manifest: Manifest, options: _Options, cancel: CancelToken) -> None:
        summary: BuildSummary | None = None
        error: Exception | None = None
        try:
            user = self._user_settings()
            planned = self.plan(
                root,
                manifest,
                options.profile,
                only=options.only,
                configured=user.configured(),
                library=user.auto_add_library(),
            )
            summary = self.build(planned, self._send, cancel=cancel, force=options.force)
        except CTStudioError as exc:
            error = exc
        except Exception as exc:  # any crash must reach the window, not end with the thread
            _LOG.exception("The build crashed")
            error = exc
        self.relay.done.emit(self.generation, summary, error)

    def _send(self, event: BuildEvent) -> None:
        self.relay.build_event.emit(self.generation, event)

    def _user_settings(self) -> UserSettings:
        """CT Studio's settings; a damaged file is reported, then left out."""
        try:
            return settings.load(self.settings_path)
        except SettingsError as exc:
            text = f"{exc.user_message} Paths set in CT Studio are ignored for this build."
            self.relay.notice.emit(self.generation, text)
            return UserSettings()
