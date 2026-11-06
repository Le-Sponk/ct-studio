"""Window navigation and shortcuts do not discard or bypass the current log."""

from pathlib import Path

import pytest
from build_window_helpers import build_window, eventually, finished, started
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from pytestqt.qtbot import QtBot

from ctstudio.core.build.events import LogLine

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_hidden_dashboard_collects_and_log_focus_keeps_cancel_shortcut(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with build_window(qtbot, tmp_path) as (window, project, fake):
        log = window.dashboard.builds.log
        QTest.keyClick(window, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
        started(qtbot, window, fake)
        window.services.build.build_event.emit(LogLine("n", "Before navigation"))
        log.toggle.click()
        window.home_action.trigger()
        assert not window.dashboard.isVisible()
        window.services.build.build_event.emit(LogLine("n", "While viewing recent projects"))
        window.dashboard_action.trigger()
        assert window.dashboard.isVisible() and log.toggle.isChecked()
        assert [log.model.index(i).data() for i in range(2)] == [
            "[n] Before navigation",
            "[n] While viewing recent projects",
        ]
        log.view.setFocus()
        QTest.keyClick(log.view, Qt.Key.Key_Escape)
        eventually(qtbot, lambda: fake.cancels[0].cancelled, "Esc from log did not request cancel")
        assert fake.cancels[0].cancelled
        assert window.services.project is project and not project.read_only
        finished(qtbot, window, fake)
        assert log.model.rowCount() == 2
