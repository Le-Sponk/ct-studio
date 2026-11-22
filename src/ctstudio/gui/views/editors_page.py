"""Settings → Editors…: which built-in editor Open in… lists first per file kind (P5-T07f1),
the user's own editor programs (P5-T07f2) and each Windows editor's Wine prefix (P5-T07f3).

Three tabs keep the window inside a small screen. "Order": one choice per kind with more
than one built-in editor ("Default order" or one editor). "Your editors": a list
with Add…, Edit… and Remove (a checked entry dialog; a removal asks first). "Wine (Linux)":
``WinePrefixSection``. Every change is saved at once on a worker
(``EditorPreferencesService``) behind a busy bar, with every control off meanwhile; Open in…
reads the file each time, so it applies without a restart. A damaged or newer settings file
is shown in a banner and the tabs are hidden, so it is never overwritten; any other failure
is shown and the window goes back to what is saved.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.project.editor_preferences import DEFAULT_EDITORS
from ctstudio.core.project.settings import SettingsError
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.spec import CustomTool
from ctstudio.gui.editor_settings import KIND_LABELS, KINDS, EditorKinds, EditorPreferencesService
from ctstudio.gui.views.custom_tool_dialog import CustomToolDialog
from ctstudio.gui.views.editors_parts import (
    EnterList,
    breakable,
    choice_note,
    custom_note,
    error_text,
)
from ctstudio.gui.views.wine_prefix_section import WinePrefixSection

_LOG = logging.getLogger(__name__)
_ID = Qt.ItemDataRole.UserRole
_INTRO = (
    "Choose which editor Open in… lists first for each kind of file. Changes apply the "
    "next time you choose Open in…."
)


class _Relay(QObject):
    """Carries a worker's result back to the UI thread (a queued signal)."""

    done = Signal(object)


_OWN = "Your own editors (Open in… offers them for every file):"


@dataclass(frozen=True)
class _Saved:
    kinds: EditorKinds
    note: str
    added: CustomTool | None = None  # the editor this save added, to select it


