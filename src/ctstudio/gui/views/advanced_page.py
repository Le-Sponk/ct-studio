"""Settings → Advanced (P5-T08e1, P5-T08e2): tool commands in the build log, build logs kept,
and the open project's reserved Wiimm arguments.

Tab This computer holds two machine settings in ``settings.json``, in one section so a
damaged file is explained once. "Tool commands in the build log" (``show_tool_commands``):
Shown (the default) or Hidden; the next GUI build reads it, and the build log file on disk
always lists the commands. "Build logs kept per project" (``build_logs_kept``): 20 (the
default) or another number; after the next build, in CT Studio or by ``ctstudio build``,
only that many ``.ctstudio/logs/build-*.log`` remain in the project built. Saving, damaged
files and the keyboard work as in every machine choice (``machine_choice``).

The open project's ``[build] extra_wszst_args`` is reserved: CT Studio does not pass it to
Wiimm's SZS Tools yet (P7-T06 will). It is shown read-only, from the project as CT Studio
holds it (read when the project opened, updated by CT Studio's own saves), at every opening
of the page. The two parts are two tabs, This computer and This project: together they are
taller than a 600 px screen at large fonts when the settings file's path is long.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from ctstudio.core.build.build_log import KEEP
from ctstudio.core.project.project import Project
from ctstudio.core.tools.commands import command_text
from ctstudio.gui.advanced import BUILD_LOGS_KEPT, TOOL_COMMANDS, AdvancedService
from ctstudio.gui.views.machine_choice import ChoiceRow, ChoiceTexts, MachineChoiceSection
from ctstudio.gui.views.wrap_text import breakable

COMMANDS = ChoiceTexts(
    name=TOOL_COMMANDS,
    intro="The same for every project on this computer; a choice is saved at once.",
    label="&Tool commands in the build log",
    tooltip="The build log file in the project's .ctstudio/logs folder always lists them.",
    subject="the Advanced settings",
)
COMMAND_CHOICES: tuple[tuple[str, object], ...] = (("Shown", True), ("Hidden", False))
LOGS = ChoiceRow(
    name=BUILD_LOGS_KEPT,
    label="&Build logs kept per project",
    tooltip=(
        "After each build, in CT Studio and by ctstudio build, older build logs in the"
        " project's .ctstudio/logs folder are deleted."
    ),
    choices=((f"{KEEP} (default)", None), ("5", 5), ("10", 10), ("50", 50), ("100", 100)),
)
RESERVED_TITLE = "Extra arguments for wszst (not used yet)"
NO_PROJECT = "Open a project to see the extra wszst arguments saved in it."
NONE_SAVED = "None saved in this project."
RESERVED_NOTE = (
    "Saved in the project file as [build] extra_wszst_args. CT Studio does not pass them to "
    "Wiimm's SZS Tools yet; a later version will."
)


class ComputerSection(MachineChoiceSection):
    """Tab This computer: tool commands in the build log, then build logs kept."""

    def __init__(self, service: AdvancedService, parent: QWidget | None = None) -> None:
        self.service = service
        super().__init__(COMMANDS, COMMAND_CHOICES, parent, more=(LOGS,))
        self.logs = self.rows[BUILD_LOGS_KEPT][1]

    def _load(self) -> Callable[[], Mapping[str, object]]:
        return self.service.load

    def _save(self, name: str, value: object) -> Callable[[], object]:
        service = self.service
        if name == BUILD_LOGS_KEPT:
            kept = cast("int | None", value)
            return lambda: service.save_build_logs_kept(kept)
        shown = cast("bool", value)
        return lambda: service.save_tool_commands(shown)

    def _saved(self, name: str, value: object) -> str:
        if name == BUILD_LOGS_KEPT:
            kept = KEEP if value is None else value
            logs = "build log" if kept == 1 else f"{kept} build logs"
            return f"Saved. After the next build each project keeps only its newest {logs}."
        if value:
            return "Saved. The next build's log shows the tool commands."
        return "Saved. The next build's log leaves the tool commands out."

    def _offer(self, name: str, value: object) -> None:
        """A saved number of build logs outside the list is offered too, in order."""
        if name != BUILD_LOGS_KEPT or not isinstance(value, int) or self.logs.findData(value) >= 0:
            return
        numbers = [self.logs.itemData(i) for i in range(1, self.logs.count())]
        at = 1 + sum(1 for number in numbers if isinstance(number, int) and number < value)
        self.logs.insertItem(at, str(value), value)


class AdvancedPage(QWidget):
    """The page: a tab for the machine choices, a tab for the open project's arguments."""

    def __init__(
        self,
        project: Callable[[], Project | None],
        service: AdvancedService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("advancedPage")
        self._project = project
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("advancedTabs")
        QVBoxLayout(self).addWidget(self.tabs)
        self.computer = ComputerSection(service, self.tabs)
        # A refused keyboard pick hides the choices: the keyboard goes to the tabs, not Close.
        self.computer.keyboard_lost.connect(self.tabs.tabBar().setFocus)
        self.tabs.addTab(self.computer, "This co&mputer")
        self.project_tab = QWidget(self.tabs)
        layout = QVBoxLayout(self.project_tab)
        title = QLabel(RESERVED_TITLE, self.project_tab)
        title.setObjectName("reservedTitle")
        layout.addWidget(title)
        self.reserved = self._text("reservedWszstArgs", layout)
        self.reserved_note = self._text("reservedNote", layout)
        self.reserved_note.setText(RESERVED_NOTE)
        layout.addStretch()
        self.tabs.addTab(self.project_tab, "This &project")

    def _text(self, name: str, layout: QVBoxLayout) -> QLabel:
        label = QLabel(self.project_tab)
        label.setObjectName(name)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        return label

    @property
    def busy(self) -> bool:
        return self.computer.busy

    def reload(self) -> None:
        """Read the settings again and show the open project's reserved arguments."""
        self.computer.reload()
        project = self._project()
        self.reserved_note.setHidden(project is None)
        if project is None:
            self.reserved.setText(NO_PROJECT)
            return
        arguments = project.manifest.build.extra_wszst_args
        self.reserved.setText(breakable(command_text(arguments)) if arguments else NONE_SAVED)
