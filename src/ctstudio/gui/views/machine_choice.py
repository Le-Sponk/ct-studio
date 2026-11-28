"""Machine settings chosen in lists and saved at once (P5-T08c; shared since P5-T08d; several
choices in one section since P5-T08e2).

Settings → Build → This computer (build steps at once), Settings → Appearance (colour
scheme) and Settings → Advanced → This computer (tool commands, build logs kept) show
choices of settings in ``settings.json``, the same for every project. One section reads all
its choices together; a pick saves that one choice at once on the section's worker through a
fresh read, and the subclass's service writes nothing when the file already says so. A
damaged or newer file is shown once and never overwritten: every choice, its label and the
intro are hidden until a reread finds the file usable (every save also re-reads and refuses
it), so the reason gets the room on a short screen. After a keyboard pick the keyboard goes
back to that choice.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial

from PySide6.QtCore import QObject, QThreadPool, Signal
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from ctstudio.core.project.settings import SettingsError
from ctstudio.gui.views.plain import busy_bar, plain_label
from ctstudio.gui.views.wrap_text import breakable

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChoiceTexts:
    """What a section shows. ``name`` starts every object name (``<name>Section``, the first
    choice ``<name>``, ``<name>Problem``, ``<name>Note``, ``<name>Busy``); ``label`` and
    ``tooltip`` belong to the first choice; ``subject`` ends "Could not save …" (for example
    "the build steps setting")."""

    name: str
    intro: str
    label: str
    tooltip: str
    subject: str


@dataclass(frozen=True)
class ChoiceRow:
    """A further choice in the same section; ``name`` is its object name and its key."""

    name: str
    label: str
    tooltip: str
    choices: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class _Result:
    values: Mapping[str, object]
    saved: str | None  # the choice saved, None for a read


class _Relay(QObject):
    done = Signal(object)


class MachineChoiceSection(QWidget):
    """The shared section; a subclass reads all its choices (``_load``), saves one
    (``_save``) and words the note after a save (``_saved``)."""

    # A choice had the keyboard but is hidden now (the file became unusable): the owner
    # gives it to something useful, or it stays on Close, which Enter or Space would press.
    keyboard_lost = Signal()

    def __init__(
        self,
        texts: ChoiceTexts,
        choices: Sequence[tuple[str, object]],
        parent: QWidget | None = None,
        *,
        more: Sequence[ChoiceRow] = (),
    ) -> None:
        super().__init__(parent)
        self.setObjectName(f"{texts.name}Section")
        self.pool = QThreadPool(self)  # first child: deleted (and waited for) first
        self._texts = texts
        self._relay = _Relay(self)
        self._relay.done.connect(self._finished)
        self._running = False
        self._values: dict[str, object] = {}
        self._read = False  # a usable file has been read
        self._locked = False  # the file cannot be used: the choices are hidden
        self._focus: QComboBox | None = None  # the choice that had the keyboard at a pick
        self._saving = False  # the running work is a save, not a read
        first = ChoiceRow(texts.name, texts.label, texts.tooltip, tuple(choices))
        self._build((first, *more))
        self._render()

    def _build(self, rows: Sequence[ChoiceRow]) -> None:
        layout = QVBoxLayout(self)
        self.intro = QLabel(self._texts.intro, self)
        self.intro.setWordWrap(True)
        layout.addWidget(self.intro)
        self.rows: dict[str, tuple[QLabel, QComboBox]] = {}
        for row in rows:
            label = QLabel(row.label, self)  # above its choice: narrow
            layout.addWidget(label)
            combo = QComboBox(self)
            combo.setObjectName(row.name)
            for text, value in row.choices:
                combo.addItem(text, value)
            combo.setToolTip(row.tooltip)
            combo.activated.connect(partial(self._picked, row.name))
            label.setBuddy(combo)
            layout.addWidget(combo)
            self.rows[row.name] = (label, combo)
        self.label, self.combo = self.rows[self._texts.name]
        self.banner = self._text(f"{self._texts.name}Problem", layout)
        self.note = self._text(f"{self._texts.name}Note", layout)
        self.busy_bar = busy_bar(self, f"{self._texts.name}Busy", slim=True)
        layout.addWidget(self.busy_bar)
        layout.addStretch()

    def _text(self, name: str, layout: QVBoxLayout) -> QLabel:
        label = plain_label(self, name)
        layout.addWidget(label)
        return label

    def _load(self) -> Callable[[], Mapping[str, object]]:
        """The read of every choice (by name) to run on the worker (taken on the GUI thread)."""
        raise NotImplementedError

    def _save(self, name: str, value: object) -> Callable[[], object]:
        """The save of choice ``name`` to run on the worker; it returns the value saved."""
        raise NotImplementedError

    def _saved(self, name: str, value: object) -> str:
        """The note after choice ``name`` was saved as ``value`` (on the GUI thread)."""
        raise NotImplementedError

    def _offer(self, name: str, value: object) -> None:
        """Make ``value`` choosable in ``name`` (a saved value may be outside the list)."""

    @property
    def busy(self) -> bool:
        return self._running

    def reload(self) -> None:
        """Read the settings again (not while a read or save runs)."""
        if not self._running:
            load = self._load()
            self._start(lambda: _Result(load(), saved=None))

    def _picked(self, name: str, index: int) -> None:
        if self._running or not self._read:
            return  # past Qt's own disabling: nothing is saved now
        combo = self.rows[name][1]
        save = self._save(name, combo.itemData(index))
        self._focus = combo if combo.hasFocus() else None
        self._start(lambda: _Result({name: save()}, saved=name), saving=True)

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
            self._values.update(payload.values)
            self._read, self._locked = True, False
            self._problem("")
            if payload.saved is not None:
                self.note.setText(self._saved(payload.saved, payload.values[payload.saved]))
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
        """Give the keyboard back after a pick: turning the choices off moved it on."""
        combo = self._focus
        if combo is not None and combo.isEnabled() and combo.isVisible():
            combo.setFocus()
        elif combo is not None and self.isVisible():  # the choice is hidden: file unusable
            self.keyboard_lost.emit()
        self._focus = None

    def _problem(self, text: str) -> None:
        self.banner.setText(breakable(text))
        self.banner.setHidden(not text)

    def _render(self) -> None:
        # Locked: only the reason is shown; it may be long, and the screen only 600 px tall.
        self.intro.setHidden(self._locked)
        for name, (label, combo) in self.rows.items():
            value = self._values.get(name)
            self._offer(name, value)
            combo.setCurrentIndex(combo.findData(value))
            combo.setEnabled(not self._running and self._read)  # hidden when locked
            label.setHidden(self._locked)
            combo.setHidden(self._locked)
        self.busy_bar.setVisible(self._running)
