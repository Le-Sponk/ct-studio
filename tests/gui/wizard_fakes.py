"""Shared pieces of the new-project wizard tests (P5-T02a): a recording creator and finders."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypeVar

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QWizard,
)
from pytestqt.qtbot import QtBot

from ctstudio.core.project.project import Project
from ctstudio.gui.views.new_project import NewProjectWizard

SCREENS = Path(__file__).resolve().parents[2] / "tests" / "artifacts" / "screens"
WAIT = 10_000
W = TypeVar("W", bound=QWidget)


class Creator:
    """Stands in for ``Project.create``: records the call and its thread, then makes it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.threads: list[threading.Thread] = []
        self.gate: threading.Event | None = None
        self.error: Exception | None = None
        self.made: list[Project] = []

    def __call__(self, root: Path, name: str, *, blend: Path | None, slot: str) -> Project:
        gate = self.gate  # read once: a test may swap it while this call waits
        self.threads.append(threading.current_thread())
        self.calls.append({"root": root, "name": name, "blend": blend, "slot": slot})
        if gate is not None:
            assert gate.wait(WAIT / 1000)
        if self.error is not None:
            raise self.error
        project = Project.create(root, name, blend=blend, slot=slot)
        self.made.append(project)
        return project

    def close_all(self) -> None:
        for project in self.made:
            project.close()


@pytest.fixture
def creator() -> Iterator[Creator]:
    made = Creator()
    yield made
    made.close_all()


class Choices:
    """Answers the folder and file choosers; None is "Cancel"."""

    def __init__(self) -> None:
        self.folder: Path | None = None
        self.blend: Path | None = None
        self.asked: list[tuple[str, Path]] = []

    def choose_folder(self, _parent: QWidget, start: Path) -> Path | None:
        self.asked.append(("folder", start))
        return self.folder

    def choose_blend(self, _parent: QWidget, start: Path) -> Path | None:
        self.asked.append(("blend", start))
        return self.blend


@pytest.fixture
def choices() -> Choices:
    return Choices()


def make_wizard(
    qtbot: QtBot, creator: Creator, choices: Choices, location: Path
) -> NewProjectWizard:
    wizard = NewProjectWizard(
        default_location=location,
        create=creator,
        choose_folder=choices.choose_folder,
        choose_blend=choices.choose_blend,
    )
    qtbot.addWidget(wizard)
    wizard.resize(720, 520)
    wizard.show()
    return wizard


def child[W: QWidget](wizard: QWidget, kind: type[W], name: str) -> W:
    found = wizard.findChild(kind, name)
    assert found is not None, name
    return found


def edit(wizard: QWidget, name: str) -> QLineEdit:
    return child(wizard, QLineEdit, name)


def label(wizard: QWidget, name: str) -> QLabel:
    return child(wizard, QLabel, name)


def push(wizard: QWidget, name: str) -> QPushButton:
    return child(wizard, QPushButton, name)


def busy_bar(wizard: QWidget) -> QProgressBar:
    return child(wizard, QProgressBar, "createBusy")


def tree(wizard: QWidget) -> QTreeWidget:
    return child(wizard, QTreeWidget, "slotTree")


def wizard_button(wizard: QWizard, which: QWizard.WizardButton) -> QPushButton:
    found = wizard.button(which)
    assert isinstance(found, QPushButton)
    return found


def _items(wizard: QWidget) -> list[tuple[QTreeWidgetItem, QTreeWidgetItem]]:
    """(cup row, slot row) for every slot row, in order."""
    picker = tree(wizard)
    pairs: list[tuple[QTreeWidgetItem, QTreeWidgetItem]] = []
    for cup in range(picker.topLevelItemCount()):
        group = picker.topLevelItem(cup)
        assert group is not None
        for row in range(group.childCount()):
            item = group.child(row)
            assert item is not None
            pairs.append((group, item))
    return pairs


def visible_slots(wizard: QWidget) -> list[str]:
    """The slot file names the list shows now, in order."""
    return [
        item.data(0, Qt.ItemDataRole.UserRole)
        for group, item in _items(wizard)
        if not item.isHidden() and not group.isHidden()
    ]


def slot_item(wizard: QWidget, file: str) -> QTreeWidgetItem:
    for _group, item in _items(wizard):
        if item.data(0, Qt.ItemDataRole.UserRole) == file:
            return item
    raise AssertionError(file)


def fill_first_page(wizard: QWidget, name: str, location: Path) -> None:
    edit(wizard, "trackName").setText(name)
    edit(wizard, "locationEdit").setText(str(location))


def shot(widget: QWidget, name: str) -> None:
    QApplication.processEvents()  # let the layout follow the last change before the picture
    SCREENS.mkdir(parents=True, exist_ok=True)
    assert widget.grab().save(str(SCREENS / name), "PNG")
