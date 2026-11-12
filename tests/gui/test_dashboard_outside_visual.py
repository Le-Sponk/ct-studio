"""P5-T06c2b2c1 actual MainWindow actions/geometry; constructed offscreen visual proxies."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import outside_visual_helpers as visual
import pytest
from assign_helpers import kcl_bytes
from outside_flow_helpers import answer_discard
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from reconcile_helpers import EditWork, settled

from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(45)]


def assert_completed(window: MainWindow, project: Project, work: EditWork, action: str) -> None:
    page, banner = window.dashboard, window.dashboard.cards["kcl"].outside
    assert len(work.calls) == 1 and work.calls[0][2] == action
    assert work.calls[0][3] is not threading.main_thread(), "core action ran on GUI thread"
    assert not work.calls[0][3].is_alive(), "outcome published before worker joined"
    assert project.manifest == manifest_io.load(project.manifest_path), "saved state not published"
    assert not project.read_only
    assert banner.note.text() and banner.note.text() == page.launch_notice.text()
    assert banner.note.accessibleDescription() == banner.note.toolTip()
    assert banner.progress.isHidden() and not banner.activity.text()
    assert_sibling_notes(window)
    assert page.edit_button.isEnabled(), "joined completion stranded sibling writers"
    assert_saved_files(window, project, action)


def assert_sibling_notes(window: MainWindow) -> None:
    assert all(
        not card.outside.note.text()
        for name, card in window.dashboard.cards.items()
        if name != "kcl"
    ), "outcome appeared on a sibling card"


def assert_saved_files(window: MainWindow, project: Project, action: str) -> None:
    page = window.dashboard
    stage = project.root / ".ctstudio/stage/course.kcl"
    if action == "lock":
        assert project.manifest.components.kcl.mode == "manual"
        assert (project.root / "files/course.kcl").is_file()
        assert (project.root / "files/course.kcl").read_bytes() == stage.read_bytes()
        assert page.cards["kcl"].status_label.text() == "your own file"
    else:
        backups = list(project.root.glob(".ctstudio/backups/*/.ctstudio/stage/course.kcl"))
        assert not stage.exists() and len(backups) == 1
        assert backups[0].read_bytes() == kcl_bytes(0x480)
        assert project.manifest.components.kcl.mode == "auto"
        assert page.cards["kcl"].status_label.text() != "edited outside CT Studio"


def click_and_check_work(qtbot: QtBot, window: MainWindow, work: EditWork, action: str) -> None:
    page, banner = window.dashboard, window.dashboard.cards["kcl"].outside
    if action == "lock":
        banner.lock_button.click()
    else:
        seen: list[bool] = []
        QTimer.singleShot(0, lambda: answer_discard(action, seen))
        banner.discard_button.click()
        assert seen == [True], "native Discard confirmation was bypassed"
    assert settled(qtbot, work.entered.is_set), "button did not dispatch core work"
    assert window.services.launch.busy and page.outside_edits.pending
    assert banner.progress.isVisible() and banner.progress.maximum() == 0
    expected = "Locking as manual…" if action == "lock" else "Backing up outside edit…"
    assert banner.activity.text() == expected
    assert not banner.lock_button.isEnabled() and not banner.discard_button.isEnabled()
    assert not page.edit_button.isEnabled() and not page.builds.controls.test_button.isEnabled()
    assert_siblings_disabled(window)


def assert_siblings_disabled(window: MainWindow) -> None:
    page = window.dashboard
    assert all(
        not card.mode_button.isEnabled() and not card.choose_action.isEnabled()
        for card in page.cards.values()
    ), "busy outside edit left sibling writers enabled"


@pytest.mark.parametrize("size", [(720, 480), (1280, 1000)], ids=["minimum", "tall"])
@pytest.mark.parametrize("enlarged", [False, True], ids=["normal", "font150-stretch120"])
@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("action", ["lock", "discard"])
def test_populated_window_outside_edit_geometry_and_real_joined_outcome(
    qtbot: QtBot,
    qapp: QApplication,
    tmp_path: Path,
    size: tuple[int, int],
    enlarged: bool,
    dark: bool,
    action: str,
) -> None:
    theme = "dark" if dark else "light"
    scale = "large" if enlarged else "normal"
    tag = f"{size[0]}x{size[1]}-{scale}-{theme}-{action}"
    folder = Path(os.environ.get("CTSTUDIO_OUTSIDE_VISUAL_DIR", "tests/artifacts/screens/outside"))
    with visual.visual_style(qapp, dark, enlarged) as family:
        with visual.outside_window(qtbot, tmp_path, size) as (window, project, work, area):
            page, card = window.dashboard, window.dashboard.cards["kcl"]
            banner = card.outside
            assert window.size().width() == size[0] and window.size().height() == size[1]
            assert len(page.cards) == 8 and all(
                c.status_label.text() != "Not checked" for c in page.cards.values()
            )
            assert page.name_label.text() and page.folder_label.text()
            assert page.slot_label.text() and page.source_label.text()
            assert page.builds.controls.isVisible() and banner.lock_button.isEnabled()
            visual.settle_layout(qtbot, window, area)
            images = [
                visual.capture(window, folder, tag + "-window"),
                visual.capture(window, folder, tag + "-populated", page=True),
            ]
            visual.assert_geometry(window, area)
            visual.tab_controls(qtbot, window, area)
            visual.reveal(qtbot, window, area, banner)
            click_and_check_work(qtbot, window, work, action)
            visual.reveal(qtbot, window, area, banner)
            images.append(visual.capture(window, folder, tag + "-working"))
            visual.assert_geometry(window, area)
            work.gate.set()
            assert settled(qtbot, lambda: visual.idle(window)), (
                "joined action/status publication never finished"
            )
            assert_completed(window, project, work, action)
            target = card if card.height() <= area.viewport().height() else banner
            visual.reveal(qtbot, window, area, target)
            images.append(visual.capture(window, folder, tag + "-outcome"))
            visual.assert_geometry(window, area)
            save_proof(folder, tag, family, window, area.viewport().width(), images)


def save_proof(
    folder: Path, tag: str, family: str, window: MainWindow, viewport: int, images: list[Path]
) -> None:
    proof = {
        "leaf": "P5-T06c2b2c1",
        "font": family,
        "case": tag,
        "proxy": "offscreen palette/font; not Linux desktop appearance",
        "widths": [viewport, window.dashboard.width()],
        "images": list(map(str, images)),
        "note": window.dashboard.cards["kcl"].outside.note.text(),
    }
    (folder / f"{tag}.json").write_text(json.dumps(proof), encoding="utf-8")
