"""Edit slot/source with explicit Save; all project file work runs on a joined thread."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.project.slots import CATALOGUE
from ctstudio.gui.project_details import DetailsSnapshot, ProjectDetailsService
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.new_project_pages import Choose, choose_blend

_LOG = logging.getLogger(__name__)
WORKER_NAME = "ctstudio-project-details"


class _Relay(QObject):
    done = Signal(object)


class ProjectDetailsDialog(QDialog):
    def __init__(
        self,
        services: AppServices,
        *,
        service: ProjectDetailsService | None = None,
        choose: Choose = choose_blend,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("projectDetailsDialog")
        self.setWindowTitle("Project details")
        self.setModal(True)
        self.resize(640, 260)
        self.services = services
        self.project = services.project
        self.service = service if service is not None else ProjectDetailsService()
        self._choose = choose
        self.saved = False
        self._saving = False
        self._snapshot: DetailsSnapshot | None = None
        self._busy = False
        self._owns_edit = False
        self._worker: threading.Thread | None = None
        self._relay = _Relay(self)
        self._relay.done.connect(self._completed)
        self.finished.connect(self._release)
        self._make_fields()
        self.services.build.running_changed.connect(self._controls)
        project = self.project
        if project is None or project.read_only or services.editing or services.build.running:
            self.problem.setText(
                "Project details cannot be edited now. Close this window and try again "
                "with a writable project after other work finishes."
            )
            self._controls()
            return
        self._owns_edit = True
        services.editing = True
        self._start(lambda: self.service.load(project))

    def _make_fields(self) -> None:
        layout = QVBoxLayout(self)
        note = QLabel("Choose the original track to replace and the optional Blender source.", self)
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.slot = QComboBox(self)
        self.slot.setObjectName("detailsSlot")
        self.slot.setToolTip("The original track or arena this project replaces.")
        for slot in CATALOGUE:
            self.slot.addItem(f"{slot.name} ({slot.abbr}) — {slot.file}.szs", slot.file)
        form.addRow("&Replaces", self.slot)
        self.source = QLineEdit(self)
        self.source.setObjectName("detailsSource")
        self.source.setPlaceholderText("No Blender file chosen")
        self.source.setToolTip("Full path of a .blend file, or empty for no source.")
        form.addRow("&Blender source", self.source)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.choose_button = QPushButton("Choose Blender file…", self)
        self.choose_button.setObjectName("detailsChooseSource")
        self.choose_button.setToolTip("Choose an existing .blend file without changing it.")
        self.choose_button.clicked.connect(self._browse)
        self.clear_button = QPushButton("Clear source", self)
        self.clear_button.setObjectName("detailsClearSource")
        self.clear_button.setToolTip(
            "Remove the source reference; the Blender file is not deleted."
        )
        self.clear_button.clicked.connect(self.source.clear)
        row.addWidget(self.choose_button)
        row.addWidget(self.clear_button)
        row.addStretch()
        layout.addLayout(row)
        self.problem = QLabel(self)
        self.problem.setObjectName("detailsProblem")
        self.problem.setTextFormat(Qt.TextFormat.PlainText)
        self.problem.setWordWrap(True)
        layout.addWidget(self.problem)
        self.progress = QProgressBar(self)
        self.progress.setObjectName("detailsProgress")
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        self.buttons.setObjectName("detailsButtons")
        self.save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setObjectName("saveProjectDetails")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    @property
    def busy(self) -> bool:
        return self._busy

    def _allowed(self) -> bool:
        return (
            self._owns_edit
            and self.project is not None
            and not self.project.read_only
            and self.services.project is self.project
            and not self.services.build.running
        )

    def _controls(self) -> None:
        editable = self._allowed() and not self._busy and self._snapshot is not None
        self.slot.setEnabled(editable)
        self.source.setEnabled(editable)
        self.choose_button.setEnabled(editable)
        self.clear_button.setEnabled(editable)
        self.save_button.setEnabled(editable)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(not self._busy)
        self.progress.setVisible(self._busy)

    def _browse(self) -> None:
        if self._busy or not self._allowed() or self.project is None:
            return
        chosen = self._choose(self, self.project.root)
        if chosen is not None:
            self.source.setText(str(chosen))

    def accept(self) -> None:
        project, snapshot = self.project, self._snapshot
        if self._busy or not self._allowed() or project is None or snapshot is None:
            return
        slot = self.slot.currentData()
        if not isinstance(slot, str):
            self.problem.setText("Choose an original track or arena before saving.")
            return
        source = self.source.text().strip()
        blend = Path(source) if source else None
        self._start(lambda: self.service.save(project, snapshot, slot, blend), saving=True)

    def _start(self, action: Callable[[], DetailsSnapshot], *, saving: bool = False) -> None:
        self._saving = saving
        self._busy = True
        self.problem.setText("Saving project details…" if saving else "Loading project details…")
        self._controls()
        relay = self._relay

        def job() -> None:
            try:
                result: DetailsSnapshot | Exception = action()
            except Exception as exc:  # failures must reach the dialog, not vanish in a thread
                _LOG.exception("Project details operation failed")
                result = exc
            relay.done.emit(result)

        self._worker = threading.Thread(target=job, name=WORKER_NAME, daemon=True)
        try:
            self._worker.start()
        except Exception as exc:
            self._completed(exc)

    def _completed(self, payload: object) -> None:
        if self._worker is not None and self._worker.ident is not None:
            self._worker.join()
        self._worker = None
        self._busy = False
        if isinstance(payload, DetailsSnapshot) and self._allowed():
            self._snapshot = payload
            if self._saving and self.project is not None:
                self.project.manifest = payload.manifest
                self.saved = True
                super().accept()
                return
            self.slot.setCurrentIndex(self.slot.findData(payload.manifest.project.slot))
            source = payload.manifest.project.blend
            self.source.setText(str(payload.root / source) if source else "")
            self.problem.clear()
        else:
            operation = "save" if self._saving else "load"
            reason = str(payload) if isinstance(payload, Exception) else "The project changed."
            self.problem.setText(
                f"Could not {operation} project details. {reason} Close and reopen to retry."
            )
        self._controls()

    def reject(self) -> None:
        if not self._busy:
            super().reject()

    def _release(self, _result: int) -> None:
        if self._owns_edit:
            self.services.editing = False
            self._owns_edit = False
