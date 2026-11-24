"""One Settings window: a page list on the left and the pages on the right (P5-T08a).

Settings → Settings… opens it at the last page shown; Settings → Tools… and Settings →
Editors… open it at their page. A page is made the first time it is shown (Tools starts its
check then) and refreshed each time the window is opened at it again: Tools checks again
unless a check runs, Editors rereads the settings file. The Build page (P5-T08b) belongs to
the open project, which may have changed since, so every opening rereads it; Appearance
(P5-T08d) rereads the settings file like Editors. Switching pages in the list only shows
them. Closing the window with unsaved Build changes asks Save / Discard / Cancel; Save closes
it once the save is done. The window fits itself again whenever its layout asks
(``_FittingDialog``).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ctstudio.gui.appearance import AppearanceService
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.appearance_section import AppearanceSection
from ctstudio.gui.views.build_page import BuildPage
from ctstudio.gui.views.editors_page import EditorsPage
from ctstudio.gui.views.tools_page import ToolsPage

TOOLS = "Tools"
BUILD = "Build"
EDITORS = "Editors"
APPEARANCE = "Appearance"
PAGES = (TOOLS, BUILD, EDITORS, APPEARANCE)  # the original P5-T08 order; Advanced follows
FIRST_SIZE = (900, 560)  # the old Tools window's size, kept within the screen


class _FittingDialog(QDialog):
    """Fits itself again whenever its layout asks for a new size: another page or tab shown,
    or a label's text changed. Qt passes that request up one widget at a time over several
    event turns, so it arrives here only once the whole window knows the new height."""

    def __init__(
        self, fit: Callable[[], None], may_close: Callable[[], bool], parent: QWidget
    ) -> None:
        super().__init__(parent)
        self._fit = fit
        self._may_close = may_close

    def event(self, event: QEvent) -> bool:
        handled = super().event(event)
        if event.type() == QEvent.Type.LayoutRequest:
            self._fit()
        return handled

    def reject(self) -> None:
        """Close, Escape and the title bar's close all come here."""
        if self._may_close():
            super().reject()

    def close_now(self) -> None:
        super().reject()


