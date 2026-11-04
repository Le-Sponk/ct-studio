"""P5-T02a: File → New project… in the main window, and the wizard's screenshots."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from build_fakes import FakeBuilds
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtWidgets import QApplication, QWizard
from pytestqt.qtbot import QtBot
from wizard_fakes import (
    WAIT,
    Choices,
    Creator,
    choices,
    creator,
    edit,
    fill_first_page,
    label,
    make_wizard,
    shot,
    slot_item,
    tree,
    wizard_button,
)

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.new_project import WORKER_NAME, NewProjectWizard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["choices", "creator"]  # fixtures used by name


def quiet_services(builds: FakeBuilds | None = None) -> AppServices:
    """Real services whose status check and build touch no tool."""
    fake = builds if builds is not None else FakeBuilds()
    status = StatusService(evaluate=lambda _project, _tools: {}, find_tools=lambda **_kw: ())
    return AppServices(status=status, build=BuildController(plan=fake.plan, build=fake.run))


def window_with(
    qtbot: QtBot, creator: Creator, choices: Choices, location: Path
) -> tuple[MainWindow, AppServices]:
    services = quiet_services()

    def wizard(parent: MainWindow) -> NewProjectWizard:
        return NewProjectWizard(
            default_location=location,
            create=creator,
            choose_folder=choices.choose_folder,
            choose_blend=choices.choose_blend,
            parent=parent,
        )

    window = MainWindow(services=services, new_project=wizard)
    qtbot.addWidget(window)
    window.show()
    return window, services


def open_wizard(window: MainWindow) -> NewProjectWizard:
    action = window.findChild(QAction, "newProjectAction")
    assert action is not None
    assert action.text() == "New project…"
    action.trigger()
    shown = [w for w in window.findChildren(NewProjectWizard) if w.isVisible()]
    assert len(shown) == 1
    return shown[0]


def test_new_project_opens_the_wizard_and_then_the_project(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    window, services = window_with(qtbot, creator, choices, tmp_path)
    wizard = open_wizard(window)
    fill_first_page(wizard, "Ma piste é", tmp_path)
    for _ in range(3):
        wizard.next()
    with qtbot.waitSignal(wizard.accepted, timeout=WAIT):
        wizard_button(wizard, QWizard.WizardButton.FinishButton).click()
    assert services.project is wizard.project
    assert services.project is not None
    assert not services.project.read_only
    assert window.windowTitle() == "Ma piste é — CT Studio"
    assert "Ma piste é" in label(window, "emptyTitle").text()
    assert Project.open(tmp_path / "Ma piste é").read_only  # this app holds it
    assert not [t for t in threading.enumerate() if t.name == WORKER_NAME]
    qtbot.waitUntil(lambda: not window.findChildren(NewProjectWizard), timeout=WAIT)  # deleted


def test_a_cancelled_wizard_leaves_the_window_as_it_was(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    window, services = window_with(qtbot, creator, choices, tmp_path)
    wizard = open_wizard(window)
    with qtbot.waitSignal(wizard.rejected, timeout=WAIT):
        wizard.reject()
    assert services.project is None
    assert window.windowTitle() == "CT Studio"
    qtbot.waitUntil(lambda: not window.findChildren(NewProjectWizard), timeout=WAIT)  # deleted
    second = open_wizard(window)  # a fresh wizard each time
    assert edit(second, "trackName").text() == ""


def test_closing_the_window_gives_the_project_back(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    window, services = window_with(qtbot, creator, choices, tmp_path)
    root = tmp_path / "Ma piste"
    Project.create(root, "Ma piste").close()
    services.adopt(Project.open(root))
    window.close()
    assert services.project is None
    with Project.open(root) as again:
        assert not again.read_only


def test_a_new_project_gives_the_one_before_back(qtbot: QtBot, tmp_path: Path) -> None:
    services = quiet_services()
    first = Project.create(tmp_path / "Une", "Une")
    services.adopt(first)
    services.adopt(Project.create(tmp_path / "Deux", "Deux"))
    with Project.open(tmp_path / "Une") as again:
        assert not again.read_only
    assert services.shutdown(WAIT / 1000)


def test_a_project_handed_over_while_building_is_closed_not_kept(
    qtbot: QtBot, tmp_path: Path
) -> None:
    builds = FakeBuilds()
    builds.gate = gate = threading.Event()
    services = quiet_services(builds)
    first = Project.create(tmp_path / "Une", "Une")
    services.adopt(first)
    with qtbot.waitSignal(services.build.running_changed, timeout=WAIT):
        services.build.start(first)
    second = Project.create(tmp_path / "Deux", "Deux")
    with pytest.raises(ProjectError, match="being built"):
        services.adopt(second)
    assert second.read_only  # given back, not left locked by nobody
    assert services.project is first
    gate.set()
    qtbot.waitUntil(lambda: not services.build.running, timeout=WAIT)
    assert services.shutdown(WAIT / 1000)


# --- screenshots --------------------------------------------------------------------------------


def _dark(app: QApplication) -> QPalette:
    palette = QPalette(app.palette())
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(role, QColor("#f3f5f8"))
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
        palette.setColor(role, QColor("#202530"))
    return palette


def test_screenshots_of_every_page(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    location = tmp_path / "Mes pistes"
    (location / "Pistë 1").mkdir(parents=True)
    (location / "Pistë 1" / "notes.txt").write_text("x")
    wizard = make_wizard(qtbot, creator, choices, location)
    fill_first_page(wizard, "Pistë 1", location)
    shot(wizard, "p5-t02a-wizard-1-name-problem.png")
    edit(wizard, "trackName").setText("Pistë des Neiges")
    shot(wizard, "p5-t02a-wizard-1-name.png")
    wizard.next()
    edit(wizard, "blendEdit").setText(str(tmp_path / "absent.blend"))
    shot(wizard, "p5-t02a-wizard-2-blend-problem.png")
    edit(wizard, "blendEdit").setText("")
    shot(wizard, "p5-t02a-wizard-2-blend.png")
    wizard.next()
    edit(wizard, "slotSearch").setText("circuit")
    tree(wizard).setCurrentItem(slot_item(wizard, "castle_course"))
    shot(wizard, "p5-t02a-wizard-3-track.png")
    wizard.next()
    shot(wizard, "p5-t02a-wizard-4-summary.png")
    creator.error = ProjectError(
        "Could not make the folder.", hint="Choose a folder you can write to."
    )
    wizard_button(wizard, QWizard.WizardButton.FinishButton).click()
    qtbot.waitUntil(lambda: not wizard.busy, timeout=WAIT)
    shot(wizard, "p5-t02a-wizard-4-summary-problem.png")
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    original = app.palette()
    app.setPalette(_dark(app))
    try:
        shot(wizard, "p5-t02a-wizard-4-summary-dark.png")
        wizard.back()
        shot(wizard, "p5-t02a-wizard-3-track-dark.png")
    finally:
        app.setPalette(original)
