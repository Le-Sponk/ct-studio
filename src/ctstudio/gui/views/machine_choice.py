"""One machine setting chosen in a list and saved at once (P5-T08c, shared since P5-T08d).

Settings → Build → This computer (build steps at once) and Settings → Appearance (colour
scheme) each show one choice of a setting in ``settings.json``, the same for every project.
A pick is saved at once on the section's worker through a fresh read; the subclass's service
writes nothing when the file already says so. A damaged or newer file is shown and never
overwritten: the choice, its label and the intro are hidden until a reread finds the file
usable (every save also re-reads and refuses it), so the reason gets the room on a short
screen. After a keyboard pick the keyboard goes back to the choice.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QComboBox, QLabel, QProgressBar, QVBoxLayout, QWidget

from ctstudio.core.project.settings import SettingsError
from ctstudio.gui.views.wrap_text import breakable

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChoiceTexts:
    """What a section shows. ``name`` starts every object name (``<name>Section``, the
    choice ``<name>``, ``<name>Problem``, ``<name>Note``, ``<name>Busy``); ``subject`` ends
    "Could not save …" (for example "the build steps setting")."""

    name: str
    intro: str
    label: str
    tooltip: str
    subject: str


@dataclass(frozen=True)
class _Result:
    value: object
    saved: bool


class _Relay(QObject):
    done = Signal(object)


class MachineChoiceSection(QWidget):
    """The shared section; a subclass reads and saves through its service (``_load``,
    ``_save``) and words the note after a save (``_saved``)."""

    # The choice had the keyboard but is hidden now (the file became unusable): the owner
    # gives it to something useful, or it stays on Close, which Enter or Space would press.
    keyboard_lost = Signal()

    def __init__(
        self,
        texts: ChoiceTexts,
        choices: Sequence[tuple[str, object]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(f"{texts.name}Section")
        self.pool = QThreadPool(self)  # first child: deleted (and waited for) first
        self._texts = texts
        self._relay = _Relay(self)
        self._relay.done.connect(self._finished)
        self._running = False
        self._value: object = None
        self._read = False  # a usable file has been read
        self._locked = False  # the file cannot be used: the choice is hidden
        self._focus = False  # the choice had the keyboard when a save began
        self._saving = False  # the running work is a save, not a read
        self._build(choices)
        self._render()

    def _build(self, choices: Sequence[tuple[str, object]]) -> None:
        layout = QVBoxLayout(self)
        self.intro = QLabel(self._texts.intro, self)
        self.intro.setWordWrap(True)
        layout.addWidget(self.intro)
        self.label = QLabel(self._texts.label, self)  # above its choice: narrow
        layout.addWidget(self.label)
        self.combo = QComboBox(self)
        self.combo.setObjectName(self._texts.name)
        for text, value in choices:
            self.combo.addItem(text, value)
        self.combo.setToolTip(self._texts.tooltip)
        self.combo.activated.connect(self._picked)
        self.label.setBuddy(self.combo)
        layout.addWidget(self.combo)
        self.banner = self._text(f"{self._texts.name}Problem", layout)
        self.note = self._text(f"{self._texts.name}Note", layout)
        self.busy_bar = QProgressBar(self)
        self.busy_bar.setObjectName(f"{self._texts.name}Busy")
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setMaximumHeight(6)
        layout.addWidget(self.busy_bar)
        layout.addStretch()

    def _text(self, name: str, layout: QVBoxLayout) -> QLabel:
        label = QLabel(self)
        label.setObjectName(name)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        return label

    def _load(self) -> Callable[[], object]:
        """The read to run on the worker (taken on the GUI thread)."""
        raise NotImplementedError

    def _save(self, value: object) -> Callable[[], object]:
        """The save of ``value`` to run on the worker; it returns the value saved."""
        raise NotImplementedError

    def _saved(self, value: object) -> str:
        """The note after ``value`` was saved (on the GUI thread)."""
        raise NotImplementedError

    def _offer(self, value: object) -> None:
        """Make ``value`` choosable (a saved value may be outside the usual list)."""

    @property
    def busy(self) -> bool:
        return self._running

    def reload(self) -> None:
        """Read the setting again (not while a read or save runs)."""
        if not self._running:
            load = self._load()
            self._start(lambda: _Result(load(), saved=False))

    def _picked(self, index: int) -> None:
        if self._running or not self._read:
            return  # past Qt's own disabling: nothing is saved now
        save = self._save(self.combo.itemData(index))
        self._focus = self.combo.hasFocus()
        self._start(lambda: _Result(save(), saved=True), saving=True)

    def _start(self, work: Callable[[], _Result], *, saving: bool = False) -> None:
        relay, subject = self._relay, self._texts.subject

        def job() -> None:
            try:
                payload: object = work()
            except Exception as exc:  # any failure must reach the section, not die here
                _LOG.exception("Reading or saving %s failed", subject)
                payload = exc
            relay.done.emit(payload)

        self._running, self._saving = True, saving
        self.note.clear()
        self._render()
        self.pool.start(job)

    def _finished(self, payload: object) -> None:
        self._running = False
        if isinstance(payload, _Result):
            self._value, self._read, self._locked = payload.value, True, False
            self._problem("")
            if payload.saved:
                self.note.setText(self._saved(payload.value))
        elif isinstance(payload, SettingsError):
            self._locked = True
            self._problem(str(payload))
        elif isinstance(payload, Exception):
            reason = str(payload) or type(payload).__name__
            action = "save" if self._saving else "read"
            self._problem(f"Could not {action} {self._texts.subject}. {reason}")
        self._render()
        self._return_keyboard()

    def _return_keyboard(self) -> None:
        """Give the keyboard back after a pick: turning the choice off moved it on."""
        if self._focus and self.combo.isEnabled() and self.combo.isVisible():
            self.combo.setFocus()
        elif self._focus and self.isVisible():  # the choice is hidden: file unusable
            self.keyboard_lost.emit()
        self._focus = False

    def _problem(self, text: str) -> None:
        self.banner.setText(breakable(text))
        self.banner.setHidden(not text)

    def _render(self) -> None:
        self._offer(self._value)
        self.combo.setCurrentIndex(self.combo.findData(self._value))
        self.combo.setEnabled(not self._running and self._read)  # hidden when locked
        # Locked: only the reason is shown; it may be long, and the screen only 600 px tall.
        self.intro.setHidden(self._locked)
        self.label.setHidden(self._locked)
        self.combo.setHidden(self._locked)
        self.busy_bar.setVisible(self._running)
