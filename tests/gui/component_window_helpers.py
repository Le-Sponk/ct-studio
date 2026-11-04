"""Window setup shared by component-control integration tests."""

from pathlib import Path

from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.project.project import Project
from ctstudio.gui.component_modes import ComponentModeService
from ctstudio.gui.main_window import MainWindow, MakeMode, _component_mode_dialog
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.project_details import ProjectDetailsDialog


def mode_window(
    qtbot: QtBot, folder: Path, factory: MakeMode = _component_mode_dialog
) -> MainWindow:
    window = MainWindow(quiet_services(), edit_component=factory)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    window._opened(Project.create(folder / "Modes café", "Modes café"))
    qtbot.waitUntil(lambda: not window.dashboard.busy)
    return window


def window_with_mode_service(
    qtbot: QtBot, folder: Path, service: ComponentModeService
) -> MainWindow:
    def factory(
        services: AppServices, component: str, mode: str, parent: QWidget
    ) -> ProjectDetailsDialog:
        from ctstudio.gui.views.component_mode import ComponentModeDialog

        return ComponentModeDialog(
            services, component, initial_mode=mode or None, service=service, parent=parent
        )

    return mode_window(qtbot, folder, factory)
