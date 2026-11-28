"""P5-T03e21: signal-only actions and progress; the parent owns the run."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.build.events import (
    BuildEvent,
    BuildStarted,
    BuildSummary,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
)
from ctstudio.core.errors import CTStudioError
from ctstudio.gui.views.copy_details import CopyDetails, details_of

_TEST = "Build a track to try in the game, with the test compression"
_RELEASE = (
    "Build the track to share, with the release compression; an error in the final check stops it"
)
from ctstudio.gui.views.plain import plain_label


class BuildControls(QWidget):
    """Render build state without starting work or deciding worker ownership."""

    build_requested = Signal(bool)
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cancel_requested = False
        self._enabled = False
        self._running = False
        self._steps: set[str] = set()
        self._completed: set[str] = set()
        self._warning = ""
        self._error = ""
        self._details: str | None = None  # the error's details, copied, never shown (P5-T10f)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        buttons = QHBoxLayout()
        self.test_button = QPushButton("Build test", self)
        self.release_button = QPushButton("Build release", self)
        self.cancel_button = QPushButton("Cancel build", self)
        for button, name, shortcut, does in (
            (self.test_button, "buildTest", "Ctrl+B", _TEST),
            (self.release_button, "buildRelease", "Ctrl+Shift+B", _RELEASE),
            (self.cancel_button, "cancelBuild", "Esc", "Stop the running build"),
        ):
            button.setObjectName(name)
            button.setShortcut(shortcut)
            button.setToolTip(f"{does} ({shortcut})")
            button.setAccessibleDescription(button.toolTip())
            buttons.addWidget(button)
        self.test_button.clicked.connect(lambda: self.build_requested.emit(False))
        self.release_button.clicked.connect(lambda: self.build_requested.emit(True))
        self.cancel_button.clicked.connect(self._request_cancel)
        layout.addLayout(buttons)
        self.progress = QProgressBar(self)
        self.progress.setObjectName("buildProgress")
        layout.addWidget(self.progress)
        self.activity = self._label("buildActivity")
        self.notice = self._label("buildNotice")
        self.last_result = self._label("buildLastResult")
        self.copy_details = CopyDetails("buildCopyDetails", "build error", self)
        layout.addWidget(self.activity)
        layout.addWidget(self.notice)
        layout.addWidget(self.copy_details, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.last_result)
        self.set_state(enabled=False, running=False)

    def _label(self, name: str) -> QLabel:
        label = plain_label(self, name, fill=True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop)
        label.setMaximumHeight(label.fontMetrics().lineSpacing() * 4 + 8)
        label.hide()  # shown with its first text
        return label

    def begin(self, release: bool) -> None:
        """Start presenting a run; planning has no known step count yet."""
        self._cancel_requested = False
        self._present(self.last_result, "")
        self._error = ""  # (an old error's details are only offered with that error)
        self._sync_notice()
        self._steps.clear()
        self._completed.clear()
        self.progress.setRange(0, 0)
        mode = "release" if release else "test"
        self._show_activity(f"Planning {mode} build…")
        self.set_state(enabled=self._enabled, running=True)

    def show_event(self, event: BuildEvent) -> None:
        """Count known terminal steps; only a joined summary may finish the run."""
        if isinstance(event, BuildStarted):
            self._steps = set(event.steps)
            self._completed.clear()
            self.progress.setRange(0, max(1, len(self._steps)))
            self.progress.setFormat(f"%v/{len(self._steps)} steps")
            self.progress.setValue(0)
            self._show_activity("Building…")
        elif isinstance(event, NodeStarted) and event.node_id in self._steps:
            self._show_activity(f"Building step: {event.node_id}")
        elif isinstance(event, (NodeFinished, NodeSkipped, NodeFailed)):
            if event.node_id not in self._steps or event.node_id in self._completed:
                return
            self._completed.add(event.node_id)
            self.progress.setValue(len(self._completed))
            self._show_activity(f"Processed step: {event.node_id}; waiting for build result…")
            if isinstance(event, NodeFailed) and not event.cancelled:
                hint = (
                    f"\nNext: {event.hint}" if event.hint else "\nReview the build log and retry."
                )
                self._error = f"Step {event.node_id} failed: {event.message}{hint}"
                self._details = event.details  # the tool's output: Copy details only
                self._sync_notice()

    def show_summary(self, summary: BuildSummary) -> None:
        """Present the parent's joined result, never infer success from progress."""
        text = f"Build {summary.outcome} in {summary.duration:.2f} s."
        errors = sum(1 for issue in summary.issues if issue.severity == "error")
        if summary.outcome == "succeeded" and errors:  # made, but the game may not load it
            found = f"{errors} error{'s' if errors != 1 else ''}"
            text = (
                f"Build finished in {summary.duration:.2f} s, but the check found {found}: "
                "the track may not load in the game yet. See Issues."
            )
        log = (
            f"Full build log: {summary.log}"
            if summary.log is not None
            else "Build log unavailable."
        )
        self._present(self.last_result, text, f"{text}\n{log}")
        self._present(self.activity, "")

    def show_error(self, error: BaseException) -> None:
        """Retain typed actionable messages; explain unexpected failures and interrupts."""
        reason = str(error) or type(error).__name__
        kind = "failed" if isinstance(error, Exception) else "interrupted"
        own_step = isinstance(error, CTStudioError) and bool(error.hint)  # "Next: …" already
        step = "" if own_step else "\nReview the problem and retry the build."
        self._error = f"Build {kind}: {reason}{step}"
        self._details = details_of(error)
        self._present(self.activity, "")
        self._sync_notice()

    def show_notice(self, text: str) -> None:
        """Keep ancillary warnings independent of transient run activity."""
        self._warning = text
        self._sync_notice()

    def _sync_notice(self) -> None:
        text = "\n".join(part for part in (self._error, self._warning) if part)
        self._present(self.notice, text)
        self.copy_details.offer(text, self._details if self._error else None)

    def clear(self) -> None:
        """Discard the previous project's presentation without touching a controller."""
        self._warning = self._error = ""
        self.copy_details.offer("", None)
        self._cancel_requested = False
        self._steps.clear()
        self._completed.clear()
        for label in (self.activity, self.notice, self.last_result):
            self._present(label, "")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.set_state(enabled=False, running=False)

    def _show_activity(self, text: str) -> None:
        text = "Cancelling…" if self._cancel_requested else text
        self._present(self.activity, text)

    @staticmethod
    def _present(label: QLabel, text: str, details: str | None = None) -> None:
        label.setText(text)
        label.setVisible(bool(text))  # an empty line takes no room in the pinned bar
        complete = text if details is None else details
        label.setToolTip(complete)
        label.setAccessibleDescription(complete)

    def _request_cancel(self) -> None:
        if not self._running or self._cancel_requested:
            return
        self._cancel_requested = True
        self._show_activity("Cancelling…")
        self.set_state(enabled=self._enabled, running=True)
        self.cancel_requested.emit()

    def set_state(self, *, enabled: bool, running: bool) -> None:
        """Use explicit eligibility, not the effective enabled state of ancestors."""
        self._enabled = enabled
        self._running = running
        self.test_button.setEnabled(enabled and not running)
        self.release_button.setEnabled(enabled and not running)
        self.cancel_button.setEnabled(running and not self._cancel_requested)
        self.progress.setVisible(running)
