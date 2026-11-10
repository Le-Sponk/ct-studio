"""Joined ownership of blocking editor, folder and file-assignment work (ARCHITECTURE §10).

``LaunchController.start`` runs one Blender launch (``component_id`` None) or one component
folder reveal (P5-T03i), and ``assign`` one ``assign_file`` call (P5-T04b), on a named thread
(``ctstudio-launch``); only one of them runs at a time. The result, including any typed error,
crash or worker interrupt, comes back once as ``completed`` on the UI thread, with the project,
root and manifest captured when it started. ``busy`` stays True until that delivery has joined
the worker; ``shutdown`` waits and, when it times out, keeps the owner busy so the caller keeps
the project open. A receipt only means the request was dispatched, not that anything displayed.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, Signal

from ctstudio.core.components.assign import Assigned, assign_file
from ctstudio.core.errors import CTStudioError, ProjectError
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors
from ctstudio.core.tools import folders as corefolders
from ctstudio.gui.blender_launch import BlenderLaunchService
from ctstudio.gui.folder_reveal import FolderRevealService

_LOG = logging.getLogger(__name__)
THREAD_NAME = "ctstudio-launch"
Receipt = editors.Launched | corefolders.OpenedFolder | Assigned


class Assign(Protocol):
    def __call__(
        self, project: Project, part: str, source: Path, *, reference: bool = False
    ) -> Assigned: ...


@dataclass(frozen=True)
class LaunchResult:
    """One finished request; exactly one of ``receipt`` and ``error`` is set."""

    project: Project
    root: Path
    manifest: Manifest
    component_id: str | None
    receipt: Receipt | None = None
    error: BaseException | None = None
    source: Path | None = None  # set for a file assignment (component_id is then its part)
    reference: bool = False


class _Relay(QObject):
    """Sends from the worker; not a child of the controller, so it outlives it."""

    done = Signal(int, object, object)  # generation, receipt or None, exception or None


@dataclass(frozen=True)
class _Context:
    project: Project
    root: Path
    manifest: Manifest
    component_id: str | None
    source: Path | None = None
    reference: bool = False

    def result(self, receipt: object = None, error: object = None) -> LaunchResult:
        return LaunchResult(
            self.project,
            self.root,
            self.manifest,
            self.component_id,
            receipt=receipt if isinstance(receipt, Receipt) else None,
            error=error if isinstance(error, BaseException) else None,
            source=self.source,
            reference=self.reference,
        )


class LaunchController(QObject):
    completed = Signal(object)  # LaunchResult
    busy_changed = Signal(bool)

    def __init__(
        self,
        *,
        blender: BlenderLaunchService | None = None,
        folders: FolderRevealService | None = None,
        assign: Assign = assign_file,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._blender = blender if blender is not None else BlenderLaunchService()
        self._folders = folders if folders is not None else FolderRevealService()
        self._assign = assign
        self._relay = _Relay()
        self._relay.done.connect(self._on_done)
        self._thread: threading.Thread | None = None
        self._context: _Context | None = None
        self._generation = 0
        self._busy = False

    @property
    def busy(self) -> bool:
        """True from ``start`` until its result was delivered (or a shutdown succeeded)."""
        return self._busy

    def start(self, project: Project, component_id: str | None = None) -> bool:
        """Start Blender (None) or reveal ``component_id``; False when nothing started."""
        return self._begin(_Context(project, project.root, project.manifest, component_id))

    def assign(self, project: Project, part: str, source: Path, *, reference: bool) -> bool:
        """Run ``assign_file``; the result's receipt is the ``Assigned`` (never published here)."""
        context = _Context(project, project.root, project.manifest, part, source, reference)
        return self._begin(context)

    def _begin(self, context: _Context) -> bool:
        if self._busy:
            return False
        self._generation += 1
        work = _Work(self._generation, self._relay, self._blender, self._folders, self._assign)
        thread = threading.Thread(target=work.run, args=(context,), name=THREAD_NAME, daemon=True)
        self._thread, self._context = thread, context
        self._set_busy(True)
        try:
            thread.start()
        except RuntimeError as exc:  # the system refused another thread
            self._thread, self._context = None, None
            self._set_busy(False)
            error = ProjectError(
                "Could not start the request in the background.",
                hint="Close other programs or restart CT Studio, then try again.",
                details=str(exc),
            )
            error.__cause__ = exc
            self.completed.emit(context.result(error=error))
            return False
        return True

    def shutdown(self, timeout: float) -> bool:
        """Wait up to ``timeout`` s; True when no worker is left (its result is then dropped)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                return False
        self._thread, self._context = None, None  # a queued delivery now finds no context
        self._set_busy(False)
        return True

    def _set_busy(self, busy: bool) -> None:
        if busy != self._busy:
            self._busy = busy
            self.busy_changed.emit(busy)

    def _on_done(self, generation: int, receipt: object, error: object) -> None:
        context = self._context
        if generation != self._generation or context is None:
            return
        thread = self._thread
        if thread is not None:
            thread.join()  # the worker's last statement was this signal's emit
        self._thread, self._context = None, None
        self._set_busy(False)
        self.completed.emit(context.result(receipt, error))


@dataclass(frozen=True)
class _Work:
    """One request, as run on the launch thread."""

    generation: int
    relay: _Relay
    blender: BlenderLaunchService
    folders: FolderRevealService
    assign: Assign

    def run(self, context: _Context) -> None:
        receipt: Receipt | None = None
        error: BaseException | None = None
        project, component_id = context.project, context.component_id
        try:
            if context.source is not None and component_id is not None:
                receipt = self.assign(
                    project, component_id, context.source, reference=context.reference
                )
            elif component_id is None:
                receipt = self.blender.launch(project)
            else:
                receipt = self.folders.reveal(project, component_id)
        except CTStudioError as exc:
            error = exc
        except BaseException as exc:  # crashes and interrupts must reach the window
            _LOG.exception("The launch request crashed")
            error = exc
        self.relay.done.emit(self.generation, receipt, error)
