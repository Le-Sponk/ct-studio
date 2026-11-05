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
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ctstudio import __version__
from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.project import Project
from ctstudio.gui.recent_projects import RecentProjects
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.dashboard import Dashboard
from ctstudio.gui.views.new_project import NewProjectWizard
from ctstudio.gui.views.project_details import ProjectDetailsDialog
from ctstudio.gui.views.tools_page import ToolsPage
from ctstudio.gui.views.welcome_page import WelcomePage, choose_project

MakeWizard = Callable[["MainWindow"], NewProjectWizard]
MakeDetails = Callable[[AppServices, QWidget], ProjectDetailsDialog]
MakeMode = Callable[[AppServices, str, str, QWidget], ProjectDetailsDialog]
_SHUTDOWN_WAIT = 10.0  # seconds a running build gets to stop when the window closes


def _new_project_wizard(parent: MainWindow) -> NewProjectWizard:
    return NewProjectWizard(default_location=Path.home(), parent=parent)


def _project_details_dialog(services: AppServices, parent: QWidget) -> ProjectDetailsDialog:
    return ProjectDetailsDialog(services, parent=parent)


def _component_mode_dialog(
    services: AppServices, component: str, mode: str, parent: QWidget
) -> ProjectDetailsDialog:
    from ctstudio.gui.views.component_mode import ComponentModeDialog

    return ComponentModeDialog(services, component, initial_mode=mode or None, parent=parent)


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
        edit_project: MakeDetails = _project_details_dialog,
        edit_component: MakeMode = _component_mode_dialog,
        recent_projects: RecentProjects | None = None,
        choose_folder: Callable[[QWidget], Path | None] = choose_project,
    ) -> None:
        _ensure_offscreen_font()
        super().__init__()
        self.services = services if services is not None else AppServices()
        self._tools = self.services.tools
        self._make_wizard = new_project
        self._make_details = edit_project
        self._make_mode = edit_component
        self._details: ProjectDetailsDialog | None = None
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
        self.welcome.checked.connect(self._welcome_checked)
        self._empty_title = self.welcome.title
        layout.addWidget(self.welcome, 1)
        layout.addStretch()
        self.pages = QStackedWidget(self)
        self.pages.addWidget(page)
        self.dashboard = Dashboard(self.services, self)
        self._route_dashboard()
        scroll = QScrollArea(self.pages)
        scroll.setObjectName("dashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.dashboard)
        self.pages.addWidget(scroll)
        self.setCentralWidget(self.pages)

        self._build_menus()
        self._show_project()

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
        self.open_project_action.triggered.connect(self._browse)
        file_menu.addAction(self.open_project_action)
        self.welcome.busy_changed.connect(self._navigation)
        self.services.build.running_changed.connect(self._navigation)
        self.services.launch.busy_changed.connect(self._navigation)

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
        self._view_menu()
        self._navigation()

    def _view_menu(self) -> None:
        menu = self.menuBar().addMenu("&View")
        self.home_action = QAction("Recent projects", self)
        self.home_action.setObjectName("homeAction")
        self.home_action.setShortcut("Ctrl+H")
        self.home_action.triggered.connect(self._go_home)
        menu.addAction(self.home_action)
        self.dashboard_action = QAction("Project dashboard", self)
        self.dashboard_action.setObjectName("dashboardAction")
        self.dashboard_action.setShortcut("Ctrl+D")
        self.dashboard_action.triggered.connect(self._show_project)
        menu.addAction(self.dashboard_action)

    def _welcome_checked(self) -> None:
        if self.welcome.problem:
            self._home()  # keep ancillary history failures visible after adopting a project

    def _home(self) -> None:
        self.pages.setCurrentIndex(0)

    def _go_home(self) -> None:
        """View → Recent projects; refused while a launch reports back to the dashboard."""
        if not self.services.launch.busy:
            self._home()

    def _blocked(self) -> bool:
        services = self.services
        busy = services.build.running or services.editing or services.launch.busy
        return self.welcome.busy or busy

    def _browse(self) -> None:
        if self._blocked():
            return
        self._home()
        self.welcome.browse()

    def _new_project(self) -> None:
        """File → New project…: a fresh wizard each time; the new project becomes current."""
        if self._blocked():
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
            self._home()
            self.welcome.show_problem(str(exc))

    def _navigation(self, _busy: bool = False) -> None:
        building = self.services.build.running
        launching = self.services.launch.busy
        navigating = not self.welcome.busy and not self.services.editing and not launching
        available = navigating and not building
        self.new_project_action.setEnabled(available)
        self.open_project_action.setEnabled(available)
        self.welcome.setEnabled(not building and not self.services.editing and not launching)
        self.dashboard.setEnabled(not self.welcome.busy)
        self.home_action.setEnabled(navigating)
        self.dashboard_action.setEnabled(self.services.project is not None and navigating)

    def _show_project(self) -> None:
        project = self.services.project
        if project is None:
            self.setWindowTitle("CT Studio")
            self._empty_title.setText("No project open")
            self._home()
            return
        name = project.manifest.project.name
        self.setWindowTitle(f"{name} — CT Studio")
        mode = " (read-only)" if project.read_only else ""
        self._empty_title.setText(f"{name} is open{mode}")
        self.dashboard.set_project(project)
        self.pages.setCurrentIndex(1)
        self._navigation()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop the build and the status work, then give the project's lock back."""
        if self._details is not None:
            if self._details.busy:
                self._details.problem.setText("Work is still finishing. Wait, then close again.")
                event.ignore()
                return
            self._details.reject()
        if not self.welcome.shutdown(_SHUTDOWN_WAIT) or not self.services.shutdown(_SHUTDOWN_WAIT):
            self._still_stopping()
            event.ignore()
            return
        super().closeEvent(event)

    def _still_stopping(self) -> None:
        text = "Work is still stopping. Wait a moment, then close again."
        if self.services.build.running and self.services.project is not None:
            self.pages.setCurrentIndex(1)
            self.dashboard.builds.controls.show_notice(text)
            return
        if self.services.launch.busy and self.services.project is not None:
            self.dashboard.show_launch_note(text)  # navigation is held: the dashboard is shown
            return
        self._home()
        self.welcome.show_problem(text)

    def _route_dashboard(self) -> None:
        self.dashboard.builds.can_start = lambda: not self.welcome.busy
        self.dashboard.edit_requested.connect(self._edit_project)
        self.dashboard.mode_requested.connect(self._edit_component)
        self.dashboard.blender_requested.connect(self._open_blender)
        self.dashboard.reveal_requested.connect(self._launch)

    def _edit_project(self) -> None:
        if not self._can_edit():
            return
        self._open_editor(self._make_details(self.services, self))

    def _can_edit(self) -> bool:
        project = self.services.project
        return (
            project is not None
            and not project.read_only
            and not self.services.editing
            and not self.services.build.running
            and not self.services.launch.busy
            and not self.welcome.busy
            and not self.dashboard.busy
        )

    def _open_blender(self) -> None:
        self._launch(None)

    def _launch(self, component: str | None = None) -> None:
        """Ask the launch owner for Blender (None) or one component's folder."""
        if self.welcome.busy or self.services.editing or self.dashboard.busy:
            return
        try:
            started = self.services.start_launch(component)
        except CTStudioError as exc:
            self.dashboard.show_launch_problem(exc)
            return
        if started:
            self.dashboard.show_launching(component)

    def _edit_component(self, component: str, mode: str = "") -> None:
        spec = COMPONENT_BY_ID.get(component)
        if (
            not self._can_edit()
            or spec is None
            or spec.manifest_table in (None, "project")
            or len(spec.modes) < 2
            or (mode != "" and mode not in spec.modes)
        ):
            return
        self._open_editor(self._make_mode(self.services, component, mode, self))

    def _open_editor(self, dialog: ProjectDetailsDialog) -> None:
        self._details = dialog
        dialog.finished.connect(self._details_finished)
        dialog.finished.connect(dialog.deleteLater)
        self._navigation()
        self.dashboard._sync()
        dialog.open()

    def _details_finished(self, _result: int) -> None:
        dialog, self._details = self._details, None
        project = self.services.project
        if dialog is not None and dialog.saved and project is not None:
            self.services.status.clear()
            self.dashboard.set_project(project, changed=True)
        self._navigation()
        self.dashboard._sync()

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
