"""P5-T09a acceptance: one user's path through the real main window, from a new project to
the issues of its first build.

New project (the wizard) → Collision chosen through Choose file… and Course data dropped on
its card (manual mode, committed fixture files) → a test build on the fake Wiimm tools →
the statuses and the issues panel show the new check. "Ready statuses" follows the
owner's decision of 2026-11-25: the assigned parts show "your own file", Objects "ready",
and every other card its pinned status, before and after the build. Setup in ``e2e_helpers``; the
pictures go to ``tests/artifacts/screens/p5-t09-*.png``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from assign_helpers import drop, local
from e2e_helpers import INPUTS, WAIT, idle, studio
from editor_request_helpers import settled
from issues_helpers import child, rows
from PySide6.QtWidgets import QWidget, QWizard
from pytestqt.qtbot import QtBot
from test_new_project_window import open_wizard
from wizard_fakes import fill_first_page, shot, wizard_button

from ctstudio.core.build.events import BuildSummary
from ctstudio.core.build.validate import ISSUES_FILE
from ctstudio.core.components.registry import ComponentSpec
from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.issues_panel import IssuesPanel

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]

NAME = "Piste é"
STATUSES = {
    "kcl": "your own file",
    "kmp": "your own file",
    "objects": "ready",
    "track_info": "warning",
    "course_model": "problem",
    "skybox": "problem",
    "minimap": "missing",
    "posteffect": "missing",
}
GROUPS = [
    "Course model — 1 error",
    "Collision — 1 note",
    "Minimap — 1 error",
    "Skybox — 1 error",
    "Course data — 2 warnings and 2 hints",
]

TRACK = "build/beginner_course.szs"
PANEL_SUMMARY = f"Last check of {TRACK}: 3 errors, 2 warnings, 2 hints and 1 note."
SKYBOX_DETAIL = (
    "Error: Skybox (vrcorn_model.brres) is not in beginner_course.szs, so the game cannot load"
    " the track.\n"
    "Next: Choose its file on the dashboard, then build again.\n"
    f"File: {TRACK}\n"
    "Part: Skybox"
)


def created(qtbot: QtBot, window: MainWindow, services: AppServices, folder: Path) -> Project:
    """Make the project with the New project wizard, as a user would."""
    wizard = open_wizard(window)
    fill_first_page(wizard, NAME, folder)
    for _ in range(3):
        wizard.next()
    shot(wizard, "p5-t09-1-wizard-summary.png")
    with qtbot.waitSignal(wizard.accepted, timeout=WAIT):
        wizard_button(wizard, QWizard.WizardButton.FinishButton).click()
    assert settled(qtbot, lambda: idle(window, services), WAIT), "the first check hung"
    project = services.project
    assert project is not None and project.root == folder / NAME
    assert window.windowTitle() == f"{NAME} — CT Studio"
    assert window.dashboard.isVisible()
    return project


def assigned(qtbot: QtBot, window: MainWindow, services: AppServices) -> None:
    """Collision through Choose file…, Course data by a drop: both copied into the project."""
    asked: list[tuple[str, Path]] = []

    def choose(_parent: QWidget, spec: ComponentSpec, start: Path) -> Path:
        asked.append((spec.id, start))
        return INPUTS / "course.kcl"

    cards = window.dashboard.cards
    cards["kcl"].choose = choose
    assert settled(qtbot, lambda: cards["kcl"].choose_action.isEnabled(), WAIT)
    cards["kcl"].choose_action.trigger()
    assert settled(qtbot, lambda: idle(window, services), WAIT), "choosing a file hung"
    copied(window, services, "kcl", "course.kcl")
    assert drop(cards["kmp"], local(INPUTS / "course.kmp")), "the card refused the drop"
    assert settled(qtbot, lambda: idle(window, services), WAIT), "the drop hung"
    copied(window, services, "kmp", "course.kmp")
    project = services.project
    assert project is not None and asked == [("kcl", project.root)]
    assert cards["kcl"].mode_label.text() == "Mode: manual"  # still, after the second one
    assert settled(qtbot, lambda: statuses(window)["kmp"] == "your own file", WAIT)


def copied(window: MainWindow, services: AppServices, part: str, name: str) -> None:
    """The part now uses a copy of the fixture in the project, and its card says so."""
    project = services.project
    assert project is not None
    card, copy = window.dashboard.cards[part], project.root / "files" / name
    assert copy.read_bytes() == (INPUTS / name).read_bytes()
    assert (card.mode_label.text(), card.path) == ("Mode: manual", copy)
    assert card.assign_note.text() == f"Copied from {name}."


def statuses(window: MainWindow) -> dict[str, str]:
    return {part: card.status_label.text() for part, card in window.dashboard.cards.items()}


def laid_out(panel: IssuesPanel) -> bool:
    """The selected finding's details have their full height and sit below the list.

    Selecting a finding grows the details label only on a later layout pass: until then its
    old one-line box lies below the list even though the new text is drawn over it.
    """
    detail, tree = panel.detail, panel.tree
    tall = detail.height() >= detail.heightForWidth(detail.width())
    return tall and detail.geometry().top() > tree.geometry().bottom()


def built(qtbot: QtBot, window: MainWindow, services: AppServices) -> BuildSummary:
    """A test build from the dashboard's button; off the UI thread, then checked again."""
    summaries: list[BuildSummary] = []
    services.build.finished.connect(summaries.append)
    controls = window.dashboard.builds.controls
    assert settled(qtbot, controls.test_button.isEnabled, WAIT)
    controls.test_button.click()
    assert settled(qtbot, lambda: len(summaries) == 1, 3 * WAIT), "the build never finished"
    assert settled(qtbot, lambda: idle(window, services), WAIT), "the check after it hung"
    services.build.finished.disconnect(summaries.append)
    return summaries[0]


