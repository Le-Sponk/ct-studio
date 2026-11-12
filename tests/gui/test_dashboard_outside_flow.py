"""Real watcher to native card buttons: no direct service request bypasses the UI."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# Wait for actual native watcher registration; there is no public bridge-ready signal.
import threading
import time
from pathlib import Path

import pytest
from outside_flow_helpers import answer_discard, change_stage, live_dashboard
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from reconcile_helpers import settled

from ctstudio.core.project import manifest_io
from ctstudio.core.project.watch import ProjectWatcher

pytestmark = [pytest.mark.gui, pytest.mark.timeout(45)]


@pytest.mark.parametrize("action", ["lock", "discard", "cancel"])
def test_real_watcher_reaches_native_choices_and_preserves_exact_bytes(
    qtbot: QtBot, tmp_path: Path, action: str
) -> None:
    with live_dashboard(qtbot, tmp_path) as (page, project, work, _area):
        card, banner = page.cards["kcl"], page.cards["kcl"].outside
        assert card.status_label.text() == "ready"
        assert banner.isHidden()
        watcher = page.services.watcher._watcher
        assert isinstance(watcher, ProjectWatcher)
        assert watcher.wait_ready(10), "the real watcher never registered"
        before = project.manifest_path.read_bytes()
        begun = time.monotonic()
        changed = change_stage(project)
        assert settled(qtbot, banner.lock_button.isEnabled), "no eligible outside-edit choice"
        assert time.monotonic() - begun < 2.0, "the edited banner took more than two seconds"
        assert not banner.isHidden() and "outside CT Studio" in banner.title.text()
        seen: list[bool] = []

        if action == "lock":
            banner.lock_button.click()
        else:
            QTimer.singleShot(0, lambda: answer_discard(action, seen))
            banner.discard_button.click()
            assert seen == [True], "the native confirmation was bypassed"
        assert settled(
            qtbot,
            lambda: (
                not page.services.launch.busy and not page.services.status.busy and not page.busy
            ),
        )
        stage = project.root / ".ctstudio/stage/course.kcl"
        if action == "cancel":
            assert not work.calls and not banner.note.text()
            assert project.manifest_path.read_bytes() == before and stage.read_bytes() == changed
        else:
            assert len(work.calls) == 1 and work.calls[0][2] == action
            assert work.calls[0][3] is not threading.main_thread()
            assert project.manifest == manifest_io.load(project.manifest_path)
            assert banner.note.text() == page.launch_notice.text() and banner.note.text()
            assert banner.progress.isHidden()
            if action == "lock":
                assert project.manifest.components.kcl.mode == "manual"
                assert (project.root / "files/course.kcl").read_bytes() == changed
            else:
                backups = list(project.root.glob(".ctstudio/backups/*/.ctstudio/stage/course.kcl"))
                assert not stage.exists() and len(backups) == 1
                assert backups[0].read_bytes() == changed


def test_real_dashboard_tab_path_reaches_and_activates_lock(qtbot: QtBot, tmp_path: Path) -> None:
    with live_dashboard(qtbot, tmp_path) as (page, project, work, area):
        banner = page.cards["kcl"].outside
        watcher = page.services.watcher._watcher
        assert isinstance(watcher, ProjectWatcher) and watcher.wait_ready(10)
        change_stage(project)
        assert settled(qtbot, banner.lock_button.isEnabled)
        area.resize(900, 260)  # force the target offscreen before testing keyboard scrolling
        assert settled(
            qtbot,
            lambda: (
                not area.viewport()
                .rect()
                .contains(
                    banner.lock_button.mapTo(area.viewport(), banner.lock_button.rect().center())
                )
            ),
        ), "keyboard fixture did not start with an offscreen action"
        area.activateWindow()
        QApplication.processEvents()
        page.refresh_button.setFocus()
        assert page.refresh_button.hasFocus()
        for _index in range(100):
            focus = QApplication.focusWidget()
            assert focus is not None
            if focus is banner.lock_button:
                break
            QTest.keyClick(focus, Qt.Key.Key_Tab)
        assert banner.lock_button.hasFocus(), "the real card's Lock action is not Tab-reachable"
        assert settled(
            qtbot,
            lambda: (
                area.viewport()
                .rect()
                .contains(
                    banner.lock_button.mapTo(area.viewport(), banner.lock_button.rect().center())
                )
            ),
        )
        assert area.verticalScrollBar().value() > 0, "keyboard focus never revealed the card"
        QTest.keyClick(banner.lock_button, Qt.Key.Key_Space)
        assert settled(
            qtbot,
            lambda: (
                not page.services.launch.busy and not page.services.status.busy and not page.busy
            ),
        )
        assert len(work.calls) == 1 and work.calls[0][2] == "lock"
        assert project.manifest.components.kcl.mode == "manual"
