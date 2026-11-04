"""P5-T02a: the new-project wizard makes a project on disk; each page checks its input.

The creator (``Project.create``) is wrapped by a recorder that also checks it runs off the
UI thread; folder and file choosers are fakes. Tests wait on signals or state, never sleep.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QWizard
from pytestqt.qtbot import QtBot
from wizard_fakes import (
    WAIT,
    Choices,
    Creator,
    busy_bar,
    choices,
    creator,
    edit,
    fill_first_page,
    label,
    make_wizard,
    push,
    slot_item,
    tree,
    wizard_button,
)

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.gui.views import new_project
from ctstudio.gui.views.new_project import NewProjectWizard, folder_name

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["choices", "creator"]  # fixtures used by name

NEXT = QWizard.WizardButton.NextButton
BACK = QWizard.WizardButton.BackButton
FINISH = QWizard.WizardButton.FinishButton
CANCEL = QWizard.WizardButton.CancelButton


def to_summary(wizard: NewProjectWizard, name: str, location: Path) -> None:
    fill_first_page(wizard, name, location)
    for _ in range(3):
        assert wizard_button(wizard, NEXT).isEnabled()
        wizard.next()


def finish(qtbot: QtBot, wizard: NewProjectWizard) -> None:
    with qtbot.waitSignal(wizard.accepted, timeout=WAIT):
        wizard_button(wizard, FINISH).click()


# --- the whole flow -----------------------------------------------------------------------------


def test_the_flow_makes_the_project_on_disk(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    location = tmp_path / "Mes pistes é"
    blend = tmp_path / "source ü" / "piste.blend"
    blend.parent.mkdir()
    blend.write_bytes(b"BLENDER-v405")
    wizard = make_wizard(qtbot, creator, choices, location)
    fill_first_page(wizard, "Piste des Neiges", location)
    wizard.next()
    edit(wizard, "blendEdit").setText(str(blend))
    wizard.next()
    edit(wizard, "slotSearch").setText("mario circ")
    tree(wizard).setCurrentItem(slot_item(wizard, "castle_course"))
    wizard.next()
    summary = label(wizard, "summaryText").text()
    assert "Piste des Neiges" in summary
    assert str(location / "Piste des Neiges") in summary
    assert "piste.blend" in summary
    assert "Mario Circuit" in summary
    finish(qtbot, wizard)

    root = location / "Piste des Neiges"
    assert creator.calls == [
        {"root": root, "name": "Piste des Neiges", "blend": blend, "slot": "castle_course"}
    ]
    assert creator.threads[0] is not threading.main_thread()
    made = manifest_io.load(root / manifest_io.FILE_NAME).project
    assert (made.name, made.slot) == ("Piste des Neiges", "castle_course")
    assert made.blend == str(blend.resolve())
    assert wizard.project is not None
    assert wizard.project.root == root
    assert not wizard.project.read_only  # handed over open, so locked by this app


def test_the_defaults_are_no_blend_and_luigi_circuit(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    assert edit(wizard, "locationEdit").text() == str(tmp_path)
    to_summary(wizard, "Ma piste", tmp_path)
    summary = label(wizard, "summaryText").text()
    assert "Luigi Circuit" in summary
    assert "none yet" in summary.lower()
    finish(qtbot, wizard)
    assert creator.calls[0]["blend"] is None
    assert creator.calls[0]["slot"] == "beginner_course"


# --- page 1: name and folder --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "folder"),
    [
        ("Piste des Neiges", "Piste des Neiges"),
        ("  Ma piste  ", "Ma piste"),
        ('a<b>c:d"e/f\\g|h?i*j', "a_b_c_d_e_f_g_h_i_j"),
        ("fin. ", "fin"),
        ("CON", "CON_"),
        ("lpt1", "lpt1_"),
        ("日本のコース", "日本のコース"),
        ("...", ""),
    ],
)
def test_the_folder_is_named_after_the_track(name: str, folder: str) -> None:
    assert folder_name(name) == folder


def test_the_first_page_shows_the_folder_it_will_make(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    assert not wizard_button(wizard, NEXT).isEnabled()  # no name yet
    edit(wizard, "trackName").setText("Ma piste")
    assert str(tmp_path / "Ma piste") in label(wizard, "folderPreview").text()
    assert wizard_button(wizard, NEXT).isEnabled()


@pytest.mark.parametrize("name", ["", "   ", "..."])
def test_a_name_without_letters_cannot_go_on(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path, name: str
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    edit(wizard, "trackName").setText(name)
    assert not wizard_button(wizard, NEXT).isEnabled()


def test_a_relative_location_cannot_go_on(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", Path("pistes"))
    assert not wizard_button(wizard, NEXT).isEnabled()
    assert "full path" in label(wizard, "locationProblem").text().lower()


def test_the_name_is_kept_without_spaces_round_it(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    to_summary(wizard, "  Ma piste  ", tmp_path)
    finish(qtbot, wizard)
    assert creator.calls[0]["name"] == "Ma piste"
    assert creator.calls[0]["root"] == tmp_path / "Ma piste"


def test_no_location_cannot_go_on(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    edit(wizard, "locationEdit").setText("  ")
    assert not wizard_button(wizard, NEXT).isEnabled()
    assert "choose where" in label(wizard, "locationProblem").text().lower()


@pytest.mark.parametrize(
    ("make", "words"),
    [
        (lambda folder: (folder / manifest_io.FILE_NAME).write_text("x"), "already has a ct"),
        (lambda folder: (folder / "notes.txt").write_text("x"), "already has files"),
    ],
    ids=["project there", "files there"],
)
def test_a_folder_in_use_cannot_go_on(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path, make: object, words: str
) -> None:
    folder = tmp_path / "Ma piste"
    folder.mkdir()
    make(folder)  # type: ignore[operator]
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    assert not wizard_button(wizard, NEXT).isEnabled()
    assert words in label(wizard, "locationProblem").text().lower()
    edit(wizard, "trackName").setText("Autre piste")  # another name: another folder
    assert wizard_button(wizard, NEXT).isEnabled()
    assert label(wizard, "locationProblem").text() == ""


def test_an_empty_folder_of_that_name_is_fine(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    (tmp_path / "Ma piste").mkdir()
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    assert wizard_button(wizard, NEXT).isEnabled()


def test_a_file_where_the_folder_would_go_cannot_go_on(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    (tmp_path / "Ma piste").write_text("x")
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    assert not wizard_button(wizard, NEXT).isEnabled()
    assert "is a file" in label(wizard, "locationProblem").text().lower()


def test_browse_sets_the_location_and_cancel_keeps_it(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    choices.folder = tmp_path / "ailleurs"
    push(wizard, "browseLocation").click()
    assert edit(wizard, "locationEdit").text() == str(tmp_path / "ailleurs")
    choices.folder = None  # Cancel
    push(wizard, "browseLocation").click()
    assert edit(wizard, "locationEdit").text() == str(tmp_path / "ailleurs")
    assert choices.asked == [("folder", tmp_path), ("folder", tmp_path / "ailleurs")]


# --- page 2: the .blend -------------------------------------------------------------------------


def test_the_blend_can_be_chosen_cleared_or_left_out(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    blend = tmp_path / "piste.blend"
    blend.write_bytes(b"BLENDER")
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    wizard.next()
    assert wizard_button(wizard, NEXT).isEnabled()  # optional
    choices.blend = blend
    push(wizard, "browseBlend").click()
    assert edit(wizard, "blendEdit").text() == str(blend)
    choices.blend = None
    push(wizard, "browseBlend").click()  # Cancel keeps it
    assert edit(wizard, "blendEdit").text() == str(blend)
    push(wizard, "clearBlend").click()
    assert edit(wizard, "blendEdit").text() == ""
    assert wizard_button(wizard, NEXT).isEnabled()


@pytest.mark.parametrize(
    ("file", "words"),
    [("absent.blend", "was not found"), ("piste.txt", "not a .blend file")],
)
def test_a_wrong_blend_cannot_go_on(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path, file: str, words: str
) -> None:
    (tmp_path / "piste.txt").write_text("x")
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    wizard.next()
    edit(wizard, "blendEdit").setText(str(tmp_path / file))
    assert not wizard_button(wizard, NEXT).isEnabled()
    assert words in label(wizard, "blendProblem").text().lower()


def test_a_blend_in_capitals_is_fine(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    (tmp_path / "PISTE.BLEND").write_bytes(b"BLENDER")
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    fill_first_page(wizard, "Ma piste", tmp_path)
    wizard.next()
    edit(wizard, "blendEdit").setText(str(tmp_path / "PISTE.BLEND"))
    assert wizard_button(wizard, NEXT).isEnabled()
    assert label(wizard, "blendProblem").text() == ""


# --- page 4: creating ---------------------------------------------------------------------------


def test_finish_is_busy_until_the_project_is_made(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    creator.gate = threading.Event()
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    to_summary(wizard, "Ma piste", tmp_path)
    assert busy_bar(wizard).isHidden()
    wizard_button(wizard, FINISH).click()
    qtbot.waitUntil(lambda: len(creator.calls) == 1, timeout=WAIT)
    assert wizard.isVisible()  # not closed before it is made
    wizard.accept()  # Enter again: not a second project
    wizard.reject()  # Escape: waits for it
    assert wizard.isVisible()
    assert wizard.busy
    assert not busy_bar(wizard).isHidden()
    for which in (FINISH, BACK, CANCEL):
        assert not wizard_button(wizard, which).isEnabled()
    with qtbot.waitSignal(wizard.accepted, timeout=WAIT):
        creator.gate.set()
    assert not wizard.busy
    assert len(creator.calls) == 1


def test_a_failure_is_shown_and_finish_can_be_tried_again(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    creator.error = ProjectError(
        "Could not make the folder.", hint="Choose a folder you can write to."
    )
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    to_summary(wizard, "Ma piste", tmp_path)
    wizard_button(wizard, FINISH).click()
    qtbot.waitUntil(lambda: not wizard.busy, timeout=WAIT)
    problem = label(wizard, "createProblem").text()
    assert "Could not make the folder." in problem
    assert "Choose a folder you can write to." in problem
    assert wizard.isVisible()
    assert wizard.project is None
    for which in (FINISH, BACK, CANCEL):
        assert wizard_button(wizard, which).isEnabled()
    wizard.back()
    wizard.next()  # back on the summary: the old failure is gone
    assert label(wizard, "createProblem").text() == ""
    creator.error = None
    finish(qtbot, wizard)
    assert label(wizard, "createProblem").text() == ""
    assert wizard.project is not None


def test_an_unexpected_failure_is_shown_too(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    creator.error = RuntimeError("boom")
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    to_summary(wizard, "Ma piste", tmp_path)
    wizard_button(wizard, FINISH).click()
    qtbot.waitUntil(lambda: not wizard.busy, timeout=WAIT)
    assert "could not be made" in label(wizard, "createProblem").text().lower()
    assert wizard.isVisible()


class _SlowEnd(threading.Thread):
    """A worker that lingers after its job: the wizard must wait for it before closing."""

    def run(self) -> None:
        super().run()
        time.sleep(0.2)


def test_the_worker_has_ended_when_the_wizard_closes(
    qtbot: QtBot,
    creator: Creator,
    choices: Choices,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(new_project, "threading", SimpleNamespace(Thread=_SlowEnd))
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    alive: list[bool] = []
    wizard.accepted.connect(lambda: alive.append(creator.threads[0].is_alive()))
    to_summary(wizard, "Ma piste", tmp_path)
    finish(qtbot, wizard)
    assert alive == [False]


def test_cancel_makes_nothing(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    to_summary(wizard, "Ma piste", tmp_path)
    with qtbot.waitSignal(wizard.rejected, timeout=WAIT):
        wizard_button(wizard, CANCEL).click()
    assert creator.calls == []
    assert not (tmp_path / "Ma piste").exists()
