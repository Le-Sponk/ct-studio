"""Add or edit one of the user's own editor programs (P5-T07f2).

The dialog only collects and checks the entry with ``CustomTool``'s own rules (a name, a
program, arguments that use only ``{file}``, ``{dir}`` and ``{project}``) plus the settings
file's text rules; the reason is shown and the dialog stays open until the entry is valid.
Saving happens afterwards, in the Editors window, on its worker.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.errors import ProjectError
from ctstudio.core.tools.spec import CustomTool

_HELP = (
    "One argument per line. Use {file} for the file to open, {dir} for its folder and "
    "{project} for the project folder; each line is passed as one argument, spaces included."
)


def _plain(label: str, text: str) -> str:
    verb = "contain" if label == "arguments" else "contains"
    if "\0" in text:
        raise ValueError(f"The {label} {verb} a NUL character; remove it.")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"The {label} {verb} text that cannot be saved; retype it.") from None
    return text


def custom_entry(name: str, program: str, arguments: str) -> CustomTool:
    """The entry as a ``CustomTool`` (its own rules decide), or ``ValueError`` saying what to
    fix. Surrounding spaces of the name and program and blank argument lines are dropped."""
    lines = [_plain("arguments", line) for line in arguments.splitlines() if line.strip()]
    name, program = _plain("name", name.strip()), _plain("program", program.strip())
    for line in lines:
        try:
            CustomTool("check", Path("check"), [line])
        except ProjectError:
            raise ValueError(
                f"The argument {line} cannot be used: the only names allowed in braces are "
                "{file}, {dir} and {project}, written exactly like that."
            ) from None
    try:
        return CustomTool(name, Path(program), lines)
    except ProjectError:
        raise ValueError("Enter a name and the program to start.") from None


class CustomToolDialog(QDialog):
    chosen = Signal(object)  # the checked entry (a CustomTool), just before closing

    def __init__(self, tool: CustomTool | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("customToolDialog")
        self.setWindowTitle("Add editor" if tool is None else "Edit editor")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.name = QLineEdit("" if tool is None else tool.name, self)
        self.name.setObjectName("customToolName")
        form.addRow("&Name shown in Open in…:", self.name)
        self.program = QLineEdit("" if tool is None else str(tool.exe), self)
        self.program.setObjectName("customToolProgram")
        self.browse = QPushButton("&Browse…", self)
        self.browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.program, 1)
        row.addWidget(self.browse)
        form.addRow("&Program:", row)
        label = form.labelForField(row)
        if isinstance(label, QLabel):
            label.setBuddy(self.program)
        arguments = ["{file}"] if tool is None else tool.args_template
        self.arguments = QPlainTextEdit("\n".join(arguments), self)
        self.arguments.setObjectName("customToolArguments")
        self.arguments.setTabChangesFocus(True)
        lines = self.fontMetrics().lineSpacing()
        self.arguments.setMinimumHeight(lines * 4)
        self.arguments.setMaximumHeight(lines * 7)
        form.addRow("&Arguments:", self.arguments)
        layout.addLayout(form)
        hint = QLabel(_HELP, self)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.problem = QLabel(self)
        self.problem.setObjectName("customToolProblem")
        self.problem.setWordWrap(True)
        self.problem.setFrameShape(QLabel.Shape.StyledPanel)
        self.problem.hide()
        layout.addWidget(self.problem)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.browser: QFileDialog | None = None

    def _fit(self) -> None:
        """Keep the window tall enough for its wrapped text at the narrowest width it may
        take, so the help text and the reason are never cut short however the window is
        resized. Qt's own minimum size for a window ignores how tall wrapped text gets (seen
        on Ubuntu's wider fonts), and its first size is at most two thirds of the screen. On a
        short screen the narrowest width is raised until the text fits the screen's height.
        The minimum lets the arguments box shrink to its own minimum; Qt grows the window to
        a raised minimum by itself. Done when shown and whenever a reason appears."""
        layout = self.layout()
        if layout is None:
            return
        layout.activate()
        screen = self.screen().availableGeometry()
        least = layout.minimumHeightForWidth  # includes the window's margins
        narrowest = layout.minimumSize().width()
        while least(narrowest) > screen.height() and narrowest < screen.width():
            narrowest = min(narrowest + 20, screen.width())
        self.setMinimumWidth(narrowest)
        # Never taller than the screen (very wide fonts on a short screen): the buttons and
        # fields then give up their spare space.
        self.setMinimumHeight(min(least(narrowest), screen.height()))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._fit()

    def _browse(self) -> None:
        browser = QFileDialog(self, "Choose the editor program", self.program.text().strip())
        browser.setFileMode(QFileDialog.FileMode.ExistingFile)
        browser.fileSelected.connect(self.program.setText)
        browser.finished.connect(browser.deleteLater)
        self.browser = browser
        browser.open()

    def accept(self) -> None:
        try:
            tool = custom_entry(self.name.text(), self.program.text(), self.arguments.toPlainText())
        except ValueError as exc:
            self.problem.setText(str(exc))
            self.problem.show()
            self._fit()
            return
        self.chosen.emit(tool)
        super().accept()
