"""Minimal native-palette Qt Widgets shell, with no build logic on the UI thread."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QAction, QCloseEvent, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from ctstudio import __version__
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.project import Project
from ctstudio.gui.recent_projects import RecentProjects
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.new_project import NewProjectWizard
from ctstudio.gui.views.tools_page import ToolsPage
from ctstudio.gui.views.welcome_page import WelcomePage, choose_project

MakeWizard = Callable[["MainWindow"], NewProjectWizard]
_SHUTDOWN_WAIT = 10.0  # seconds a running build gets to stop when the window closes


def _new_project_wizard(parent: MainWindow) -> NewProjectWizard:
    return NewProjectWizard(default_location=Path.home(), parent=parent)


def _ensure_offscreen_font() -> None:
    """Qt's Windows offscreen plugin may expose no system fonts; load one for readable CI PNGs."""
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen" or QFontDatabase.families():
        return
    font_path = (
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        if sys.platform == "win32"
        else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    )
    if not font_path.is_file():
        return
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        return
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    font = app.font()
    font.setFamily(QFontDatabase.applicationFontFamilies(font_id)[0])
    app.setFont(font)


class MainWindow(QMainWindow):
    """Welcome, project navigation and the native application menus."""

    def __init__(
        self,
        services: AppServices | None = None,
        *,
        new_project: MakeWizard = _new_project_wizard,
        recent_projects: RecentProjects | None = None,
        choose_folder: Callable[[QWidget], Path | None] = choose_project,
    ) -> None:
        _ensure_offscreen_font()
        super().__init__()
        self.services = services if services is not None else AppServices()
        self._tools = self.services.tools
        self._make_wizard = new_project
        self._tools_dialog: QDialog | None = None
        self._tools_page: ToolsPage | None = None
        self.setWindowTitle("CT Studio")
        self.resize(960, 600)
        self.setMinimumSize(720, 480)

        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        heading = QLabel("CT Studio", page)
        heading_font = heading.font()
        heading_font.setPointSize(18)
        heading_font.setBold(True)
        heading.setFont(heading_font)
        layout.addWidget(heading)
        layout.addStretch()

        self.welcome = WelcomePage(
            recent_projects if recent_projects is not None else RecentProjects(),
            choose_folder=choose_folder,
            open_project=self._open_from_disk,
            parent=page,
        )
        self.welcome.new_requested.connect(self._new_project)
        self.welcome.opened.connect(self._opened)
        self._empty_title = self.welcome.title
        layout.addWidget(self.welcome, 1)
        layout.addStretch()
        self.setCentralWidget(page)

        self._build_menus()

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.new_project_action = QAction("New project…", self)
        self.new_project_action.setObjectName("newProjectAction")
        self.new_project_action.setShortcut("Ctrl+N")
        self.new_project_action.setToolTip("Make a new track project.")
        self.new_project_action.triggered.connect(self._new_project)
        file_menu.addAction(self.new_project_action)
        self.open_project_action = QAction("Open project…", self)
        self.open_project_action.setObjectName("openProjectAction")
        self.open_project_action.setShortcut("Ctrl+O")
        self.open_project_action.setToolTip("Open a CT Studio project folder.")
        self.open_project_action.triggered.connect(self.welcome.browse)
        file_menu.addAction(self.open_project_action)
        self.welcome.busy_changed.connect(self._navigation)
        self.services.build.running_changed.connect(self._navigation)
        self._navigation()

        settings_menu = self.menuBar().addMenu("&Settings")
        self.tools_action = QAction("Tools…", self)
        self.tools_action.setObjectName("toolsAction")
        self.tools_action.triggered.connect(self._open_tools)
        settings_menu.addAction(self.tools_action)

        self.about_dialog = self._make_about_dialog()
        help_menu = self.menuBar().addMenu("&Help")
        self.about_action = QAction("About CT Studio", self)
        self.about_action.setObjectName("aboutAction")
        self.about_action.triggered.connect(self.about_dialog.open)
        help_menu.addAction(self.about_action)

    def _new_project(self) -> None:
        """File → New project…: a fresh wizard each time; the new project becomes current."""
        if self.welcome.busy or self.services.build.running:
            return
        wizard = self._make_wizard(self)
        wizard.accepted.connect(lambda: self._created(wizard))
        wizard.finished.connect(wizard.deleteLater)
        wizard.open()

    def _created(self, wizard: NewProjectWizard) -> None:
        if wizard.project is not None:
            self._opened(wizard.project)
            self.welcome.remember(wizard.project.root)

    def _open_from_disk(self, root: Path) -> Project:
        current = self.services.project
        if current is not None and current.root == root:
            return current
        return Project.open(root)

    def _opened(self, project: Project) -> None:
        try:
            if project is not self.services.project:
                self.services.adopt(project)
            self._show_project()
        except CTStudioError as exc:
            self.welcome.show_problem(str(exc))

    def _navigation(self, _busy: bool = False) -> None:
        building = self.services.build.running
        available = not self.welcome.busy and not building
        self.new_project_action.setEnabled(available)
        self.open_project_action.setEnabled(available)
        self.welcome.setEnabled(not building)

    def _show_project(self) -> None:
        project = self.services.project
        if project is None:
            self.setWindowTitle("CT Studio")
            self._empty_title.setText("No project open")
            return
        name = project.manifest.project.name
        self.setWindowTitle(f"{name} — CT Studio")
        mode = " (read-only)" if project.read_only else ""
        self._empty_title.setText(f"{name} is open{mode}")  # the dashboard comes in P5-T03

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop the build and the status work, then give the project's lock back."""
        if not self.welcome.shutdown(_SHUTDOWN_WAIT) or not self.services.shutdown(_SHUTDOWN_WAIT):
            self.welcome.show_problem("Work is still stopping. Wait a moment, then close again.")
            event.ignore()
            return
        super().closeEvent(event)

    def _open_tools(self) -> None:
        """Settings → Tools: made on first use (checking starts then), checked again later."""
        if self._tools_dialog is None or self._tools_page is None:
            dialog = QDialog(self)
            dialog.setObjectName("toolsDialog")
            dialog.setWindowTitle("Tools")
            dialog.resize(900, 560)
            layout = QVBoxLayout(dialog)
            self._tools_page = ToolsPage(self._tools, parent=dialog)
            layout.addWidget(self._tools_page)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            self._tools_dialog = dialog
        elif not self._tools_page.busy:
            self._tools_page.recheck(force=False)
        self._tools_dialog.open()

    def _make_about_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setObjectName("aboutDialog")
        dialog.setWindowTitle("About CT Studio")
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        for text in (
            f"CT Studio {__version__}",
            "Turn a Blender project into a Mario Kart Wii custom track.",
            "Licence: GPL-3.0-or-later",
            "Third-party notices will be listed here before release.",
        ):
            label = QLabel(text, dialog)
            label.setWordWrap(True)
            layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog
