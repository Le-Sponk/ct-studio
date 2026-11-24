"""Settings → Appearance (P5-T08d): the colour scheme, Follow system, Light or Dark.

A machine setting in ``settings.json`` (``colour_scheme``), the same for every project.
Saving, damaged files and the keyboard work as in every machine choice
(``machine_choice``). A saved choice is applied at once (``appearance.apply_scheme``); where
the system does not let Qt change the scheme, the note says so. Every start applies the
saved scheme again (``run_gui``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PySide6.QtWidgets import QWidget

from ctstudio.gui.appearance import AppearanceService, apply_scheme
from ctstudio.gui.views.machine_choice import ChoiceTexts, MachineChoiceSection

TEXTS = ChoiceTexts(
    name="colourScheme",
    intro="The same for every project on this computer; a choice is saved and used at once.",
    label="Colour &scheme",  # Alt+C may be Close on Linux
    tooltip="Follow system uses the light or dark scheme your system is set to.",
    subject="the colour scheme setting",
)
CHOICES: tuple[tuple[str, object], ...] = (
    ("Follow system", None),
    ("Light", "light"),
    ("Dark", "dark"),
)


class AppearanceSection(MachineChoiceSection):
    def __init__(
        self,
        service: AppearanceService,
        parent: QWidget | None = None,
        *,
        apply: Callable[[str | None], bool] = apply_scheme,
    ) -> None:
        self.service = service
        self._apply = apply
        super().__init__(TEXTS, CHOICES, parent)

    def _load(self) -> Callable[[], object]:
        return self.service.load

    def _save(self, value: object) -> Callable[[], object]:
        service, scheme = self.service, cast("str | None", value)
        return lambda: service.save(scheme)

    def _saved(self, value: object) -> str:
        scheme = cast("str | None", value)
        if not self._apply(scheme):
            return "Saved, but this system does not let CT Studio change its colour scheme."
        if scheme is None:
            return "Saved. CT Studio follows the system's colour scheme."
        return f"Saved. CT Studio uses the {scheme} colour scheme."
