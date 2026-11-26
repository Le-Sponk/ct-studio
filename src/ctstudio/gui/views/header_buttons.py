"""A row of buttons that takes two rows only when one does not fit (P5-T10d).

The choice follows the width alone, so placing the buttons never resizes them into a loop,
and the smallest width is the two-row one, so a window can still shrink to it. Labels are
never squeezed: a bigger font or a narrower window moves the buttons to two rows instead.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QGridLayout, QPushButton, QSizePolicy, QWidget


class HeaderButtons(QWidget):
    def __init__(self, buttons: list[QPushButton], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons = list(buttons)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._columns = 0
        self._place(2)

    def _gap(self) -> int:
        spacing = self._grid.horizontalSpacing()  # 6 px in every Windows style and Fusion
        if spacing < 0:  # a style that spaces each pair of controls itself (some Linux themes)
            button = QSizePolicy.ControlType.PushButton
            spacing = self.style().layoutSpacing(button, button, Qt.Orientation.Horizontal)
        return max(0, spacing)

    def _one_row_width(self) -> int:
        widths = [button.sizeHint().width() for button in self._buttons]
        return sum(widths) + self._gap() * (len(widths) - 1)

    def _two_row_width(self) -> int:
        columns = (self._buttons[0::2], self._buttons[1::2])
        widths = [max((b.sizeHint().width() for b in column), default=0) for column in columns]
        return sum(widths) + self._gap()

    def _place(self, columns: int) -> None:
        if columns == self._columns:
            return
        self._columns = columns
        for button in self._buttons:
            self._grid.removeWidget(button)
        for column in range(self._grid.columnCount()):
            self._grid.setColumnStretch(column, 0)
        for index, button in enumerate(self._buttons):
            self._grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self._grid.setColumnStretch(column, 1)
        self.updateGeometry()

    def _fit(self, width: int) -> None:
        self._place(len(self._buttons) if width >= self._one_row_width() else 2)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit(event.size().width())

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.LayoutRequest:  # a label or font changed a button's size
            self._fit(self.width())
        return super().event(event)

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), self._two_row_width()), hint.height())
