"""How the wizard reports project-making failures through its worker (Deep Clean #1 f)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import NoReturn

import pytest
from PySide6.QtWidgets import QWizard
from pytestqt.qtbot import QtBot
from waits import settled
from wizard_fakes import Choices, Creator, choices, creator, edit, label, make_wizard, wizard_button

from ctstudio.core.errors import CTStudioError
from ctstudio.gui.views.new_project import NewProjectWizard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
__all__ = ["choices", "creator"]  # fixtures used by name


def test_a_thread_that_cannot_start_says_so_and_frees_the_wizard(
    qtbot: QtBot,
    creator: Creator,
    choices: Choices,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    _to_summary(wizard, tmp_path)

    def no_threads(_thread: threading.Thread) -> NoReturn:
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, "start", no_threads)
    wizard_button(wizard, QWizard.WizardButton.FinishButton).click()
    assert not wizard.busy and wizard.project is None and wizard.isVisible()
    assert "could not be made" in label(wizard, "createProblem").text()
    assert wizard_button(wizard, QWizard.WizardButton.FinishButton).isEnabled()


def _to_summary(wizard: NewProjectWizard, tmp_path: Path) -> None:
    blend = tmp_path / "piste.blend"
    blend.write_bytes(b"BLENDER")
    edit(wizard, "trackName").setText("Ma piste")
    wizard_button(wizard, QWizard.WizardButton.NextButton).click()
    edit(wizard, "blendEdit").setText(str(blend))
    for _ in range(2):
        wizard_button(wizard, QWizard.WizardButton.NextButton).click()


def test_a_refusal_for_the_user_is_shown_and_not_logged_as_a_fault(
    qtbot: QtBot,
    creator: Creator,
    choices: Choices,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    _to_summary(wizard, tmp_path)
    creator.error = CTStudioError("That folder already has files.")
    with caplog.at_level(logging.ERROR, logger="ctstudio"):
        wizard_button(wizard, QWizard.WizardButton.FinishButton).click()
        assert settled(qtbot, lambda: not wizard.busy)
    assert "already has files" in label(wizard, "createProblem").text()
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
