"""Settings → Build, "This computer" (P5-T08c): how many build steps may run at once.

A machine setting in ``settings.json`` (``build_jobs``), the same for every project and shown
with or without one: Automatic (the runner's own ``min(4, CPUs)``) or a number. A pick is
saved at once on the section's worker through a fresh read; nothing is written when the file
already says so. A damaged or newer file is shown and never overwritten: the choice is hidden
until a reread finds the file usable (every save also re-reads and refuses it). GUI builds and
``ctstudio build`` read the setting fresh, so the next build uses it.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from PySide6.QtCore import QObject, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QComboBox, QLabel, QProgressBar, QVBoxLayout, QWidget

from ctstudio.core.build.runner import default_jobs
from ctstudio.core.project.settings import MAX_BUILD_JOBS, SettingsError
from ctstudio.gui.build_settings import BuildJobsService
from ctstudio.gui.views.wrap_text import breakable

_LOG = logging.getLogger(__name__)
INTRO = "The same for every project on this computer; a choice is saved at once."
OFFERED = min(MAX_BUILD_JOBS, max(8, os.cpu_count() or 1))  # more when the file says so


@dataclass(frozen=True)
class _Result:
    jobs: int | None
    saved: bool


class _Relay(QObject):
    done = Signal(object)


class BuildJobsSection(QWidget):
    # The choice had the keyboard but is hidden now (the file became unusable): the owner
    # gives it to something useful, or it stays on Close, which Enter or Space would press.
    keyboard_lost = Signal()

    def __init__(self, service: BuildJobsService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("buildJobsSection")
        self.service = service
        self.pool = QThreadPool(self)  # first child: deleted (and waited for) first
        self._relay = _Relay(self)
        self._relay.done.connect(self._finished)
        self._running = False
        self._jobs: int | None = None
        self._read = False  # a usable file has been read
        self._locked = False  # the file cannot be used: the choice is hidden
        self._focus = False  # the choice had the keyboard when a save began
        self._saving = False  # the running work is a save, not a read
        self._build()
        self._render()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        self.intro = QLabel(INTRO, self)
        self.intro.setWordWrap(True)
        layout.addWidget(self.intro)
        self.label = QLabel("Build steps at &once", self)  # above its choice: narrow
        layout.addWidget(self.label)
        self.combo = QComboBox(self)
        self.combo.setObjectName("buildJobs")
        self.combo.addItem(f"Automatic ({default_jobs()} on this computer)", None)
        self._offer(OFFERED)
        self.combo.setToolTip("Used by the next build, in CT Studio and by ctstudio build.")
        self.combo.activated.connect(self._picked)
        self.label.setBuddy(self.combo)
        layout.addWidget(self.combo)
        self.banner = self._text("buildJobsProblem", layout)
        self.note = self._text("buildJobsNote", layout)
        self.busy_bar = QProgressBar(self)
        self.busy_bar.setObjectName("buildJobsBusy")
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setMaximumHeight(6)
        layout.addWidget(self.busy_bar)
        layout.addStretch()

    def _text(self, name: str, layout: QVBoxLayout) -> QLabel:
        label = QLabel(self)
        label.setObjectName(name)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        return label

    def _offer(self, highest: int) -> None:
        """Offer every number up to ``highest`` (a saved number may be above the usual list)."""
        for jobs in range(self.combo.count(), highest + 1):
            self.combo.addItem(str(jobs), jobs)

    @property
    def busy(self) -> bool:
        return self._running

    def reload(self) -> None:
        """Read the setting again (not while a read or save runs)."""
        if not self._running:
            service = self.service
            self._start(lambda: _Result(service.load(), saved=False))

    def _picked(self, index: int) -> None:
        if self._running or not self._read:
            return  # past Qt's own disabling: nothing is saved now
        jobs = cast("int | None", self.combo.itemData(index))
        service = self.service
        self._focus = self.combo.hasFocus()
        self._start(lambda: _Result(service.save(jobs), saved=True), saving=True)

    def _start(self, work: Callable[[], _Result], *, saving: bool = False) -> None:
        relay = self._relay

        def job() -> None:
            try:
                payload: object = work()
            except Exception as exc:  # any failure must reach the section, not die here
                _LOG.exception("Reading or saving the build steps setting failed")
                payload = exc
            relay.done.emit(payload)

        self._running, self._saving = True, saving
        self.note.clear()
        self._render()
        self.pool.start(job)

    def _finished(self, payload: object) -> None:
        self._running = False
        if isinstance(payload, _Result):
            self._jobs, self._read, self._locked = payload.jobs, True, False
            self._problem("")
            if payload.saved:
                self.note.setText(_saved(payload.jobs))
        elif isinstance(payload, SettingsError):
            self._locked = True
            self._problem(str(payload))
        elif isinstance(payload, Exception):
            reason = str(payload) or type(payload).__name__
            action = "save" if self._saving else "read"
            self._problem(f"Could not {action} the build steps setting. {reason}")
        self._render()
        self._return_keyboard()

    def _return_keyboard(self) -> None:
        """Give the keyboard back after a pick: turning the choice off moved it on."""
        if self._focus and self.combo.isEnabled() and self.combo.isVisible():
            self.combo.setFocus()
        elif self._focus and self.isVisible():  # the choice is hidden: file unusable
            self.keyboard_lost.emit()
        self._focus = False

    def _problem(self, text: str) -> None:
        self.banner.setText(breakable(text))
        self.banner.setHidden(not text)

    def _render(self) -> None:
        if self._jobs is not None:
            self._offer(self._jobs)
        self.combo.setCurrentIndex(self.combo.findData(self._jobs))
        self.combo.setEnabled(not self._running and self._read)  # hidden when locked
        # Locked: only the reason is shown; it may be long, and the screen only 600 px tall.
        self.intro.setHidden(self._locked)
        self.label.setHidden(self._locked)
        self.combo.setHidden(self._locked)
        self.busy_bar.setVisible(self._running)


def _saved(jobs: int | None) -> str:
    if jobs is None:
        return "Saved. The next build chooses how many steps run at once."
    return f"Saved. The next build runs up to {jobs} steps at once."
