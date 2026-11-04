"""R1: history and status completion must not cache ancestor-disabled widget state."""

import threading
from pathlib import Path

import pytest
from PySide6.QtWidgets import QVBoxLayout, QWidget, QWizard
from pytestqt.qtbot import QtBot
from test_new_project_window import open_wizard, window_with
from wizard_fakes import Choices, Creator, fill_first_page, wizard_button

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.recent_projects import RecentProjects, RecentResult
from ctstudio.gui.views.component_card import ComponentCard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


class HeldHistory(RecentProjects):
    def __init__(self, path: Path, gate: threading.Event, fail: bool) -> None:
        super().__init__(path)
        self.gate, self.fail = gate, fail

    def remember(self, root: Path) -> RecentResult:
        assert self.gate.wait(10), "History worker was not released"
        if self.fail:
            raise RuntimeError("Synthetic history save failed")
        return super().remember(root)


def assert_dashboard_ready(window: MainWindow) -> None:
    page = window.dashboard
    assert page.isEnabled()
    assert page.edit_button.isEnabled()
    assert page.refresh_button.isEnabled()
    for card in page.cards.values():
        assert card.mode_button.isEnabled() == bool(card.mode_actions)
        assert all(action.isEnabled() for action in card.mode_actions.values())
        if card.path is not None:
            assert card.copy_action.isEnabled()
            assert card.more_button.isEnabled()


@pytest.mark.parametrize("fail", [False, True], ids=["history-saved", "history-error"])
def test_new_project_history_finishes_after_statuses(
    qtbot: QtBot, tmp_path: Path, fail: bool
) -> None:
    creator, choices = Creator(), Choices()
    window, services = window_with(qtbot, creator, choices, tmp_path)
    gate = threading.Event()
    window.welcome.history = HeldHistory(tmp_path / "history.json", gate, fail)
    try:
        wizard = open_wizard(window)
        fill_first_page(wizard, "History overlap café", tmp_path)
        for _ in range(3):
            wizard.next()
        wizard_button(wizard, QWizard.WizardButton.FinishButton).click()
        qtbot.waitUntil(lambda: services.project is not None and window.welcome.busy)
        qtbot.waitUntil(lambda: not window.dashboard.busy)
        assert window.welcome.busy
        assert not window.dashboard.cards["kcl"].mode_button.isEnabled()
        gate.set()
        qtbot.waitUntil(lambda: not window.welcome.busy)
        assert_dashboard_ready(window)
    finally:
        gate.set()
        qtbot.waitUntil(lambda: not window.welcome.busy)
        window.close()
        creator.close_all()


@pytest.mark.parametrize("component", ["course_model", "track_info"])
def test_ancestor_reenable_restores_copy_and_mode_controls(
    qtbot: QtBot, tmp_path: Path, component: str
) -> None:
    with Project.create(tmp_path / "Ancestor café", "Ancestor café") as project:
        host = QWidget()
        qtbot.addWidget(host)
        card = ComponentCard(COMPONENT_BY_ID[component], host)
        layout = QVBoxLayout(host)
        layout.addWidget(card)
        card.bind(project)
        card.set_actions_enabled(True)
        host.show()
        host.setEnabled(False)
        card.set_actions_enabled(True)
        host.setEnabled(True)
        assert card.copy_button.isEnabled()
        assert card.copy_action.isEnabled()
        assert card.more_button.isEnabled()
        assert card.mode_button.isEnabled() == bool(card.mode_actions)
