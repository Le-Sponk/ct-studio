"""The editor-choice dialog for one file (P5-T07e1): pick an available editor, or learn why not.

Signal-free and work-free: it only shows a delivered PreparedEditors snapshot and records the
chosen EditorChoice. The dashboard opens it after preparation and dispatches the choice through
the joined launch owner, which re-checks the project and the choice before starting anything.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.gui.editor_launch import EditorOption, PreparedEditors
from ctstudio.gui.views.plain import plain_label

_SUFFIX = {"available": "", "missing": " (not found)", "ineligible": " (cannot open this file)"}
READ_ONLY = "This project is open read-only here, so no editor can be started from it."
NONE_AVAILABLE = "No editor here can open this file yet."
LAUNCH_ONLY = "CT Studio starts the editor; it cannot tell whether the file finished opening."


def _reason(option: EditorOption) -> str:
    return f"{option.explanation}\nNext: {option.hint}" if option.hint else option.explanation


class EditorChoices(QDialog):
    """Choose one available editor for ``prepared.document``; ``chosen`` is None otherwise."""

    def __init__(
        self,
        prepared: PreparedEditors,
        *,
        can_open: bool,
        why_not: str | None = None,
        part: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("editorChoices")
        what = f"{part} ({prepared.document.name})" if part else prepared.document.name
        self.setWindowTitle(f"Open {what} in…")
        self.chosen: EditorChoice | None = None
        self.setup: str | None = None  # a missing built-in editor to set up in Tools
        self._options = prepared.options
        self._can_open = can_open
        self._why_not = why_not
        layout = QVBoxLayout(self)
        heading = QLabel(f"&Choose an editor for {what}:", self)
        heading.setTextFormat(Qt.TextFormat.PlainText)  # names a file; the & still works
        layout.addWidget(heading)
        self.choices = QListWidget(self)
        heading.setBuddy(self.choices)
        self.choices.setObjectName("editorChoiceList")
        self.choices.setAccessibleName("Editors")
        self.choices.setAccessibleDescription(f"Editors for {what}")
        for option in self._options:
            item = QListWidgetItem(option.label + _SUFFIX[option.state], self.choices)
            item.setToolTip(_reason(option))
            item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, _reason(option))
            if option.state != "available":
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        self.choices.itemDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.choices)
        self.setup_button = self._setup_button()
        layout.addWidget(self.setup_button)
        self.notes = plain_label(self, "editorChoiceNotes", self._notes(), selectable=True)
        layout.addWidget(self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, parent=self)
        self.open_button = buttons.addButton("Open", QDialogButtonBox.ButtonRole.AcceptRole)
        self.open_button.setObjectName("editorChoiceOpen")
        self.open_button.clicked.connect(self._open_current)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        first = next((row for row, o in enumerate(self._options) if o.state == "available"), -1)
        self.choices.setCurrentRow(first)
        self.open_button.setEnabled(can_open and first >= 0)
        self.open_button.setDefault(True)

    def _notes(self) -> str:
        lines: list[str] = []
        if not self._can_open:
            lines.append(READ_ONLY)
            if self._why_not:  # the project's own reason, e.g. who holds it
                lines.append(f"Why: {self._why_not.rstrip('.')}.")
        elif not any(option.state == "available" for option in self._options):
            lines.append(NONE_AVAILABLE)
        lines += [f"{o.label}: {_reason(o)}" for o in self._options if o.state != "available"]
        lines.append(LAUNCH_ONLY)
        return "\n".join(lines)

    def _setup_button(self) -> QPushButton:
        """One way to the Tools window for the missing built-in editors (custom ones are not
        listed there, and an ineligible editor needs a file, not a tool)."""
        missing = [
            o for o in self._options if o.state == "missing" and o.choice.namespace == "builtin"
        ]
        name = missing[0].label if len(missing) == 1 else "editors"
        button = QPushButton(f"Set up {name} in Tools…", self)
        button.setObjectName("editorChoiceSetup")
        button.setToolTip("Opens Settings → Tools, where you can choose or download a program.")
        button.setEnabled(bool(missing))
        button.setVisible(bool(missing))
        self._setup_id = missing[0].choice.tool_id if missing else None
        button.clicked.connect(self._set_up)
        return button

    def _set_up(self) -> None:
        if self._setup_id is not None:
            self.setup = self._setup_id
            self.reject()

    def _choose(self, row: int) -> None:
        if self._can_open and 0 <= row < len(self._options):
            option = self._options[row]
            if option.state == "available":
                self.chosen = option.choice
                self.accept()

    def _open_current(self) -> None:
        self._choose(self.choices.currentRow())

    def _double_clicked(self, item: QListWidgetItem) -> None:
        self._choose(self.choices.row(item))
