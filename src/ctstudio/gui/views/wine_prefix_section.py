"""Settings → Editors… → Wine (Linux) (P5-T07f3): the Wine-prefix folder of each Windows
editor, built-in (those with a prefix recipe) or the user's own ``.exe`` programs.

On Linux CT Studio runs a Windows editor through Wine in the prefix folder chosen here; on
Windows the choices are kept but not used, and the tab says so. The tab only shows and asks:
Choose folder… opens a folder dialog and Clear asks for no prefix, both through ``chosen``;
the page saves on its worker and shows the result again with ``show_rows``.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.tools.editors import PREFIX_RECIPES
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.spec import CustomTool
from ctstudio.gui.views.editors_parts import EnterList

_ID = Qt.ItemDataRole.UserRole
_INTRO = (
    "On Linux, CT Studio opens these Windows e&ditors through Wine, each in a prefix folder "
    "you choose here. Windows does not use these folders."
)
_OWN_RECIPE = "WINEPREFIX=<folder> wineboot -u"
NO_PREFIX = "no prefix chosen"


class WinePrefixSection(QWidget):
    chosen = Signal(str, object)  # an editor id and its new prefix folder, or None to clear

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("winePrefixSection")
        self.folder_dialog: QFileDialog | None = None  # the open folder dialog
        self._names: dict[str, str] = {}
        self._recipes: dict[str, str] = {}
        self._prefixes: Mapping[str, Path] = {}
        layout = QVBoxLayout(self)
        self.intro = QLabel(_INTRO, self)  # also the rows' heading (its mnemonic)
        self.intro.setWordWrap(True)
        layout.addWidget(self.intro)
        self.rows = EnterList(self)
        self.rows.setObjectName("winePrefixes")
        self.rows.setMinimumHeight(self.fontMetrics().lineSpacing() * 4)
        # Long prefix paths are shortened in the middle; the full row shows on hover.
        self.rows.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.rows.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows.itemActivated.connect(self._activated)
        self.rows.itemSelectionChanged.connect(self._render_buttons)
        self.intro.setBuddy(self.rows)
        layout.addWidget(self.rows)
        self.how = QLabel(self)  # how to make a prefix for the selected editor
        self.how.setObjectName("wineHow")
        self.how.setWordWrap(True)
        self.how.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.how)
        row = QHBoxLayout()
        self.choose_button = QPushButton("Choose &folder…", self)
        self.choose_button.clicked.connect(self.choose)
        self.clear_button = QPushButton("C&lear", self)
        self.clear_button.clicked.connect(self.clear)
        for button in (self.choose_button, self.clear_button):
            button.setAutoDefault(False)  # Enter elsewhere in the window must not press them
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    def show_rows(
        self, prefixes: Mapping[str, Path], custom: Mapping[str, CustomTool], editable: bool
    ) -> None:
        """List the built-in Windows editors, then the user's own ``.exe`` programs, each
        with its saved prefix; the selection is kept by id."""
        kept = self.selected()
        self._names = {tool_id: TOOL_BY_ID[tool_id].name for tool_id in PREFIX_RECIPES}
        self._recipes = dict(PREFIX_RECIPES)
        for tool_id, tool in custom.items():
            if tool.exe.suffix.lower() == ".exe":
                self._names[tool_id], self._recipes[tool_id] = tool.name, _OWN_RECIPE
        self._prefixes = prefixes
        self.rows.clear()
        for tool_id, name in self._names.items():
            item = QListWidgetItem(f"{name}: {prefixes.get(tool_id, NO_PREFIX)}", self.rows)
            item.setToolTip(item.text())
            item.setData(_ID, tool_id)
            if tool_id == kept:
                self.rows.setCurrentItem(item)
        self.rows.setEnabled(editable)
        self._render_buttons()

    def selected(self) -> str | None:
        items = self.rows.selectedItems()
        return str(items[0].data(_ID)) if items else None

    def name_of(self, editor_id: str) -> str:
        return self._names.get(editor_id, editor_id)

    def _activated(self, _item: QListWidgetItem) -> None:
        self.choose()  # Enter or a double-click chooses the selected editor's folder

    def choose(self) -> None:
        editor_id = self.selected()
        if editor_id is None:
            return
        start = str(self._prefixes.get(editor_id, ""))
        title = f"Choose the Wine prefix folder for {self.name_of(editor_id)}"
        dialog = QFileDialog(self, title, start)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly)
        dialog.fileSelected.connect(partial(self._picked, editor_id))
        dialog.finished.connect(self._closed)
        self.folder_dialog = dialog
        dialog.open()

    def _picked(self, editor_id: str, folder: str) -> None:
        self.chosen.emit(editor_id, Path(folder))

    def _closed(self, _result: int) -> None:
        dialog, self.folder_dialog = self.folder_dialog, None
        if dialog is not None:
            dialog.deleteLater()

    def clear(self) -> None:
        editor_id = self.selected()
        if editor_id is not None:
            self.chosen.emit(editor_id, None)

    def _render_buttons(self) -> None:
        chosen = self.selected() if self.rows.isEnabled() else None
        self.choose_button.setEnabled(chosen is not None)
        self.clear_button.setEnabled(chosen in self._prefixes)
        self.how.setText(f"To make one: {self._recipes[chosen]}" if chosen else "")
