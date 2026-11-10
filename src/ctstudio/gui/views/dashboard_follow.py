"""P5-T03e34: keep the dashboard's end in view during a build while the reader stays there."""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QScrollArea


class DashboardFollower(QObject):
    """Follow the scroll area's end while active; a reader scrolling up pauses following.

    Every queued layout pass that grows the page changes the scroll range, so following
    reacts to the range itself rather than to build events. Focus is never moved.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._area: QScrollArea | None = None
        self._active = False
        self._following = False

    def attach(self, area: QScrollArea) -> None:
        if self._area is area:
            return
        self._area = area
        bar = area.verticalScrollBar()
        bar.rangeChanged.connect(self._range_changed)
        bar.valueChanged.connect(self._moved)

    def start(self) -> None:
        """A new accepted build: follow the end until the reader scrolls away."""
        self._active = self._following = True
        self._range_changed(0, 0)

    def stop(self) -> None:
        """A rebind or cleared presentation: never scroll for a forgotten run."""
        self._active = self._following = False

    def _range_changed(self, _minimum: int, _maximum: int) -> None:
        if self._area is not None and self._active and self._following:
            bar = self._area.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _moved(self, value: int) -> None:
        if self._area is not None and self._active:
            self._following = value >= self._area.verticalScrollBar().maximum()
