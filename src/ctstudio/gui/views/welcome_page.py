"""Welcome and recent projects; all filesystem work runs on one joined worker thread."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.project import Project
from ctstudio.gui.recent_projects import RecentProjects, RecentResult

_LOG = logging.getLogger(__name__)
WORKER_NAME = "ctstudio-welcome"


def choose_project(parent: QWidget) -> Path | None:
    chosen = QFileDialog.getExistingDirectory(parent, "Open a CT Studio project folder")
    return Path(chosen) if chosen else None


@dataclass
class _Opened:
    project: Project
    history: RecentResult


class _Relay(QObject):
    done = Signal()


class WelcomePage(QWidget):
    new_requested = Signal()
    opened = Signal(object)
    checked = Signal()
    busy_changed = Signal(bool)

    def __init__(
        self,
        history: RecentProjects,
        *,
        choose_folder: Callable[[QWidget], Path | None] = choose_project,
        open_project: Callable[[Path], Project] = Project.open,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.history = history
        self._choose = choose_folder
        self._open = open_project
        self._thread: threading.Thread | None = None
        self._result: RecentResult | _Opened | Exception | None = None
        self._history = RecentResult(())
        self._stopped = False
        self._relay = _Relay()  # survives a pending emit until shutdown joins the worker
        self._relay.done.connect(self._finished)
        self._build()
        self.refresh()

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        self.title = title = QLabel("No project open", self)
        title.setObjectName("emptyTitle")
        title.setWordWrap(True)
        title.setTextFormat(Qt.TextFormat.PlainText)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        body = QLabel("Make a new track project, or open a project folder to continue.", self)
        body.setObjectName("emptyBody")
        body.setWordWrap(True)
        layout.addWidget(body)
        actions = QHBoxLayout()
        self._new = self._button("New project…", "welcomeNew", "Make a new track project.")
        self._new.clicked.connect(self.new_requested)
        self._browse = self._button("Open project…", "welcomeOpen", "Choose a project folder.")
        self._browse.clicked.connect(self.browse)
        actions.addWidget(self._new)
        actions.addWidget(self._browse)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(QLabel("Recent projects", self))
        self._list = QListWidget(self)
        self._list.setObjectName("recentProjects")
        self._list.setToolTip("Recently opened folders, newest first. Missing folders stay listed.")
        self._list.currentRowChanged.connect(self._selection)
        self._list.itemActivated.connect(lambda _item: self._open_selected())
        layout.addWidget(self._list, 1)
        self._empty = QLabel("No recent projects yet. Use New or Open to get started.", self)
        self._empty.setObjectName("recentEmpty")
        layout.addWidget(self._empty)
        self._build_footer(layout)

    def _build_footer(self, layout: QVBoxLayout) -> None:
        recent_actions = QHBoxLayout()
        self._recent = self._button("Open selected", "openRecent", "Open the selected project.")
        self._recent.clicked.connect(self._open_selected)
        self._remove = self._button(
            "Remove from list", "removeRecent", "Forget this entry; no files are deleted."
        )
        self._remove.clicked.connect(self._remove_selected)
        for button in (self._recent, self._remove):
            recent_actions.addWidget(button)
        recent_actions.addStretch()
        layout.addLayout(recent_actions)
        self._problem = QLabel(self)
        self._problem.setObjectName("welcomeProblem")
        self._problem.setWordWrap(True)
        self._problem.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._problem)
        self._progress = QProgressBar(self)
        self._progress.setObjectName("welcomeBusy")
        self._progress.setRange(0, 0)
        self._progress.setToolTip("Reading project folders and settings…")
        layout.addWidget(self._progress)

    def _button(self, text: str, name: str, tip: str) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName(name)
        button.setToolTip(tip)
        return button

    @property
    def problem(self) -> str:
        """The navigation/history warning, also visible when a project was opened."""
        return self._problem.text()

    def show_problem(self, message: str) -> None:
        self._problem.setText(message)

    def refresh(self) -> None:
        self._start(self.history.check)

    def remember(self, root: Path) -> None:
        self._start(lambda: self.history.remember(root))

    def browse(self) -> None:
        if self.busy or self._stopped:
            return
        chosen = self._choose(self)
        if chosen is not None:
            self.open_path(chosen)

    def open_path(self, root: Path) -> None:
        def job() -> _Opened:
            project = self._open(root)
            try:
                history = self.history.remember(root)
            except Exception as exc:  # the project opened: history failure must not lose its lock
                _LOG.exception("Saving recent projects failed")
                history = RecentResult(self._history.entries, _error(exc))
            return _Opened(project, history)

        self._start(job)

    def _start(self, operation: Callable[[], RecentResult | _Opened]) -> None:
        if self.busy or self._stopped:
            return

        def job() -> None:
            try:
                self._result = operation()
            except Exception as exc:  # always deliver worker failures to the window
                _LOG.exception("Welcome operation failed")
                self._result = exc
            self._relay.done.emit()

        self._thread = threading.Thread(target=job, name=WORKER_NAME, daemon=True)
        self._controls(True)
        self._thread.start()

    def _finished(self) -> None:
        if self._stopped:
            return
        if self._thread is not None:
            self._thread.join()  # worker has emitted; do not delete while it is still ending
        self._thread = None
        result, self._result = self._result, None
        if isinstance(result, Exception):
            self._problem.setText(_error(result))
        else:
            history = result.history if isinstance(result, _Opened) else result
            if history is not None:
                self._render(history)
        self._controls(False)
        if isinstance(result, _Opened):
            self.opened.emit(result.project)  # receiver now owns the open project
        self.checked.emit()

    def _render(self, result: RecentResult) -> None:
        self._history = result
        self._list.clear()
        for entry in result.entries:
            state = " — Missing folder" if entry.missing else ""
            item = QListWidgetItem(f"{entry.root.name}{state}\n{entry.root}", self._list)
            item.setToolTip(str(entry.root))
        self._empty.setVisible(not result.entries)
        self._problem.setText(result.problem or "")

    def _controls(self, busy: bool) -> None:
        self._new.setEnabled(not busy)
        self._browse.setEnabled(not busy)
        self._list.setEnabled(not busy)
        self._progress.setVisible(busy)
        self._selection()
        self.busy_changed.emit(busy)

    def _selection(self, _row: int = -1) -> None:
        row = self._list.currentRow()
        entry = self._history.entries[row] if 0 <= row < len(self._history.entries) else None
        self._recent.setEnabled(not self.busy and entry is not None and not entry.missing)
        self._remove.setEnabled(not self.busy and entry is not None and not self._history.problem)

    def _open_selected(self) -> None:
        if self._recent.isEnabled():
            self.open_path(self._history.entries[self._list.currentRow()].root)

    def _remove_selected(self) -> None:
        if self._remove.isEnabled():
            root = self._history.entries[self._list.currentRow()].root
            self._start(lambda: self.history.remove(root))

    def shutdown(self, timeout: float) -> bool:
        """Invalidate queued signals and release a project not yet handed to the window."""
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                return False
        self._stopped = True
        self._thread = None
        if isinstance(self._result, _Opened):
            self._result.project.close()
        self._result = None
        return True


def _error(exc: Exception) -> str:
    if isinstance(exc, CTStudioError):
        return str(exc)
    return (
        "The project or recent list could not be read. Choose another folder or try again; "
        "details are in the log."
    )
