"""Settings → Editors… (P5-T07f1): which built-in editor Open in… lists first per file kind.

One choice per kind with more than one built-in editor: "Default order" or one editor. A
pick is saved at once on a worker (``EditorPreferencesService``) behind a busy bar, with the
choices off meanwhile; Open in… reads the file each time, so it applies without a restart.
A damaged or newer settings file is shown in a banner and the choices stay off, so it is
never overwritten; any other failure is shown and the choice goes back to what is saved.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial

from PySide6.QtCore import QObject, QThreadPool, Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from ctstudio.core.project.editor_preferences import DEFAULT_EDITORS
from ctstudio.core.project.settings import SettingsError
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.gui.editor_settings import KIND_LABELS, KINDS, EditorKinds, EditorPreferencesService

_LOG = logging.getLogger(__name__)
_INTRO = (
    "Choose which editor Open in… lists first for each kind of file. Changes apply the "
    "next time you choose Open in…."
)


class _Relay(QObject):
    """Carries a worker's result back to the UI thread (a queued signal)."""

    done = Signal(object)


@dataclass(frozen=True)
class _Saved:
    kinds: EditorKinds
    kind: str
    tool: str | None


def _note(saved: _Saved) -> str:
    if saved.tool is None:
        return f"Saved. Open in… now uses the default order for {saved.kind} files."
    return f"Saved. Open in… now lists {TOOL_BY_ID[saved.tool].name} first for {saved.kind} files."


def _error_text(error: Exception) -> str:
    return str(error) or type(error).__name__


def _breakable(text: str) -> str:
    """Let a Windows path wrap after each backslash (a zero-width space): a word-wrapped label
    cannot break after a backslash, so the path would widen the window past the screen.
    Qt already breaks after "/" (tested with a long Linux-style path)."""
    return text.replace("\\", "\\\u200b")


class EditorsPage(QWidget):
    shown = Signal()  # a read or save finished and is shown

    def __init__(self, service: EditorPreferencesService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.pool = QThreadPool(self)  # first child: deleted (and waited for) first
        self._relay = _Relay(self)
        self._relay.done.connect(self._finished)
        self._running = False
        self._choices: Mapping[str, str | None] | None = None  # None until first read
        self._locked = False  # the file cannot be used: choices stay off (a save refuses it too)
        self.combos: dict[str, QComboBox] = {}
        self._build()
        self.reload()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(_INTRO, self)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.banner = QLabel(self)
        self.banner.setObjectName("editorsProblem")
        self.banner.setWordWrap(True)
        self.banner.setFrameShape(QLabel.Shape.StyledPanel)
        self.banner.hide()
        layout.addWidget(self.banner)
        self.busy_bar = QProgressBar(self)
        self.busy_bar.setObjectName("editorsBusy")
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setMaximumHeight(6)
        self.busy_bar.hide()
        layout.addWidget(self.busy_bar)
        form = QFormLayout()
        form.setObjectName("editorsForm")
        # Labels above their choices: the same at every font size, and never wider than the screen.
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        for kind in KINDS:
            form.addRow(f"{KIND_LABELS[kind]}:", self._combo(kind))
        layout.addLayout(form)
        self.note = QLabel(self)
        self.note.setObjectName("editorsNote")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch(1)

    def _combo(self, kind: str) -> QComboBox:
        box = QComboBox(self)
        box.setObjectName(f"editorChoice{kind}")
        tools = DEFAULT_EDITORS[kind]
        box.addItem(f"Default order ({TOOL_BY_ID[tools[0]].name} first)")
        for tool in tools:
            box.addItem(TOOL_BY_ID[tool].name)
        box.activated.connect(partial(self._picked, kind))
        self.combos[kind] = box
        return box

    @property
    def busy(self) -> bool:
        return self._running

    def reload(self) -> None:
        """Read the saved choices again (not while a read or save runs)."""
        if not self._running:
            self._start(self.service.load)

    def _picked(self, kind: str, index: int) -> None:
        # A damaged file needs no check here: the save reads it again and refuses it.
        if self._running or self._choices is None:
            return  # past Qt's own disabling: nothing is saved now
        tool = (None, *DEFAULT_EDITORS[kind])[index]
        service = self.service

        def save() -> _Saved:
            return _Saved(service.save(kind, tool), kind, tool)

        self._start(save)

    def _start(self, work: Callable[[], object]) -> None:
        relay = self._relay

        def job() -> None:
            try:
                payload: object = work()
            except Exception as exc:  # any failure must reach the page, not die here
                _LOG.exception("Reading or saving editor choices failed")
                payload = exc
            relay.done.emit(payload)

        self._running = True
        self._render()
        self.pool.start(job)

    def _finished(self, payload: object) -> None:
        self._running = False
        self.note.setText("")
        if isinstance(payload, _Saved):
            self._choices = payload.kinds.choices
            self.note.setText(_note(payload))
            self._problem(None)
        elif isinstance(payload, EditorKinds):
            self._choices, self._locked = payload.choices, False
            self._problem(None)
        elif isinstance(payload, SettingsError):
            self._locked = True
            self._problem(str(payload))
        elif isinstance(payload, Exception):
            self._problem(f"Could not read or save the editor choices: {_error_text(payload)}")
        self._render()
        self.shown.emit()

    def _problem(self, text: str | None) -> None:
        self.banner.setText(_breakable(text or ""))
        self.banner.setVisible(bool(text))

    def _render(self) -> None:
        """Show the saved choices; the choices are on only when idle and the file is usable."""
        choices = self._choices or {}
        editable = not self._running and not self._locked and self._choices is not None
        for kind, box in self.combos.items():
            box.setCurrentIndex((None, *DEFAULT_EDITORS[kind]).index(choices.get(kind)))
            box.setEnabled(editable)
        self.busy_bar.setVisible(self._running)
