"""Settings → Build (P5-T08b): the open project's build settings.

Test and release compression, the ``_d`` copy and auto-add live in the project file, so each
project has its own. The page reads them on a joined worker each time it is refreshed and
saves only on Save (one backup per save); Undo changes goes back to what is saved. While it
reads or saves, every control is off and the page owns ``services.editing``, so the project
cannot be closed or switched under it. Save is off while a build or a launch runs (the
project then belongs to that work); the change is kept for after. A read-only project is
shown but not editable; with no project open the page says where the settings live. When
the file no longer matches the project as opened (edited outside CT Studio), the page says so
and stays read-only: the next build uses the opened project until it is reopened. Why Save is
off is shown apart from the last result or error (``blocked`` vs ``problem``). A save
publishes the new manifest to the open project on the GUI thread, after joining, and emits
``saved``; the next build uses it. All of that is the "This project" tab; the "This computer"
tab (``BuildJobsSection``, P5-T08c) shows and saves how many build steps may run at once,
with or without a project.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.project import manifest_io
from ctstudio.core.project.manifest import COMPRESSIONS
from ctstudio.core.project.project import Project
from ctstudio.gui.build_settings import BuildChoices, BuildJobsService, BuildSettingsService
from ctstudio.gui.project_details import DetailsSnapshot
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.build_jobs import BuildJobsSection
from ctstudio.gui.views.plain import busy_bar, plain_label
from ctstudio.gui.views.wrap_text import breakable

_LOG = logging.getLogger(__name__)
WORKER_NAME = "ctstudio-build-settings"
COMPRESSION_TEXT = {
    "best": "Best (smallest, slowest)",
    "fast": "Fast (larger, quicker)",
    "none": "None (largest, quickest)",
}
OUTSIDE = (
    "The project file changed outside CT Studio after the project was opened, so the next "
    "build still uses the settings it was opened with. Reopen the project to change them."
)
NO_PROJECT = (
    "Open a project to change its build settings. They are saved in the project's own "
    f"file ({manifest_io.FILE_NAME}), so each project has its own."
)


class _Relay(QObject):
    done = Signal(object)


class BuildPage(QWidget):
    saved = Signal()  # a save was published to the open project
    save_finished = Signal(bool)  # a save ended: True when it was saved and published

    def __init__(
        self,
        services: AppServices,
        *,
        service: BuildSettingsService | None = None,
        jobs_service: BuildJobsService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("buildPage")
        self.services = services
        self.service = service if service is not None else BuildSettingsService()
        self._project: Project | None = None  # whose settings are shown
        self._snapshot: DetailsSnapshot | None = None
        self._outside = False  # the file no longer matches the project as opened
        self._busy = False
        self._saving = False
        self._worker: threading.Thread | None = None
        self._relay = _Relay(self)
        self._relay.done.connect(self._completed)
        self._build(jobs_service or BuildJobsService())
        services.build.running_changed.connect(self._render)
        services.launch.busy_changed.connect(self._render)
        self.reload()

    def _build(self, jobs_service: BuildJobsService) -> None:
        # Two tabs: both parts together are taller than a 600 px screen at large fonts.
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("buildTabs")
        QVBoxLayout(self).addWidget(self.tabs)
        self.project_tab = QWidget(self.tabs)
        layout = QVBoxLayout(self.project_tab)
        self.note = plain_label(self, "buildNote")
        layout.addWidget(self.note)
        self.fields = QWidget(self)
        self.fields.setObjectName("buildFields")
        form = QFormLayout(self.fields)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)  # labels above: narrow
        self.test_compression = self._compression("buildTestCompression")
        form.addRow("&Test builds", self.test_compression)
        self.release_compression = self._compression("buildReleaseCompression")
        form.addRow("&Release builds", self.release_compression)
        self.d_copy = self._check("buildDCopy", "Also make the track's _&d copy")
        self.d_copy.setToolTip("The game loads <slot>_d.szs in some modes; it is the same track.")
        form.addRow(self.d_copy)
        self.auto_add = self._check("buildAutoAdd", "&Auto-add missing object files")
        self.auto_add.setToolTip(
            "Uses this computer's auto-add library when one is set up (auto_add_library in "
            "CT Studio's settings file); without one, nothing is added."
        )
        form.addRow(self.auto_add)
        layout.addWidget(self.fields)
        self._footer(layout)
        self.tabs.addTab(self.project_tab, "This &project")
        self.jobs = BuildJobsSection(jobs_service, self.tabs)
        self.jobs.keyboard_lost.connect(self.tabs.tabBar().setFocus)
        self.tabs.addTab(self.jobs, "This co&mputer")

    def _compression(self, name: str) -> QComboBox:
        combo = QComboBox(self.fields)
        combo.setObjectName(name)
        for value in COMPRESSIONS:
            combo.addItem(COMPRESSION_TEXT[value], value)
        combo.currentIndexChanged.connect(self._edited)
        return combo

    def _check(self, name: str, text: str) -> QCheckBox:
        box = QCheckBox(text, self.fields)
        box.setObjectName(name)
        box.toggled.connect(self._edited)
        return box

    def _footer(self, layout: QVBoxLayout) -> None:
        self.blocked = self._label("buildBlocked", layout)  # why Save is off, from outside
        self.problem = self._label("buildProblem", layout)  # the last result or error
        self.progress = busy_bar(self, "buildProgress")
        layout.addWidget(self.progress)
        self.action_row = QWidget(self)  # hidden with the choices when no project is open
        row = QHBoxLayout(self.action_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch()
        self.undo_button = QPushButton("&Undo changes", self.action_row)
        self.undo_button.setObjectName("buildUndo")
        self.undo_button.clicked.connect(self.undo)
        self.save_button = QPushButton("&Save", self.action_row)
        self.save_button.setObjectName("buildSave")
        self.save_button.clicked.connect(self.save)
        row.addWidget(self.undo_button)
        row.addWidget(self.save_button)
        layout.addWidget(self.action_row)
        layout.addStretch()

    def _label(self, name: str, layout: QVBoxLayout) -> QLabel:
        label = plain_label(self, name)
        layout.addWidget(label)
        return label

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def can_save(self) -> bool:
        """Save would start now: something changed and nothing outside the page stops it."""
        return self._may_save() and self._snapshot is not None and self.changed

    @property
    def changed(self) -> bool:
        """The shown choices differ from what is saved."""
        snapshot = self._snapshot
        return snapshot is not None and self._choices() != BuildChoices.of(snapshot.manifest.build)

    def _choices(self) -> BuildChoices:
        return BuildChoices(
            self.test_compression.currentData(),
            self.release_compression.currentData(),
            self.d_copy.isChecked(),
            self.auto_add.isChecked(),
        )

    def reload(self) -> None:
        """Read the open project's saved choices and this computer's setting again (each not
        while it reads or saves)."""
        self.jobs.reload()
        if self._busy:
            return
        project = self.services.project
        self._project, self._snapshot, self._outside = project, None, False
        self.problem.clear()
        if project is None or not self._start(lambda: self.service.load(project)):
            self._render()

    def save(self) -> bool:
        """Start saving the shown choices; False when nothing was started."""
        project, snapshot = self._project, self._snapshot
        if not self._may_save() or project is None or snapshot is None or not self.changed:
            return False
        choices = self._choices()
        return self._start(lambda: self.service.save(project, snapshot, choices), saving=True)

    def undo(self) -> None:
        if not self._busy and self._snapshot is not None:
            self._fill(self._snapshot)
            self._render()

    def _may_save(self) -> bool:
        return (
            not self._busy
            and not self._outside
            and self._project is not None
            and self.services.project is self._project
            and not self._project.read_only
            and not self.services.build.running
            and not self.services.launch.busy
        )

    def _start(self, work: Callable[[], DetailsSnapshot], *, saving: bool = False) -> bool:
        """Run ``work`` on the page's worker, owning the project; False when another editor
        owns it."""
        if self.services.editing:
            self.problem.setText("Another window is editing this project. Close it first.")
            return False
        self.services.editing = True
        self._busy, self._saving = True, saving
        self.problem.setText("Saving the build settings…" if saving else "")
        self._render()
        relay = self._relay

        def job() -> None:
            try:
                result: object = work()
            except Exception as exc:  # failures must reach the page, not vanish in a thread
                _LOG.exception("Reading or saving the build settings failed")
                result = exc
            relay.done.emit(result)

        self._worker = threading.Thread(target=job, name=WORKER_NAME, daemon=True)
        try:
            self._worker.start()
        except Exception as exc:
            self._completed(exc)
        return True

    def _completed(self, payload: object) -> None:
        if self._worker is not None and self._worker.ident is not None:
            self._worker.join()
        self._worker = None
        self._busy = False
        self.services.editing = False
        # The project cannot change meanwhile: the page owned ``services.editing``.
        project = self._project
        ok = isinstance(payload, DetailsSnapshot) and project is not None
        if isinstance(payload, DetailsSnapshot) and project is not None:
            self._snapshot = payload
            if self._saving:
                project.manifest = payload.manifest
                self.problem.setText("Saved. The next build uses these settings.")
                self.saved.emit()
            # After publishing a save: only a file that differs from the open project counts.
            self._outside = payload.manifest != project.manifest
            self._fill(payload)
        else:
            action = "save" if self._saving else "read"
            reason = _reason(payload) if isinstance(payload, Exception) else "No project is open."
            self.problem.setText(breakable(f"Could not {action} the build settings. {reason}"))
        self._render()
        if self._saving:
            self.save_finished.emit(ok)

    def _fill(self, snapshot: DetailsSnapshot) -> None:
        choices = BuildChoices.of(snapshot.manifest.build)
        self.test_compression.setCurrentIndex(
            self.test_compression.findData(choices.test_compression)
        )
        self.release_compression.setCurrentIndex(
            self.release_compression.findData(choices.release_compression)
        )
        self.d_copy.setChecked(choices.make_d_variant)
        self.auto_add.setChecked(choices.auto_add)

    def _edited(self) -> None:
        if self._snapshot is not None and self.problem.text().startswith("Saved."):
            self.problem.clear()
        self._render()

    def _render(self) -> None:
        project = self._project
        self.fields.setHidden(project is None)
        self.action_row.setHidden(project is None)
        self.note.setText(
            NO_PROJECT
            if project is None
            else f"These settings belong to {project.manifest.project.name} and are saved in "
            f"its project file ({manifest_io.FILE_NAME})."
        )
        editable = self._snapshot is not None and not self._busy and not self._outside
        editable = editable and project is not None and not project.read_only
        for widget in (self.test_compression, self.release_compression, self.d_copy, self.auto_add):
            widget.setEnabled(editable)
        self.save_button.setEnabled(editable and self._may_save() and self.changed)
        self.undo_button.setEnabled(editable and self.changed)
        self.progress.setVisible(self._busy)
        self._blocked_note(editable)

    def _blocked_note(self, editable: bool) -> None:
        """Say why Save is off, when the reason is outside the page."""
        project, text = self._project, ""
        if project is not None and project.read_only and self._snapshot is not None:
            reason = project.read_only_reason or "No project write lock"
            text = f"This project is open read-only ({reason}), so it is shown only."
        elif self._outside:
            text = OUTSIDE
        elif editable and self.services.build.running:
            text = "A build is running. Save the changes after it finishes."
        elif editable and self.services.launch.busy:
            text = "Other work is still finishing. Save the changes after it."
        self.blocked.setText(breakable(text))
        self.blocked.setHidden(not text)


def _reason(error: Exception) -> str:
    if isinstance(error, OSError) and error.strerror:
        return f"{error.strerror}: {error.filename}" if error.filename else error.strerror
    return str(error) or type(error).__name__
