"""Mounted outside-edit choices remain signal-only and explicitly gated."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.components.status import ComponentStatus, State
from ctstudio.core.project.project import Project
from ctstudio.gui.views.component_card import ComponentCard
from ctstudio.gui.views.outside_edit_banner import OutsideEditBanner

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("state", [None, State.READY, State.EDITED_EXTERNALLY])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("readonly", [False, True])
def test_card_mounts_only_edited_choices_and_forwards_owned_part(
    qtbot: QtBot, tmp_path: Path, state: State | None, enabled: bool, readonly: bool
) -> None:
    with Project.create(tmp_path / "Pistë 日本", "T") as project:
        project.read_only_reason = "Unsafe recovery" if readonly else None
        card = ComponentCard(COMPONENT_BY_ID["kcl"])
        qtbot.addWidget(card)
        banner = card.findChild(OutsideEditBanner)
        assert isinstance(banner, OutsideEditBanner), "outside-edit choices are not mounted"
        layout = card.layout()
        assert layout is not None
        assert layout.indexOf(banner) >= 0, (
            "the banner is a child but not mounted in the card layout"
        )
        card.bind(project)
        card.set_actions_enabled(enabled)
        card.show_status(None if state is None else ComponentStatus(state, ("A reason",)))
        edited = state == State.EDITED_EXTERNALLY
        eligible = edited and enabled and not readonly
        assert banner.isHidden() is not edited
        assert banner.lock_button.isEnabled() is eligible
        assert banner.discard_button.isEnabled() is eligible
        if edited:
            card.resize(420, 520)
            card.show()
            QApplication.processEvents()
            assert banner.rect().contains(banner.lock_button.geometry())
            assert not banner.geometry().intersects(card.summary.geometry()), (
                "banner overlaps card data"
            )
        emitted = QSignalSpy(card.reconcile_requested)
        banner.lock_button.click()
        assert emitted.count() == int(eligible)
        if eligible:
            assert emitted.at(0) == ["kcl", "lock"]
        banner.requested.emit("discard")  # bypass Qt disablement to prove the card's own guard
        assert emitted.count() == 2 * int(eligible)
        if eligible:
            assert emitted.at(1) == ["kcl", "discard"]
        banner.requested.emit("not-an-action")
        assert emitted.count() == 2 * int(eligible), "an invalid outside-edit action escaped"
        assert project.manifest.components.kcl.mode == "auto"


def test_non_generated_part_never_shows_outside_edit_choices(qtbot: QtBot, tmp_path: Path) -> None:
    with Project.create(tmp_path / "Pistë 日本", "T") as project:
        card = ComponentCard(COMPONENT_BY_ID["objects"])
        qtbot.addWidget(card)
        banner = card.findChild(OutsideEditBanner)
        assert isinstance(banner, OutsideEditBanner)
        card.bind(project)
        card.set_actions_enabled(True)
        card.show_status(ComponentStatus(State.EDITED_EXTERNALLY))
        assert banner.isHidden(), "a non-generated part exposed generated-file actions"
        emitted = QSignalSpy(card.reconcile_requested)
        banner.requested.emit("lock")
        assert emitted.count() == 0


def test_manual_mode_and_rebind_invalidate_old_banner_state(qtbot: QtBot, tmp_path: Path) -> None:
    with Project.create(tmp_path / "Pistë 日本", "T") as project:
        card = ComponentCard(COMPONENT_BY_ID["kcl"])
        qtbot.addWidget(card)
        banner = card.findChild(OutsideEditBanner)
        assert isinstance(banner, OutsideEditBanner), "outside-edit choices are not mounted"
        card.bind(project)
        card.set_actions_enabled(True)
        card.show_status(ComponentStatus(State.EDITED_EXTERNALLY))
        banner.show_note("old result", "old full path")
        banner.show_work("lock")
        components = replace(
            project.manifest.components, kcl=replace(project.manifest.components.kcl, mode="manual")
        )
        project.manifest = replace(project.manifest, components=components)
        card.bind(project)
        card.show_status(ComponentStatus(State.EDITED_EXTERNALLY))
        assert banner.isHidden(), "a manual part must not offer generated-file choices"
        assert not banner.note.text() and not banner.note.toolTip()
        assert not banner.note.accessibleDescription() and banner.progress.isHidden()