class EditorsPage(QWidget):
    def __init__(self, service: EditorPreferencesService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.pool = QThreadPool(self)  # first child: deleted (and waited for) first
        self._relay = _Relay(self)
        self._relay.done.connect(self._finished)
        self._running = False
        self._choices: Mapping[str, str | None] | None = None  # None until first read
        self._custom: Mapping[str, CustomTool] = {}
        self._prefixes: Mapping[str, Path] = {}
        self.tool_dialog: CustomToolDialog | None = None  # the open add/edit dialog
        self.question: QMessageBox | None = None  # the open "remove?" question
        self._locked = False  # the file cannot be used: controls hidden (a save refuses it too)
        self._focus: QWidget | None = None  # had the keyboard focus when a read or save began
        self._kept: str | None = None  # the editor to select when the list is shown again
        self.combos: dict[str, QComboBox] = {}
        self._build()
        self.reload()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
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
        # The tabs are hidden while the file cannot be used: they could do nothing then, and
        # the damaged-file banner keeps the room on a small screen.
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("editorsTabs")
        self.choices_section = QWidget(self.tabs)
        self.choices_section.setObjectName("editorChoicesSection")
        form = QFormLayout(self.choices_section)
        form.setObjectName("editorsForm")
        # Labels above their choices: the same at every font size, and never wider than the screen.
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        intro = QLabel(_INTRO, self.choices_section)  # this tab's own: the others explain theirs
        intro.setWordWrap(True)
        form.addRow(intro)
        for kind in KINDS:
            form.addRow(f"{KIND_LABELS[kind]}:", self._combo(kind))
        self.tabs.addTab(self.choices_section, "&Order")
        self._build_own()
        self.tabs.addTab(self.own_section, "&Your editors")
        self.wine = WinePrefixSection(self.tabs)
        self.wine.chosen.connect(self._prefix_picked)
        self.tabs.addTab(self.wine, "&Wine (Linux)")
        layout.addWidget(self.tabs)
        self.note = QLabel(self)
        self.note.setObjectName("editorsNote")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch(1)

    def _build_own(self) -> None:
        self.own_section = QWidget(self.tabs)
        self.own_section.setObjectName("customEditorsSection")
        section = QVBoxLayout(self.own_section)
        heading = QLabel(_OWN, self.own_section)
        heading.setWordWrap(True)
        section.addWidget(heading)
        self.own = EnterList(self.own_section)
        self.own.setObjectName("customEditors")
        self.own.setMinimumHeight(self.fontMetrics().lineSpacing() * 4)
        # Long program paths are shortened in the middle; the full row shows on hover.
        self.own.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.own.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.own.itemActivated.connect(self._activated)
        self.own.itemSelectionChanged.connect(self._render_buttons)
        heading.setBuddy(self.own)
        section.addWidget(self.own)
        row = QHBoxLayout()
        self.add_button = QPushButton("&Add…", self.own_section)
        self.add_button.clicked.connect(self.add_tool)
        self.edit_button = QPushButton("&Edit…", self.own_section)
        self.edit_button.clicked.connect(self.edit_tool)
        self.remove_button = QPushButton("&Remove", self.own_section)
        self.remove_button.clicked.connect(self.remove_tool)
        for button in (self.add_button, self.edit_button, self.remove_button):
            button.setAutoDefault(False)  # Enter elsewhere in the window must not press them
            row.addWidget(button)
        row.addStretch(1)
        section.addLayout(row)

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

    def _idle(self) -> bool:
        # A damaged file needs no check here: every save reads it again and refuses it.
        return not self._running and self._choices is not None

    def _picked(self, kind: str, index: int) -> None:
        if not self._idle():
            return  # past Qt's own disabling: nothing is saved now
        tool = (None, *DEFAULT_EDITORS[kind])[index]
        self._save(lambda service: service.save(kind, tool), choice_note(kind, tool))

    def selected_tool(self) -> str | None:
        items = self.own.selectedItems()
        return str(items[0].data(_ID)) if items else None

    def _activated(self, _item: QListWidgetItem) -> None:
        self.edit_tool()  # Enter or a double-click edits the selected editor

    def add_tool(self) -> None:
        if self._idle() and self.tool_dialog is None:
            self._open_tool(None)

    def edit_tool(self) -> None:
        tool_id = self.selected_tool()
        if self._idle() and self.tool_dialog is None and tool_id in self._custom:
            self._open_tool(tool_id)

    def _open_tool(self, tool_id: str | None) -> None:
        old = None if tool_id is None else self._custom[tool_id]
        dialog = CustomToolDialog(old, parent=self)
        self.tool_dialog = dialog

        def chosen(new: CustomTool) -> None:
            if self._idle():  # a read started meanwhile (not from the UI): save nothing
                note = custom_note(old, new)
                added = new if tool_id is None else None
                self._save(lambda service: service.save_custom(tool_id, new), note, added)

        def done(_result: int) -> None:
            self.tool_dialog = None
            dialog.deleteLater()

        dialog.chosen.connect(chosen)
        dialog.finished.connect(done)
        dialog.open()

    def _prefix_picked(self, editor_id: str, prefix: Path | None) -> None:
        if not self._idle():
            return  # past Qt's own disabling: nothing is saved now
        name = self.wine.name_of(editor_id)
        note = f"Cleared the Wine prefix of {name}."
        if prefix is not None:
            note = f"Saved. On Linux, {name} now runs in the prefix {prefix}."
        self._save(lambda service: service.save_prefix(editor_id, prefix, name=name), note)

    def remove_tool(self) -> None:
        tool_id = self.selected_tool()
        if tool_id is None or not self._idle() or self.question is not None:
            return
        old = self._custom.get(tool_id)
        if old is None:
            return
        yes, cancel = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Cancel
        text = f"Remove {old.name} from Open in…? The program itself is not touched."
        question = QMessageBox(QMessageBox.Icon.Question, "Remove editor", text, yes | cancel, self)
        question.setDefaultButton(cancel)
        self.question = question

        def done(_result: int) -> None:
            self.question = None
            question.deleteLater()
            if question.clickedButton() is question.button(yes) and self._idle():
                note = f"Removed {old.name}. Open in… no longer offers it."
                self._save(lambda service: service.save_custom(tool_id, None), note)

        question.finished.connect(done)
        question.open()

    def _save(
        self,
        change: Callable[[EditorPreferencesService], EditorKinds],
        note: str,
        added: CustomTool | None = None,
    ) -> None:
        service = self.service

        def save() -> _Saved:
            return _Saved(change(service), note, added)

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

        # The window's own focus widget: right even while the add/edit dialog is in front.
        # Qt returns None when nothing in the window has had the focus (the stubs omit it).
        focus = cast("QWidget | None", self.window().focusWidget())
        self._focus = focus if focus is not None and self.isAncestorOf(focus) else None
        self._running = True
        self._render()
        self.pool.start(job)

    def _finished(self, payload: object) -> None:
        self._running = False
        self.note.setText("")
        if isinstance(payload, _Saved):
            before = self._custom
            self._choices, self._custom = payload.kinds.choices, payload.kinds.custom
            self._prefixes = payload.kinds.prefixes
            self.note.setText(payload.note)
            self._problem(None)
            self._select(payload.added, before)
        elif isinstance(payload, EditorKinds):
            self._choices, self._custom, self._locked = payload.choices, payload.custom, False
            self._prefixes = payload.prefixes
            self._problem(None)
        elif isinstance(payload, SettingsError):
            self._locked = True
            self._problem(str(payload))
        elif isinstance(payload, Exception):
            self._problem(f"Could not read or save the editor settings: {error_text(payload)}")
        self._render()
        self._restore_focus()

    def _select(self, added: CustomTool | None, before: Mapping[str, CustomTool]) -> None:
        """Select the editor this save added: the new id holding it. Editors added outside
        the window meanwhile also appear, but are not selected."""
        new = [tool_id for tool_id in self._custom if tool_id not in before]
        mine = sorted(tool_id for tool_id in new if self._custom[tool_id] == added)
        if mine:
            self._kept = mine[0]

    def _restore_focus(self) -> None:
        """Give the focus back to what had it when the read or save began: turning the
        controls off moved it on (often to Close, which the next Space or Enter presses)."""
        focus, self._focus = self._focus, None
        if focus is None:
            return
        if focus.isEnabled() and focus.isVisible():
            focus.setFocus()
        elif self.own.isEnabled() and self.own.isVisible():
            self.own.setFocus()  # it is off now (Remove with nothing selected): use the list

    def _problem(self, text: str | None) -> None:
        self.banner.setText(breakable(text or ""))
        self.banner.setVisible(bool(text))

    def _render(self) -> None:
        """Show the saved choices; the choices are on only when idle and the file is usable."""
        choices = self._choices or {}
        editable = not self._running and not self._locked and self._choices is not None
        for kind, box in self.combos.items():
            box.setCurrentIndex((None, *DEFAULT_EDITORS[kind]).index(choices.get(kind)))
            box.setEnabled(editable)
        self._render_own(editable)
        self.wine.show_rows(self._prefixes, self._custom, editable)
        self.tabs.setVisible(not self._locked)
        self.busy_bar.setVisible(self._running)

    def _render_own(self, editable: bool) -> None:
        """List the saved editors (the selection is kept by id) and turn the buttons on."""
        kept, self._kept = self._kept or self.selected_tool(), None
        self.own.clear()
        for tool_id, tool in self._custom.items():
            item = QListWidgetItem(f"{tool.name} ({tool.exe})", self.own)
            item.setToolTip(item.text())
            item.setData(_ID, tool_id)
            if tool_id == kept:
                self.own.setCurrentItem(item)
        self.own.setEnabled(editable)
        self.add_button.setEnabled(editable)
        self._render_buttons()

    def _render_buttons(self) -> None:
        chosen = self.own.isEnabled() and self.selected_tool() is not None
        self.edit_button.setEnabled(chosen)
        self.remove_button.setEnabled(chosen)
