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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, Signal

from ctstudio.core.components.assign import Assigned, assign_file
from ctstudio.core.components.edited import discard_edit, lock_as_manual
from ctstudio.core.errors import CTStudioError, ProjectError
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors
from ctstudio.core.tools import folders as corefolders
from ctstudio.gui.blender_launch import BlenderLaunchService
from ctstudio.gui.folder_reveal import FolderRevealService
from ctstudio.gui.project_details import DetailsSnapshot, ProjectDetailsService

_LOG = logging.getLogger(__name__)
THREAD_NAME = "ctstudio-launch"
Receipt = editors.Launched | corefolders.OpenedFolder | Assigned | Path


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
    edit_action: str | None = None  # lock/discard; None for assignment or editor/folder dispatch
    saved: DetailsSnapshot | None = None  # post-attempt disk state, not the captured input
    recovery_error: BaseException | None = None  # separate from the original action/start error
    recovery_root: Path | None = None  # independently resolved on the recovery worker


@dataclass(frozen=True)
class _Recovered:
    receipt: Receipt | None
    snapshot: DetailsSnapshot | None = None
    error: BaseException | None = None
    root: Path | None = None


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
    edit_action: str | None = None  # lock/discard; None for assignment or editor/folder dispatch

    def result(self, receipt: object = None, error: object = None) -> LaunchResult:
        recovered = receipt if isinstance(receipt, _Recovered) else None
        if recovered is not None:
            receipt = recovered.receipt
        return LaunchResult(
            self.project,
            self.root,
            self.manifest,
            self.component_id,
            receipt=receipt if isinstance(receipt, Receipt) and error is None else None,
            error=error if isinstance(error, BaseException) else None,
            source=self.source,
            reference=self.reference,
            edit_action=self.edit_action,
            saved=recovered.snapshot if recovered is not None else None,
            recovery_error=recovered.error if recovered is not None else None,
            recovery_root=recovered.root if recovered is not None else None,
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
        lock: Callable[[Project, str], Assigned] = lock_as_manual,
        discard: Callable[[Project, str], Path] = discard_edit,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._blender = blender if blender is not None else BlenderLaunchService()
        self._folders = folders if folders is not None else FolderRevealService()
        self._assign = assign
        self._lock, self._discard = lock, discard
        self._relay = _Relay()
        self._relay.done.connect(self._on_done)
        self._thread: threading.Thread | None = None
        self._context: _Context | None = None
        self._generation = 0
        self._busy = False
        self._start_error: BaseException | None = None

    @property
    def busy(self) -> bool:
        """True from ``start`` until its result was delivered (or a shutdown succeeded)."""
        return self._busy

    def start(self, project: Project, component_id: str | None = None) -> bool:
        """Start Blender (None) or reveal ``component_id``.

        False is not rollback: native startup acknowledgement can fail after dispatch.
        Respect busy ownership and joined completion even when this returns False.
        """
        return self._begin(_Context(project, project.root, project.manifest, component_id))

    def assign(self, project: Project, part: str, source: Path, *, reference: bool) -> bool:
        """Run ``assign_file``; the result's receipt is the ``Assigned`` (never published here)."""
        context = _Context(project, project.root, project.manifest, part, source, reference)
        return self._begin(context)

    def reconcile(self, project: Project, part: str, action: str) -> bool:
        """Run Lock or Discard; the receiver alone publishes a saved manifest after joining."""
        if action not in ("lock", "discard"):
            raise ProjectError(
                f"Unknown outside-edit action '{action}'.",
                hint="Choose Lock as manual or Discard on the part's card.",
            )
        return self._begin(
            _Context(project, project.root, project.manifest, part, edit_action=action)
        )

    def _begin(self, context: _Context) -> bool:
        if self._busy:
            return False
        self._generation += 1
        work = _Work(
            self._generation,
            self._relay,
            self._blender,
            self._folders,
            self._assign,
            self._lock,
            self._discard,
        )
        thread = threading.Thread(target=work.run, args=(context,), name=THREAD_NAME, daemon=True)
        self._thread, self._context = thread, context
        self._set_busy(True)
        try:
            thread.start()
        except BaseException as exc:  # start can be interrupted after native creation
            if thread in threading.enumerate() or thread.ident is not None:
                # Enumeration must precede ident: pending bootstrap has no ident yet.
                self._start_error = exc
            else:
                self._start_failed(context, exc)
            return False
        return True

    def _start_failed(self, context: _Context, exc: BaseException) -> None:
        self._thread, self._context = None, None
        generation = self._generation
        self._set_busy(False)
        error = exc
        if isinstance(exc, RuntimeError):
            error = ProjectError(
                "Could not start the request in the background.",
                hint="Close other programs or restart CT Studio, then try again.",
                details=str(exc),
            )
            error.__cause__ = exc
        if generation == self._generation:
            self.completed.emit(context.result(error=error))

    def shutdown(self, timeout: float) -> bool:
        """Wait up to ``timeout`` s; True when no worker is left (its result is then dropped)."""
        thread = self._thread
        if thread is not None:
            # A busy callback can run before start(); native bootstrap can also be
            # in threading's registry before its acknowledgement makes join legal.
            if not thread.is_alive() and thread in threading.enumerate():
                return False
            if thread.ident is None:
                return False
            thread.join(timeout)
            if thread.is_alive():
                return False
        self._thread, self._context = None, None  # a queued delivery now finds no context
        self._start_error = None
        self._generation += 1
        self._set_busy(False)
        return self._thread is None  # an idle callback may have started another request

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
        if self._start_error is not None:
            error = self._start_error
        self._start_error = None
        self._thread, self._context = None, None
        self._set_busy(False)
        if generation == self._generation:
            self.completed.emit(context.result(receipt, error))


@dataclass(frozen=True)
class _Work:
    """One request, as run on the launch thread."""

    generation: int
    relay: _Relay
    blender: BlenderLaunchService
    folders: FolderRevealService
    assign: Assign
    lock: Callable[[Project, str], Assigned]
    discard: Callable[[Project, str], Path]

    def run(self, context: _Context) -> None:
        receipt: Receipt | None = None
        error: BaseException | None = None
        project, component_id = context.project, context.component_id
        try:
            if context.edit_action is not None and component_id is not None:
                action = self.lock if context.edit_action == "lock" else self.discard
                receipt = action(project, component_id)
            elif context.source is not None and component_id is not None:
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
        outgoing = self._recover(project, receipt) if context.edit_action is not None else receipt
        self.relay.done.emit(self.generation, outgoing, error)

    @staticmethod
    def _recover(project: Project, receipt: Receipt | None) -> _Recovered:
        try:
            root = project.root.resolve()
            return _Recovered(receipt, ProjectDetailsService().load(project), root=root)
        except BaseException as exc:  # a separate, explicit outcome; never replace the action error
            return _Recovered(receipt, error=exc)
