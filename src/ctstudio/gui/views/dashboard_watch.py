"""The dashboard's side of file watching (P5-T06a): a check on outside changes, and a notice.

The app's services watch the current project and ask for statuses when its files change;
this shows that check as running, and keeps a separate notice when changes can no longer be
noticed (a status result never hides it). ``follow`` (run on every Refresh, and whenever a
saved manifest is published) re-watches as the manifest now says, which also retries after
watching stopped. No disk work happens here.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ctstudio.core.project.project import Project
from ctstudio.gui.services import AppServices


class DashboardWatch(QObject):
    def __init__(
        self,
        services: AppServices,
        shown: Callable[[], Project | None],
        begin_check: Callable[[], None],
        page: QWidget,
    ) -> None:
        """``shown``: the dashboard's project while it is the current one, else None."""
        super().__init__(page)
        self._services, self._shown, self._begin_check = services, shown, begin_check
        self.notice = QLabel(page)
        self.notice.setObjectName("dashboardWatchNotice")
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        self.notice.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.notice.hide()
        self._failed_meanwhile = False
        services.watcher.changed.connect(self._changed)
        services.watcher.failed.connect(self._failed)

    def follow(self) -> None:
        """Watch the shown project as its manifest now says; a new watcher clears the notice."""
        if self._shown() is None:
            return
        self._failed_meanwhile = False
        if self._services.follow_files() and not self._failed_meanwhile:
            self.clear()

    def clear(self) -> None:
        self._show("")

    def _changed(self, root: object) -> None:
        project = self._shown()
        # During a build the services asked for nothing: the build's own refresh will.
        if project is not None and root == project.root and not self._services.build.running:
            self._begin_check()

    def _failed(self, error: object) -> None:
        if self._shown() is not None:
            self._failed_meanwhile = True
            self._show(str(error))

    def _show(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setToolTip(text)
        self.notice.setAccessibleDescription(text)
        self.notice.setVisible(bool(text))
