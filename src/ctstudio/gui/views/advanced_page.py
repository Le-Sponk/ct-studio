"""Settings → Advanced (P5-T08e1): tool commands in the build log, and the open project's
reserved Wiimm arguments.

"Tool commands in the build log" is a machine setting in ``settings.json``
(``show_tool_commands``): Shown (the default) or Hidden. Saving, damaged files and the
keyboard work as in every machine choice (``machine_choice``); the next GUI build reads it.
The build log file on disk always lists the commands.

The open project's ``[build] extra_wszst_args`` is reserved: CT Studio does not pass it to
Wiimm's SZS Tools yet (P7-T06 will). It is shown read-only, from the project as CT Studio
holds it (read when the project opened, updated by CT Studio's own saves), at every opening
of the page. The two parts are two tabs, This computer and This project: together they are
taller than a 600 px screen at large fonts when the settings file's path is long.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from ctstudio.core.project.project import Project
from ctstudio.core.tools.commands import command_text
from ctstudio.gui.advanced import ToolCommandsService
from ctstudio.gui.views.machine_choice import ChoiceTexts, MachineChoiceSection
from ctstudio.gui.views.wrap_text import breakable

COMMANDS = ChoiceTexts(
    name="toolCommands",
    intro="The same for every project on this computer; a choice is saved at once.",
    label="&Tool commands in the build log",
    tooltip="The build log file in the project's .ctstudio/logs folder always lists them.",
    subject="the tool commands setting",
)
COMMAND_CHOICES: tuple[tuple[str, object], ...] = (("Shown", True), ("Hidden", False))
RESERVED_TITLE = "Extra arguments for wszst (not used yet)"
NO_PROJECT = "Open a project to see the extra wszst arguments saved in it."
NONE_SAVED = "None saved in this project."
RESERVED_NOTE = (
    "Saved in the project file as [build] extra_wszst_args. CT Studio does not pass them to "
    "Wiimm's SZS Tools yet; a later version will."
)


class ToolCommandsSection(MachineChoiceSection):
    def __init__(self, service: ToolCommandsService, parent: QWidget | None = None) -> None:
        self.service = service
        super().__init__(COMMANDS, COMMAND_CHOICES, parent)

    def _load(self) -> Callable[[], object]:
        return self.service.load

    def _save(self, value: object) -> Callable[[], object]:
        service, shown = self.service, cast("bool", value)
        return lambda: service.save(shown)

    def _saved(self, value: object) -> str:
        if value:
            return "Saved. The next build's log shows the tool commands."
        return "Saved. The next build's log leaves the tool commands out."


class AdvancedPage(QWidget):
    """The page: a tab for the machine choice, a tab for the open project's arguments."""

    def __init__(
        self,
        project: Callable[[], Project | None],
        service: ToolCommandsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("advancedPage")
        self._project = project
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("advancedTabs")
        QVBoxLayout(self).addWidget(self.tabs)
        self.commands = ToolCommandsSection(service, self.tabs)
        # A refused keyboard pick hides the choice: the keyboard goes to the tabs, not Close.
        self.commands.keyboard_lost.connect(self.tabs.tabBar().setFocus)
        self.tabs.addTab(self.commands, "This co&mputer")
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
        return self.commands.busy

    def reload(self) -> None:
        """Read the setting again and show the open project's reserved arguments."""
        self.commands.reload()
        project = self._project()
        self.reserved_note.setHidden(project is None)
        if project is None:
            self.reserved.setText(NO_PROJECT)
            return
        arguments = project.manifest.build.extra_wszst_args
        self.reserved.setText(breakable(command_text(arguments)) if arguments else NONE_SAVED)
