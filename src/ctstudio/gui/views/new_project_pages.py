"""The new-project wizard's pages (P5-T02a): each checks its own input and says what is wrong.

Folder checks are a single look at one folder (exists, a file, has a project, has anything in it).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

from ctstudio.core.project import manifest_io
from ctstudio.core.project.slots import CATALOGUE, DEFAULT_SLOT, Slot, cups

Choose = Callable[[QWidget, Path], Path | None]  # None: the user cancelled
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{d}{n}" for d in ("COM", "LPT") for n in range(1, 10)}
_WORDS = re.compile(r"[^\W_]+")
_SLOT_ROLE = Qt.ItemDataRole.UserRole


def folder_name(name: str) -> str:
    """The project folder's name for a track name, safe on Windows and Linux ("" if none)."""
    safe = _UNSAFE.sub("_", name.strip()).rstrip(" .")
    if safe.split(".")[0].upper() in _RESERVED:
        safe += "_"
    return safe


def choose_folder(parent: QWidget, start: Path) -> Path | None:
    chosen = QFileDialog.getExistingDirectory(parent, "Where to make the project", str(start))
    return Path(chosen) if chosen else None


def choose_blend(parent: QWidget, start: Path) -> Path | None:
    chosen, _filter = QFileDialog.getOpenFileName(
        parent, "Choose the Blender file", str(start), "Blender files (*.blend)"
    )
    return Path(chosen) if chosen else None


def _problem_label(name: str, parent: QWidget) -> QLabel:
    label = QLabel("", parent)
    label.setObjectName(name)
    label.setWordWrap(True)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