class _PageList(QListWidget):
    """The page names, as wide as the longest one in the current font. Enter stays here: a
    plain list passes it on to the window, whose default button (Close) would shut it."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPages")
        self.setAccessibleName("Settings pages")
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.addItems(list(PAGES))
        self._fit_names()

    def _fit_names(self) -> None:
        margin = self.fontMetrics().averageCharWidth()
        self.setFixedWidth(self.sizeHintForColumn(0) + 2 * self.frameWidth() + margin)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._fit_names()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()


class SettingsWindow:
    """The Settings window, made on first use and reused."""

    def __init__(
        self,
        services: AppServices,
        parent: QWidget,
        *,
        build_saved: Callable[[], None] | None = None,
    ) -> None:
        self._services = services
        self._parent = parent
        self._build_saved = build_saved
        self._last = TOOLS
        self._close_after_save = False
        self.question: QMessageBox | None = None
        self.dialog: _FittingDialog | None = None
        self.pages: _PageList | None = None
        self.close: QPushButton | None = None
        self.stack: QStackedWidget | None = None
        self.tools_page: ToolsPage | None = None
        self.build_page: BuildPage | None = None
        self.editors_page: EditorsPage | None = None
        self.appearance_page: AppearanceSection | None = None

    def open(self, name: str | None = None) -> None:
        """Show the window at page ``name`` (default: the last one shown), refreshed."""
        dialog, pages = self._window()
        target = self._last if name is None else name
        pages.setCurrentRow(PAGES.index(target))  # makes and shows it (``_show``)
        self._refresh(target)  # a page made just now is still busy, so this skips it
        if target != BUILD and self.build_page is not None:
            self.build_page.reload()  # the project may have changed since it was read
        dialog.open()  # showing it asks the layout, which fits it (_FittingDialog)

    def _window(self) -> tuple[QDialog, _PageList]:
        if self.dialog is not None and self.pages is not None:
            return self.dialog, self.pages
        dialog = _FittingDialog(self._fit, self._may_close, self._parent)
        dialog.setObjectName("settingsDialog")
        dialog.setWindowTitle("Settings")
        area = dialog.screen().availableGeometry()
        dialog.resize(min(FIRST_SIZE[0], area.width()), min(FIRST_SIZE[1], area.height()))
        pages = _PageList(dialog)
        stack = QStackedWidget(dialog)
        stack.setObjectName("settingsStack")
        body = QHBoxLayout()
        body.addWidget(pages)
        body.addWidget(stack, 1)
        layout = QVBoxLayout(dialog)
        layout.addLayout(body)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        close = buttons.button(QDialogButtonBox.StandardButton.Close)
        close.setDefault(True)  # never an in-page button such as Add… or Re-check
        layout.addWidget(buttons)
        self.dialog, self.pages, self.stack, self.close = dialog, pages, stack, close
        pages.currentRowChanged.connect(self._show)
        return dialog, pages

    def _made(self, name: str) -> QWidget | None:
        made: dict[str, QWidget | None] = {
            TOOLS: self.tools_page,
            BUILD: self.build_page,
            EDITORS: self.editors_page,
        }
        return made.get(name, self.appearance_page)

    def _show(self, row: int) -> None:
        if not 0 <= row < len(PAGES) or self.stack is None or self.dialog is None:
            return
        name = PAGES[row]
        page = self._made(name)
        if page is None:
            page = self._make(name, self.dialog)
            self.stack.addWidget(page)
            self._close_last(page)
        self.stack.setCurrentWidget(page)
        self._last = name

    def _close_last(self, page: QWidget) -> None:
        """Tab goes list, page, Close: a page made after Close would come after it otherwise
        (Qt orders Tab by creation)."""
        last: QWidget | None = None
        widget = page.nextInFocusChain()
        while widget is not None and widget is not page and page.isAncestorOf(widget):
            if widget.focusPolicy() != Qt.FocusPolicy.NoFocus:
                last = widget  # Qt ignores a tab order that starts at an unfocusable widget
            widget = widget.nextInFocusChain()
        if last is not None and self.close is not None:
            QWidget.setTabOrder(last, self.close)

    def _make(self, name: str, dialog: QDialog) -> QWidget:
        if name == TOOLS:
            self.tools_page = ToolsPage(self._services.tools, parent=dialog)
            return self.tools_page
        if name == BUILD:
            self.build_page = BuildPage(self._services, parent=dialog)
            self.build_page.saved.connect(self._saved)
            self.build_page.save_finished.connect(self._save_finished)
            return self.build_page
        if name == EDITORS:
            self.editors_page = EditorsPage(self._services.editor_settings, parent=dialog)
            return self.editors_page
        self.appearance_page = AppearanceSection(AppearanceService(), dialog)
        if self.pages is not None:  # a refused pick hides the choice: keep the keyboard near
            self.appearance_page.keyboard_lost.connect(self.pages.setFocus)
        self.appearance_page.reload()
        return self.appearance_page

    def _refresh(self, name: str) -> None:
        if name == TOOLS and self.tools_page is not None and not self.tools_page.busy:
            self.tools_page.recheck(force=False)
        elif name == BUILD and self.build_page is not None:
            self.build_page.reload()  # a running read or save is kept
        elif name == EDITORS and self.editors_page is not None:
            self.editors_page.reload()  # the file may have changed since; a running read is kept
        elif name == APPEARANCE and self.appearance_page is not None:
            self.appearance_page.reload()  # likewise

    def _saved(self) -> None:
        if self._build_saved is not None:
            self._build_saved()

    def _may_close(self) -> bool:
        """Close unless the Build page is busy or has unsaved changes (then it asks)."""
        page, dialog = self.build_page, self.dialog
        if self.question is not None:
            return False  # already asking
        if page is None or dialog is None:
            return True
        if page.busy:
            page.problem.setText(
                "The build settings are still being read or saved. Wait, then close."
            )
            return False
        if not page.changed:
            return True
        save, discard = QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Discard
        cancel = QMessageBox.StandardButton.Cancel
        if page.can_save:
            text = "Save the changes to this project's build settings before closing?"
            buttons, default = save | discard | cancel, save
        else:  # Save would do nothing now (a build runs, say): offer only what works
            text = "These build settings changes cannot be saved now. Discard them and close?"
            buttons, default = discard | cancel, cancel
        question = QMessageBox(
            QMessageBox.Icon.Question, "Unsaved build settings", text, buttons, dialog
        )
        question.setObjectName("buildUnsavedQuestion")
        question.setDefaultButton(default)
        self.question = question
        question.finished.connect(partial(self._answered, question, page, dialog))
        question.open()
        return False

    def _answered(
        self, question: QMessageBox, page: BuildPage, dialog: _FittingDialog, _result: int
    ) -> None:
        self.question = None
        question.deleteLater()
        clicked = question.clickedButton()
        if clicked is question.button(QMessageBox.StandardButton.Discard):
            page.undo()
            dialog.close_now()
        elif clicked is question.button(QMessageBox.StandardButton.Save):
            # Set first: a save that cannot start its thread finishes inside ``save()``.
            self._close_after_save = True
            if not page.save():
                self._close_after_save = False

    def _save_finished(self, ok: bool) -> None:
        close, self._close_after_save = self._close_after_save, False
        if close and ok and self.dialog is not None:
            self.dialog.close_now()

    def _fit(self) -> None:
        """Make the window tall enough for its wrapped text at its width (``adjustSize`` does
        not ask wrapped labels): a long banner or large font is never cut short."""
        dialog = self.dialog
        layout = None if dialog is None else dialog.layout()
        if dialog is None or layout is None:
            return
        layout.activate()
        width = max(dialog.width(), layout.minimumSize().width())
        height = min(
            layout.totalHeightForWidth(width), dialog.screen().availableGeometry().height()
        )
        dialog.setMinimumHeight(height)
        dialog.resize(width, max(height, dialog.height()))
