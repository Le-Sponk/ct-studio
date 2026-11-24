"""Settings → Build, "This computer" (P5-T08c): how many build steps may run at once.

A machine setting in ``settings.json`` (``build_jobs``), the same for every project and shown
with or without one: Automatic (the runner's own ``min(4, CPUs)``) or a number. Saving,
damaged files and the keyboard work as in every machine choice (``machine_choice``). GUI
builds and ``ctstudio build`` read the setting fresh, so the next build uses it.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import cast

from PySide6.QtWidgets import QWidget

from ctstudio.core.build.runner import default_jobs
from ctstudio.core.project.settings import MAX_BUILD_JOBS
from ctstudio.gui.build_settings import BuildJobsService
from ctstudio.gui.views.machine_choice import ChoiceTexts, MachineChoiceSection

INTRO = "The same for every project on this computer; a choice is saved at once."
OFFERED = min(MAX_BUILD_JOBS, max(8, os.cpu_count() or 1))  # more when the file says so
TEXTS = ChoiceTexts(
    name="buildJobs",
    intro=INTRO,
    label="Build steps at &once",
    tooltip="Used by the next build, in CT Studio and by ctstudio build.",
    subject="the build steps setting",
)


class BuildJobsSection(MachineChoiceSection):
    def __init__(self, service: BuildJobsService, parent: QWidget | None = None) -> None:
        self.service = service
        automatic = (f"Automatic ({default_jobs()} on this computer)", None)
        super().__init__(TEXTS, [automatic], parent)
        self._offer(TEXTS.name, OFFERED)

    def _load(self) -> Callable[[], Mapping[str, object]]:
        load = self.service.load
        return lambda: {TEXTS.name: load()}

    def _save(self, name: str, value: object) -> Callable[[], object]:
        service, jobs = self.service, cast("int | None", value)
        return lambda: service.save(jobs)

    def _saved(self, name: str, value: object) -> str:
        if value is None:
            return "Saved. The next build chooses how many steps run at once."
        return f"Saved. The next build runs up to {value} steps at once."

    def _offer(self, name: str, value: object) -> None:
        """Offer every number up to ``value`` (a saved number may be above the usual list)."""
        if isinstance(value, int):
            for jobs in range(self.combo.count(), value + 1):
                self.combo.addItem(str(jobs), jobs)
