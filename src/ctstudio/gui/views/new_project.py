"""The new-project wizard (P5-T02a): name and folder, .blend, the track it replaces, summary.

Each page says what is wrong in plain words and keeps Next off until it is right. Finish
makes the project with ``Project.create`` on a named thread (``ctstudio-new-project``),
joined before the wizard closes. The wizard stays open (Back, Finish and Cancel off) until it
is made, shows a failure on the summary page, and hands the new project over open, so locked,
as ``project``. The pages are in ``new_project_pages``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget, QWizard

from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.project import Project
from ctstudio.gui.views.new_project_pages import (
    BlendPage,
    Choose,
    NamePage,
    SlotPage,
    SummaryPage,
    choose_blend,
    choose_folder,
    folder_name,
)

_LOG = logging.getLogger(__name__)
Create = Callable[..., Project]  # (root, name, *, blend, slot) -> the project, opened
WORKER_NAME = "ctstudio-new-project"
__all__ = ["WORKER_NAME", "NewProjectWizard", "folder_name"]


class _Relay(QObject):
    done = Signal(object)  # the Project, or the exception


class NewProjectWizard(QWizard):
    """Accepted once the project is made; it is then ``project`` (open, so locked)."""

    def __init__(
        self,
        *,
        default_location: Path,
        create: Create = Project.create,
        choose_folder: Choose = choose_folder,
        choose_blend: Choose = choose_blend,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("newProjectWizard")
        self.setWindowTitle("New project")
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage)
        self._create = create
        self._relay = _Relay(self)
        self._relay.done.connect(self._made)
        self.project: Project | None = None
        self._busy = False
        self._worker: threading.Thread | None = None
        self._name = NamePage(default_location, choose_folder)
        self._blend = BlendPage(choose_blend, self._blend_start)
        self._slot = SlotPage()
        self._summary = SummaryPage()
        for page in (self._name, self._blend, self._slot, self._summary):
            self.addPage(page)
        self.currentIdChanged.connect(self._page_changed)

    @property
    def busy(self) -> bool:
        return self._busy

    def accept(self) -> None:
        """Finish: make the project on a worker; the wizard closes once it is made."""
        if self.project is not None:
            super().accept()
            return
        root, slot = self._name.root(), self._slot.chosen()
        if self._busy or root is None or slot is None:
            return
        name, blend, create, relay = (
            self._name.name.text().strip(),
            self._blend.chosen(),
            self._create,
            self._relay,
        )

        def job() -> None:
            result: Project | Exception
            try:
                result = create(root, name, blend=blend, slot=slot.file)
            except CTStudioError as exc:
                result = exc
            except Exception as exc:  # any failure must reach the wizard, not die here
                _LOG.exception("Making the project failed")
                result = exc
            relay.done.emit(result)

        self._set_busy(True)
        self._summary.problem.setText("")
        self._worker = threading.Thread(target=job, name=WORKER_NAME, daemon=True)
        self._worker.start()

    def reject(self) -> None:
        if not self._busy:  # Escape or Cancel while making it: wait for it
            super().reject()

    def _made(self, result: object) -> None:
        if self._worker is not None:  # its last step was the emit: done, or about to be
            self._worker.join()
            self._worker = None
        self._set_busy(False)
        if isinstance(result, Project):
            self.project = result
            super().accept()
        elif isinstance(result, CTStudioError):
            self._summary.problem.setText(f"{result.user_message}\n{result.hint or ''}".strip())
        else:
            self._summary.problem.setText(
                "The project could not be made. The details are in CT Studio's log."
            )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._summary.busy.setVisible(busy)
        for which in (
            QWizard.WizardButton.FinishButton,
            QWizard.WizardButton.BackButton,
            QWizard.WizardButton.CancelButton,
        ):
            button = self.button(which)
            if button is not None:
                button.setEnabled(not busy)

    def _blend_start(self) -> Path:
        where = self._name.location.text().strip()
        return Path(where) if where else Path.home()

    def _page_changed(self, _page: int) -> None:
        if self.currentPage() is self._summary:
            self._summary.problem.setText("")
            self._summary.text.setText(self._summary_text())

    def _summary_text(self) -> str:
        root, slot, blend = self._name.root(), self._slot.chosen(), self._blend.chosen()
        lines = [
            f"Track name: {self._name.name.text().strip()}",
            f"Project folder: {root}",
            f"Blender file: {blend if blend is not None else 'none yet (you can add it later)'}",
            f"Replaces: {slot.label if slot is not None else '-'}",
        ]
        return "\n".join(lines)