class NamePage(QWizardPage):
    def __init__(self, location: Path, choose: Choose) -> None:
        super().__init__()
        self.setTitle("Name your track")
        self.setSubTitle(
            "The project folder is named after the track. You can rename the track later."
        )
        self._choose = choose
        self.name = QLineEdit(self)
        self.name.setObjectName("trackName")
        self.name.setPlaceholderText("For example: Snowy Peaks")
        self.name.setToolTip("The track's name, as it will appear in CT Studio.")
        self.location = QLineEdit(str(location), self)
        self.location.setObjectName("locationEdit")
        self.location.setToolTip("The folder the project folder is made in.")
        browse = QPushButton("Browse…", self)
        browse.setObjectName("browseLocation")
        browse.setToolTip("Choose the folder to make the project folder in.")
        browse.clicked.connect(self._browse)
        self.preview = QLabel("", self)
        self.preview.setObjectName("folderPreview")
        self.preview.setWordWrap(True)
        self.problem = _problem_label("locationProblem", self)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Track name", self))
        layout.addWidget(self.name)
        layout.addSpacing(12)
        layout.addWidget(QLabel("Make the project folder in", self))
        row = QHBoxLayout()
        row.addWidget(self.location, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        layout.addWidget(self.preview)
        layout.addWidget(self.problem)
        layout.addStretch()
        for edit in (self.name, self.location):
            edit.textChanged.connect(self._changed)
        self._changed()

    def root(self) -> Path | None:
        """The project folder to make, or None when the name or location is not usable."""
        folder, where = folder_name(self.name.text()), self.location.text().strip()
        return Path(where) / folder if folder and where else None

    def isComplete(self) -> bool:
        root = self.root()
        return root is not None and _folder_problem(root) is None

    def _changed(self) -> None:
        root = self.root()
        where = self.location.text().strip()
        self.preview.setText(f"The project folder will be: {root}" if root is not None else "")
        if not where:
            self.problem.setText("Choose where to make the project folder.")
        elif root is None:
            self.problem.setText("")  # no name yet: nothing to say, Next is simply off
        else:
            self.problem.setText(_folder_problem(root) or "")
        self.completeChanged.emit()

    def _browse(self) -> None:
        where = self.location.text().strip()
        chosen = self._choose(self, Path(where) if where else Path.home())
        if chosen is not None:
            self.location.setText(str(chosen))


def _folder_problem(root: Path) -> str | None:
    if not root.is_absolute():
        return "Give the full path of a folder (for example, starting with a drive letter or /)."
    if root.is_file():
        return "There is a file with that name there. Choose another name or location."
    if (root / manifest_io.FILE_NAME).exists():
        return "That folder already has a CT Studio project. Open it, or choose another name."
    if root.is_dir() and any(root.iterdir()):
        return "That folder already has files in it. Choose another name or location."
    return None


class BlendPage(QWizardPage):
    def __init__(self, choose: Choose, start: Callable[[], Path]) -> None:
        super().__init__()
        self.setTitle("Blender file (optional)")
        self.setSubTitle(
            "The .blend file the track is made from. You can leave this empty and add it later."
        )
        self._choose, self._start = choose, start
        self.blend = QLineEdit(self)
        self.blend.setObjectName("blendEdit")
        self.blend.setPlaceholderText("No Blender file yet")
        self.blend.setToolTip("The full path of the track's .blend file.")
        browse = QPushButton("Choose…", self)
        browse.setObjectName("browseBlend")
        browse.setToolTip("Choose the track's .blend file.")
        browse.clicked.connect(self._browse)
        clear = QPushButton("Clear", self)
        clear.setObjectName("clearBlend")
        clear.setToolTip("Go on without a Blender file.")
        clear.clicked.connect(self.blend.clear)
        self.problem = _problem_label("blendProblem", self)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(self.blend, 1)
        row.addWidget(browse)
        row.addWidget(clear)
        layout.addLayout(row)
        layout.addWidget(self.problem)
        layout.addStretch()
        self.blend.textChanged.connect(self._changed)

    def chosen(self) -> Path | None:
        text = self.blend.text().strip()
        return Path(text) if text else None

    def isComplete(self) -> bool:
        return _blend_problem(self.chosen()) is None

    def _changed(self) -> None:
        self.problem.setText(_blend_problem(self.chosen()) or "")
        self.completeChanged.emit()

    def _browse(self) -> None:
        current = self.chosen()
        picked = self._choose(self, current.parent if current is not None else self._start())
        if picked is not None:
            self.blend.setText(str(picked))


def _blend_problem(blend: Path | None) -> str | None:
    if blend is None:
        return None
    if blend.suffix.lower() != ".blend":
        return f"{blend.name} is not a .blend file."
    if not blend.is_file():
        return f"{blend} was not found."
    return None


class SlotPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Track to replace")
        self.setSubTitle(
            "Your track takes the place of one original track or arena. You can change this later."
        )
        self.search = QLineEdit(self)
        self.search.setObjectName("slotSearch")
        self.search.setPlaceholderText("Search by name, abbreviation or cup")
        self.search.setToolTip("Type part of a track's name, its abbreviation (LC) or its cup.")
        self.search.setClearButtonEnabled(True)
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("slotTree")
        self.tree.setHeaderHidden(True)
        self.tree.setToolTip("The original tracks and arenas, by cup.")
        self.problem = _problem_label("slotProblem", self)
        self._words: dict[str, set[str]] = {}
        for cup, members in cups().items():
            group = QTreeWidgetItem(self.tree, [cup])
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for slot in members:
                item = QTreeWidgetItem(group, [f"{slot.name} ({slot.abbr})"])
                item.setData(0, _SLOT_ROLE, slot.file)
                self._words[slot.file] = _slot_words(slot)
        self.tree.expandAll()
        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.problem)
        self.search.textChanged.connect(self._filter)
        self.tree.currentItemChanged.connect(lambda *_: self.completeChanged.emit())
        self._select(DEFAULT_SLOT)

    def chosen(self) -> Slot | None:
        item = self.tree.currentItem()
        file = item.data(0, _SLOT_ROLE) if item is not None else None  # never a hidden row
        return next((slot for slot in CATALOGUE if slot.file == file), None)

    def isComplete(self) -> bool:
        return self.chosen() is not None

    def _select(self, file: str) -> None:
        for item in self._slot_items():
            if item.data(0, _SLOT_ROLE) == file:
                self.tree.setCurrentItem(item)

    def _slot_items(self) -> list[QTreeWidgetItem]:
        items: list[QTreeWidgetItem] = []
        for cup in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(cup)
            if group is not None:
                items += [c for r in range(group.childCount()) if (c := group.child(r)) is not None]
        return items

    def _filter(self, text: str) -> None:
        wanted = [word.casefold() for word in _WORDS.findall(text)]
        shown = [item for item in self._slot_items() if self._show(item, wanted)]
        groups = {id(item.parent()) for item in shown}
        for cup in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(cup)
            if group is not None:
                group.setHidden(id(group) not in groups)
        self._keep_choice(shown)
        self.problem.setText(
            "" if shown else f"No original track or arena matches “{text.strip()}”."
        )
        self.completeChanged.emit()

    def _show(self, item: QTreeWidgetItem, wanted: list[str]) -> bool:
        """Show ``item`` when every searched word starts one of its words."""
        words = self._words[item.data(0, _SLOT_ROLE)]
        hit = all(any(word.startswith(part) for word in words) for part in wanted)
        item.setHidden(not hit)
        return hit

    def _keep_choice(self, shown: list[QTreeWidgetItem]) -> None:
        """Keep the chosen track if it is still shown, else choose the first shown (or none)."""
        if not shown:
            self.tree.setCurrentIndex(QModelIndex())
        elif self.tree.currentItem() not in shown:
            self.tree.setCurrentItem(shown[0])


def _slot_words(slot: Slot) -> set[str]:
    text = " ".join((slot.name, slot.abbr, slot.cup, slot.file))
    return {word.casefold() for word in _WORDS.findall(text)}


class SummaryPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Ready to make the project")
        self.setSubTitle("Check the details, then choose Finish.")
        self.text = QLabel("", self)
        self.text.setObjectName("summaryText")
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.busy = QProgressBar(self)
        self.busy.setObjectName("createBusy")
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.setToolTip("Making the project folder…")
        self.busy.hide()
        self.problem = _problem_label("createProblem", self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        layout.addSpacing(12)
        layout.addWidget(self.busy)
        layout.addWidget(self.problem)
        layout.addStretch()
