"""P5-GATE review: the wizard's pages check the disk once per edit, never again in isComplete.
QWizard asks isComplete often (every completeChanged, page change and button refresh); on a
slow or sleeping drive each disk check can hold the window, so the answer is kept."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QWizard
from pytestqt.qtbot import QtBot
from wizard_fakes import (
    Choices,
    Creator,
    choices,
    creator,
    edit,
    label,
    make_wizard,
    wizard_button,
)

from ctstudio.gui.views import new_project_pages
from ctstudio.gui.views.new_project_pages import BlendPage, NamePage

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["choices", "creator"]  # fixtures used by name


def counted(monkeypatch: pytest.MonkeyPatch, name: str) -> list[object]:
    calls: list[object] = []
    real = getattr(new_project_pages, name)

    def wrapper(arg: Path | None) -> str | None:
        calls.append(arg)
        return real(arg)

    monkeypatch.setattr(new_project_pages, name, wrapper)
    return calls


def test_the_project_page_checks_the_folder_once_per_edit(
    qtbot: QtBot,
    creator: Creator,
    choices: Choices,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    calls = counted(monkeypatch, "_folder_problem")
    edit(wizard, "trackName").setText("Ma piste")
    assert len(calls) == 1
    page = wizard.currentPage()
    assert isinstance(page, NamePage)
    assert all(page.isComplete() for _ in range(5))
    assert wizard_button(wizard, QWizard.WizardButton.NextButton).isEnabled()
    assert len(calls) == 1, "isComplete went back to the disk"


def test_the_kept_answer_follows_the_last_edit(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    (tmp_path / "Ma piste").write_text("x")
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    page = wizard.currentPage()
    assert isinstance(page, NamePage)
    edit(wizard, "trackName").setText("Ma piste")
    assert not page.isComplete()
    edit(wizard, "trackName").setText("Autre piste")
    assert page.isComplete()
    edit(wizard, "trackName").setText("")
    assert not page.isComplete()


def test_the_blend_page_checks_the_file_once_per_edit(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = BlendPage(lambda _parent, _start: None, lambda: tmp_path)
    qtbot.addWidget(page)
    assert page.isComplete()  # empty is allowed
    calls = counted(monkeypatch, "_blend_problem")
    page.blend.setText(str(tmp_path / "missing.blend"))
    assert len(calls) == 1
    assert not any(page.isComplete() for _ in range(5))
    assert len(calls) == 1, "isComplete went back to the disk"
    (tmp_path / "found.blend").write_bytes(b"BLENDER")
    page.blend.setText(str(tmp_path / "found.blend"))
    assert page.isComplete()
    page.blend.clear()
    assert page.isComplete()


def test_going_back_checks_the_folder_again(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    """The kept answer is refreshed when a page is shown again (P5-GATE delta review)."""
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    edit(wizard, "trackName").setText("Ma piste")
    wizard_button(wizard, QWizard.WizardButton.NextButton).click()
    folder = tmp_path / "Ma piste"
    folder.mkdir()
    (folder / "old.txt").write_text("x")  # someone used the folder meanwhile
    wizard_button(wizard, QWizard.WizardButton.BackButton).click()
    page = wizard.currentPage()
    assert isinstance(page, NamePage)
    assert not page.isComplete()
    assert not wizard_button(wizard, QWizard.WizardButton.NextButton).isEnabled()
    assert "already has files" in label(wizard, "locationProblem").text()


def test_going_back_checks_the_blend_again(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    blend = tmp_path / "piste.blend"
    blend.write_bytes(b"BLENDER")
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    edit(wizard, "trackName").setText("Ma piste")
    wizard_button(wizard, QWizard.WizardButton.NextButton).click()
    edit(wizard, "blendEdit").setText(str(blend))
    wizard_button(wizard, QWizard.WizardButton.NextButton).click()
    blend.unlink()  # moved away meanwhile
    wizard_button(wizard, QWizard.WizardButton.BackButton).click()
    page = wizard.currentPage()
    assert isinstance(page, BlendPage)
    assert not page.isComplete()
    assert "was not found" in label(wizard, "blendProblem").text()
