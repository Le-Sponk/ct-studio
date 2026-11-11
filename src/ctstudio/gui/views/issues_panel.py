"""The dashboard's Issues panel (P5-T05b): the last check's findings, grouped by part.

It only shows a report the status thread has already read (``StatusResult.issues``) and
asks for a card with ``part_requested``; it does no disk work. A click or Enter on a
finding asks for its part's card. The selected finding's next step, file and help page are
shown below the list, and "Copy report" copies the whole report as Markdown.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.validation.issues import Issue
from ctstudio.core.validation.report import (
    IssueGroup,
    IssueReport,
    counts_text,
    report_text,
    severity_word,
    shown_file,
)

OpenUrl = Callable[[str], object]
NOT_CHECKED = "Not checked yet: build the track to check it for problems."
PICK = "Select a finding to see its next step and file."
_ENTRY = Qt.ItemDataRole.UserRole


def _open_url(url: str) -> bool:
    return QDesktopServices.openUrl(QUrl(url))


def _wiki_page(text: str | None) -> str | None:
    """Saved findings may link to wiki pages, never to OS protocol handlers or local files."""
    if text is None:
        return None
    url = QUrl(text, QUrl.ParsingMode.StrictMode)
    allowed = (
        url.isValid()
        and url.scheme() == "https"
        and url.host() == "mkwiiki.org"
        and not url.userInfo()
        and url.port() in (-1, 443)
        and url.path().startswith("/wiki/")
    )
    return text if allowed else None


def _one_line(text: str) -> str:
    return " ".join(text.split())


class IssuesPanel(QWidget):
    part_requested = Signal(str)  # a component id: show and focus its card

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("issuesPanel")
        self.open_url: OpenUrl = _open_url
        self._report: IssueReport | None = None
        self._name = ""
        self._entries: list[tuple[IssueGroup, Issue | None]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        title = self._text("issuesTitle", "Issues")
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        self.summary = self._text("issuesSummary", NOT_CHECKED)
        layout.addWidget(self.summary)
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("issuesTree")
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setAccessibleName("Issues found by the last check")
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tree.setMinimumHeight(self.tree.fontMetrics().lineSpacing() * 10)
        self.tree.currentItemChanged.connect(self._selected)
        self.tree.itemClicked.connect(self._go)
        self.tree.itemActivated.connect(self._go)
        layout.addWidget(self.tree)
        self.detail = self._text("issuesDetail", PICK)
        self.detail.setMaximumHeight(self.detail.fontMetrics().lineSpacing() * 6)
        layout.addWidget(self.detail)
        layout.addLayout(self._buttons())
        self.clear()

    def _text(self, name: str, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName(name)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()
        self.help_button = QPushButton("Open help page", self)
        self.help_button.setObjectName("issuesHelp")
        self.help_button.clicked.connect(self._open_help)
        row.addWidget(self.help_button)
        self.copy_button = QPushButton("Copy report", self)
        self.copy_button.setObjectName("issuesCopy")
        self.copy_button.setToolTip("Copy every finding, with next steps and help pages.")
        self.copy_button.setAccessibleDescription(self.copy_button.toolTip())
        self.copy_button.clicked.connect(self._copy)
        row.addWidget(self.copy_button)
        return row

    def clear(self) -> None:
        """Nothing checked yet (or another project): no findings, nothing to copy."""
        self.show_report(None, None, "")

    def show_report(self, report: IssueReport | None, problem: str | None, name: str) -> None:
        self._report = report  # the status worker returns either a report or a problem
        self._name = name
        self._entries = []
        self.tree.clear()
        if problem:
            self._set_summary(problem)
        elif report is None:
            self._set_summary(NOT_CHECKED)
        elif not report.groups:
            self._set_summary(f"The last check of {report.track} found no issues.")
        else:
            self._set_summary(f"Last check of {report.track}: {counts_text(report)}.")
            for group in report.groups:
                self._add_group(group)
        self.copy_button.setEnabled(self._report is not None)
        self._selected(None)

    def _set_summary(self, text: str) -> None:
        self.summary.setText(text)
        self.summary.setAccessibleDescription(text)

    def _add_group(self, group: IssueGroup) -> None:
        item = QTreeWidgetItem(self.tree, [f"{group.title} — {_counts(group)}"])
        item.setData(0, _ENTRY, self._remember(group, None))
        for issue in group.issues:
            text = f"{severity_word(issue.severity)}: {_one_line(issue.message)}"
            row = QTreeWidgetItem(item, [text])
            row.setToolTip(0, text)
            row.setData(0, _ENTRY, self._remember(group, issue))
        item.setExpanded(True)

    def _remember(self, group: IssueGroup, issue: Issue | None) -> int:
        self._entries.append((group, issue))
        return len(self._entries) - 1

    def _entry(self, item: QTreeWidgetItem | None) -> tuple[IssueGroup, Issue | None] | None:
        index = None if item is None else item.data(0, _ENTRY)
        return self._entries[index] if isinstance(index, int) else None

    def _selected(self, item: QTreeWidgetItem | None, _previous: object = None) -> None:
        entry = self._entry(item)
        page = None
        if entry is None:
            text = PICK if self._entries else ""
        else:
            group, issue = entry
            text = self._describe(group, issue)
            page = _wiki_page(issue.wiki) if issue is not None else None
            page = page or _wiki_page(group.wiki)
        self.detail.setText(text)
        self.detail.setToolTip(text)
        self.detail.setAccessibleDescription(text)
        self.help_button.setEnabled(page is not None)
        self.help_button.setToolTip(page or "")

    def _describe(self, group: IssueGroup, issue: Issue | None) -> str:
        if issue is None:
            return f"{group.title}: {_counts(group)}. Select a finding to see its details."
        lines = [f"{severity_word(issue.severity)}: {_one_line(issue.message)}"]
        if issue.hint:
            lines.append(f"Next: {_one_line(issue.hint)}")
        if issue.file is not None:
            root = self._report.root if self._report is not None else None
            lines.append(f"File: {shown_file(issue.file, root)}")
        lines.append("About the whole track." if group.part is None else f"Part: {group.title}")
        return "\n".join(lines)

    def _go(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        entry = self._entry(item)
        if entry is not None and entry[1] is not None and entry[0].part is not None:
            self.part_requested.emit(entry[0].part)

    def _open_help(self) -> None:
        page = self.help_button.toolTip()
        if self.help_button.isEnabled() and page:
            self.open_url(page)

    def _copy(self) -> None:
        if self._report is not None:
            QApplication.clipboard().setText(report_text(self._report, self._name))


def _counts(group: IssueGroup) -> str:
    return counts_text(IssueReport((group,)))
