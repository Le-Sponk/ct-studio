"""Native, collapsible presentation of bounded build output (no disk I/O)."""

from PySide6.QtCore import QEvent, QObject, QPersistentModelIndex, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLabel,
    QListView,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ctstudio.core.build.events import CommandRun, LogLine
from ctstudio.gui.build_log_model import COPY_SHORTCUT, BuildLogModel, LogRole

_EMPTY = "No output yet. Start a build below, or wait for its next message."


class _LogView(QListView):
    """Distinguish native layout range clamps from reader scrolls."""

    synchronizing = False
    endRequested = Signal()

    def updateGeometries(self) -> None:
        previous = self.synchronizing
        self.synchronizing = True
        try:
            super().updateGeometries()
        finally:
            self.synchronizing = previous

    def keyPressEvent(self, event: QKeyEvent) -> None:
        super().keyPressEvent(event)
        if event.key() == Qt.Key.Key_End:
            self.endRequested.emit()


class BuildLogPanel(QWidget):
    def __init__(
        self, parent: QWidget | None = None, *, model: BuildLogModel | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("build_log")
        self.setAccessibleName("Build log")
        self.model = model if model is not None else BuildLogModel(self)
        self._following = True
        self._updating = False
        self._anchor = QPersistentModelIndex()
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._refresh)
        self.toggle = QToolButton(self)
        self.toggle.setObjectName("build_log_toggle")
        self.toggle.setAccessibleName("Show build log")
        self.toggle.setText("Show build log")
        self.toggle.setCheckable(True)
        self.body = QWidget(self)
        self.body.setObjectName("build_log_body")
        self.body.setAccessibleName("Build output")
        self.history = QLabel(_EMPTY, self.body)
        self.history.setObjectName("build_log_history")
        self.history.setAccessibleName("Build log history")
        self.history.setAccessibleDescription(self.history.text())
        self.history.setTextFormat(Qt.TextFormat.PlainText)
        self.history.setWordWrap(True)
        self.history.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.view = _LogView(self.body)
        self.view.setObjectName("build_log_view")
        self.view.setAccessibleName("Build output lines")
        self.view.setModel(self.model)
        # Uniform sizes also assume equal widths, clipping wider retained rows.
        self.view.setLayoutMode(QListView.LayoutMode.Batched)
        self.view.setBatchSize(256)
        self.view.setWordWrap(False)
        self.view.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.view.verticalScrollBar().valueChanged.connect(self._scrolled)
        self.view.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self.view.endRequested.connect(self._follow)
        self.view.installEventFilter(self)
        self._copy_actions()
        self._height()
        self.view.hide()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.history)
        body.addWidget(self.view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)
        self.body.hide()
        self.toggle.toggled.connect(self._expanded)

    def _copy_actions(self) -> None:
        """Copy command acts only on a trusted command row; ordinary output never enables it."""
        self.copy_command = QAction("Copy command", self)
        self.copy_command.setObjectName("build_log_copy_command")
        self.copy_command.setShortcut(QKeySequence(COPY_SHORTCUT))
        self.copy_command.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.copy_command.setEnabled(False)
        self._menu_open = False
        self.copy_command.triggered.connect(self._copy)
        self.view.addAction(self.copy_command)
        self.menu = QMenu(self)
        self.menu.setObjectName("build_log_menu")
        self.menu.addAction(self.copy_command)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_menu)
        # Evicting the current row moves Qt's current index (currentChanged); a reset does not.
        self.view.selectionModel().currentChanged.connect(self._sync_copy)
        self.model.modelReset.connect(self._sync_copy)
        # An open menu acts only on the row it was opened on, never a newer command that
        # becomes current when that row is evicted; below the rows it offers no copy.
        self._menu_row: QPersistentModelIndex | None = None
        self.model.rowsRemoved.connect(self._sync_copy)
        self.menu.aboutToHide.connect(self._menu_closed)

    def _command(self) -> str | None:
        index = self._menu_row if self._menu_open else self.view.currentIndex()
        command = index.data(LogRole.Command) if index is not None else None
        return command if isinstance(command, str) and command else None

    def _menu_closed(self) -> None:
        self._menu_open = False
        self._sync_copy()

    def _sync_copy(self) -> None:
        self.copy_command.setEnabled(self._command() is not None)

    def _copy(self) -> None:
        # A menu click arrives after Qt hides the menu, so this reads the current row; that is
        # the menu row whenever the action was enabled, and a disabled action never triggers.
        command = self._command()
        if command is not None:
            QApplication.clipboard().setText(command)

    def _show_menu(self, position: QPoint) -> None:
        index = self.view.indexAt(position)
        self._menu_row = QPersistentModelIndex(index) if index.isValid() else None
        self._menu_open = True
        if index.isValid():
            self.view.setCurrentIndex(index)
        self._sync_copy()
        self.menu.popup(self.view.viewport().mapToGlobal(position))

    def _height(self) -> None:
        self.view.setFixedHeight(
            6 * self.view.fontMetrics().lineSpacing()
            + 2 * self.view.frameWidth()
            + self.view.horizontalScrollBar().sizeHint().height()
            + 8
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.view and event.type() == QEvent.Type.FontChange:
            self._height()
        return super().eventFilter(watched, event)

    def _expanded(self, checked: bool) -> None:
        text = "Hide build log" if checked else "Show build log"
        self.toggle.setText(text)
        self.toggle.setAccessibleName(text)
        self.body.setVisible(checked)
        if checked:
            self._queue()

    def _capture(self) -> None:
        index = self.view.indexAt(QPoint(2, 2))
        if not index.isValid():
            # Qt's hit-test index is incomplete during native batches, even for
            # measured rows. Locate the top using their actual (variable) geometry.
            low, high = 0, self.model.rowCount()
            while low < high:
                middle = (low + high) // 2
                rect = self.view.visualRect(self.model.index(middle))
                if rect.isValid() and rect.bottom() < 2:
                    low = middle + 1
                else:
                    high = middle
            index = self.model.index(low)
        self._anchor = QPersistentModelIndex(index)
        self._offset = self.view.visualRect(index).top()

    def _follow(self) -> None:
        self._following = True
        self._queue()

    def _scrolled(self, value: int) -> None:
        if not self._updating and not self.view.synchronizing:
            self._following = value >= self.view.verticalScrollBar().maximum()
            if not self._following:
                self._capture()

    def _range_changed(self, _minimum: int, _maximum: int) -> None:
        if not self._updating:
            self._queue()

    def _queue(self) -> None:
        if not self._timer.isActive():
            self._timer.start(0)

    def append(self, event: LogLine | CommandRun) -> None:
        self._updating = True
        self.model.append(event)
        self._updating = False
        self._queue()

    def _refresh(self) -> None:
        self._updating = True
        count = self.model.rowCount()
        text = (
            f"{count} retained lines; {self.model.dropped_rows} omitted lines. "
            "Long lines and step names may be shortened. The disk log is unchanged."
            if count
            else _EMPTY
        )
        self.history.setText(text)
        self.history.setAccessibleDescription(text)
        self.view.setVisible(count > 0)
        if self.view.isVisible():
            if self._following:
                self.view.scrollToBottom()
            elif self._anchor.isValid():
                self.view.scrollTo(self._anchor, QAbstractItemView.ScrollHint.PositionAtTop)
                bar = self.view.verticalScrollBar()
                bar.setValue(bar.value() - self._offset)
            else:
                self.view.scrollToTop()
        self._updating = False

    def clear(self, *, collapse: bool = False) -> None:
        self._timer.stop()
        self._updating = True
        self.model.clear()
        self._following = True
        self._anchor = QPersistentModelIndex()
        self._offset = 0
        self._updating = False
        if collapse:
            self.toggle.setChecked(False)
        self._refresh()