def test_a_new_project_is_assigned_built_and_checked(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_tools_path: object
) -> None:
    folder = tmp_path / "Projets é"
    folder.mkdir()
    with studio(qtbot, folder, monkeypatch) as (window, services):
        project = created(qtbot, window, services, folder)
        shot(window, "p5-t09-2-new-project.png")
        assert window.dashboard.issues.tree.topLevelItemCount() == 0

        assigned(qtbot, window, services)
        assert settled(qtbot, lambda: statuses(window) == STATUSES, WAIT), sorted(
            statuses(window).items()
        )
        shot(window, "p5-t09-3-assigned.png")

        summary = built(qtbot, window, services)
        assert summary.outcome == "succeeded", summary
        assert summary.ran == ("stage:kcl", "stage:kmp", "assemble", "validate")
        cards = window.dashboard.cards
        result = window.dashboard.builds.controls.last_result.text()
        # The fixture track has check errors: made, but not called a success (P5-GATE).
        assert result.startswith("Build finished in ") and "See Issues" in result, result
        for part in ("kcl", "kmp"):
            assert cards[part].build_label.text() == "Build: done", part
        assert (project.root / ISSUES_FILE).is_file()
        # The build changes no status (manual parts stay "your own file"); what it adds is the
        # check's report, shown below. The statuses are pinned again after its refresh.
        assert settled(qtbot, lambda: statuses(window) == STATUSES, WAIT), sorted(
            statuses(window).items()
        )
        shot(window, "p5-t09-4-built.png")

        tree = window.dashboard.issues.tree
        assert settled(qtbot, lambda: tree.topLevelItemCount() > 0, WAIT), "no issues shown"
        assert [group for group, _items in rows(tree)] == GROUPS
        panel = window.dashboard.issues
        assert panel.summary.text() == PANEL_SUMMARY
        group = tree.topLevelItem(GROUPS.index("Skybox — 1 error"))
        assert group is not None
        tree.setCurrentItem(child(group, 0))
        assert panel.detail.text() == SKYBOX_DETAIL
        assert settled(qtbot, lambda: laid_out(panel), WAIT), "the details cover the list"
        shot(window, "p5-t09-5-issues.png")
