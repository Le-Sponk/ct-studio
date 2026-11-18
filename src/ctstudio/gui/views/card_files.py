"""Card file assignment helpers: the native chooser and one-file copy-only drops (P5-T04b)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QFileDialog, QWidget

from ctstudio.core.components.registry import ComponentSpec

DROP_ONE = "Drop one file or folder from this computer. Nothing was changed."
ChooseSource = Callable[[QWidget, ComponentSpec, Path], Path | None]  # None: cancelled


def choose_source(parent: QWidget, spec: ComponentSpec, start: Path) -> Path | None:
    """The native chooser: a folder for post-effects, otherwise one file."""
    if spec.kind is None:
        chosen = QFileDialog.getExistingDirectory(
            parent, f"Choose the {spec.name} folder", str(start)
        )
    else:
        chosen, _filter = QFileDialog.getOpenFileName(
            parent, f"Choose the {spec.name} file", str(start)
        )
    return Path(chosen) if chosen else None


def takes_a_file(spec: ComponentSpec) -> bool:
    """A part whose modes include manual and that has its own settings table."""
    return "manual" in spec.modes and spec.manifest_table not in (None, "project")


def copyable(event: QDropEvent) -> bool:
    copy = Qt.DropAction.CopyAction
    return event.mimeData().hasUrls() and event.possibleActions() & copy == copy


def dropped_path(data: QMimeData) -> Path | None:
    """The one local file or folder in a drop, or None for anything else."""
    urls = data.urls() if data.hasUrls() else []
    if len(urls) != 1 or not urls[0].isLocalFile() or not urls[0].toLocalFile():
        return None
    return Path(urls[0].toLocalFile())
