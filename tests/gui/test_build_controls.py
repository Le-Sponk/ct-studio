"""P5-T03e21: signal-only build controls, before dashboard integration."""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING

from ctstudio.core.build.events import (
    BuildEvent,
    BuildFinished,
    BuildStarted,
    BuildSummary,
    LogLine,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
)
from ctstudio.core.errors import BuildError, CTStudioError

if TYPE_CHECKING:
    from ctstudio.gui.views.build_controls import BuildControls

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

pytestmark = [pytest.mark.gui, pytest.mark.timeout(10)]


@pytest.fixture
def controls(qtbot: QtBot) -> BuildControls:
    from ctstudio.gui.views.build_controls import BuildControls

    widget = BuildControls()
    qtbot.addWidget(widget)
    widget.show()
    return widget


def assert_planning(controls: BuildControls, mode: str) -> None:
    assert controls.progress.minimum() == controls.progress.maximum() == 0
    assert "planning" in controls.activity.text().lower()
    assert mode in controls.activity.text().lower()


def assert_cancelling(controls: BuildControls) -> None:
    assert controls.activity.text() == "Cancelling…"
    assert not controls.cancel_button.isEnabled()
    assert not controls.progress.isHidden()
    assert not controls.test_button.isEnabled()


def test_cancel_emits_once_until_new_run(controls: BuildControls) -> None:
    cancelled = QSignalSpy(controls.cancel_requested)
    controls.begin(release=False)
    assert_planning(controls, "test")
    controls.cancel_button.click()
    controls.cancel_button.click()
    assert cancelled.count() == 1
    assert_cancelling(controls)
    controls.set_state(enabled=True, running=True)
    assert_cancelling(controls)
    controls.set_state(enabled=True, running=False)
    assert controls.progress.isHidden()
    assert controls.test_button.isEnabled()
    controls.begin(release=True)
    assert_planning(controls, "release")
    assert controls.cancel_button.isEnabled()
    controls.cancel_button.click()
    assert cancelled.count() == 2


def summary(outcome: str = "succeeded") -> BuildSummary:
    from typing import cast

    from ctstudio.core.build.events import Outcome

    return BuildSummary(
        cast(Outcome, outcome), (), (), (), (), (), (), 12.25, Path("é logs/build.log")
    )


@pytest.mark.parametrize(
    "terminal",
    [
        NodeFinished("archive", 1.0, ()),
        NodeSkipped("archive"),
        NodeFailed("archive", "Bad input", "Fix source", False),
        NodeFailed("archive", "Stopped", None, True),
    ],
)
def test_event_progress_counts_unique_known_steps(
    controls: BuildControls, terminal: BuildEvent
) -> None:
    controls.begin(release=False)
    controls.show_event(BuildStarted(("model", "archive")))
    assert controls.progress.maximum() == 2
    assert controls.progress.value() == 0
    controls.show_event(NodeStarted("archive"))
    assert "archive" in controls.activity.text()
    assert "ready" not in controls.activity.text().lower()
    controls.show_event(terminal)
    controls.show_event(terminal)
    assert controls.progress.value() == 1
    controls.show_event(NodeSkipped("model"))
    assert controls.progress.value() == 2
    assert not controls.last_result.text()
    assert not controls.progress.isHidden()
    controls.begin(release=True)
    controls.show_event(BuildStarted(("archive",)))
    controls.show_event(NodeSkipped("archive"))
    assert controls.progress.value() == 1


def test_unknown_and_nonterminal_events_do_not_finish_build(controls: BuildControls) -> None:
    controls.begin(release=False)
    controls.show_event(NodeStarted("archive"))
    assert_planning(controls, "test")
    controls.show_event(BuildStarted(("archive",)))
    controls.show_event(NodeStarted("archive"))
    activity = controls.activity.text()
    controls.show_event(LogLine("archive", "archive ready <b>raw</b>"))
    controls.show_event(BuildFinished(summary()))
    controls.show_event(NodeStarted("unknown"))
    controls.show_event(NodeFinished("unknown", 0, ()))
    assert controls.activity.text() == activity
    assert controls.progress.value() == 0
    assert not controls.last_result.text()


def test_cancellation_activity_survives_events(controls: BuildControls) -> None:
    controls.begin(release=False)
    controls.cancel_button.click()
    controls.show_event(BuildStarted(("archive",)))
    controls.show_event(NodeStarted("archive"))
    controls.show_event(NodeFailed("archive", "Stopped", None, True))
    assert controls.progress.value() == 1
    assert controls.activity.text() == "Cancelling…"
    assert controls.last_result.text() == ""
    assert not controls.cancel_button.isEnabled()


def test_empty_build_has_known_zero_progress(controls: BuildControls) -> None:
    controls.begin(release=False)
    controls.show_event(BuildStarted(()))
    assert controls.progress.maximum() > 0
    assert controls.progress.value() == 0
    assert "0/0" in controls.progress.text()
    assert not controls.last_result.text()


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled"])
def test_joined_summary_and_warning_are_independent(controls: BuildControls, outcome: str) -> None:
    controls.show_notice("History <b>warning</b>: retry saving history")
    controls.begin(release=False)
    controls.show_summary(summary(outcome))
    assert outcome in controls.last_result.text().lower()
    if outcome != "succeeded":
        assert "succeeded" not in controls.last_result.text().lower()
    assert "12.25" in controls.last_result.text()
    assert str(summary().log) in controls.last_result.toolTip()
    controls.set_state(enabled=True, running=False)
    assert "warning" in controls.notice.text()
    controls.begin(release=True)
    assert not controls.last_result.text()
    assert not controls.last_result.toolTip()
    assert "warning" in controls.notice.text()


def test_clear_discards_project_presentation(controls: BuildControls) -> None:
    controls.show_notice("Old warning")
    controls.begin(release=False)
    controls.cancel_button.click()
    controls.show_summary(summary())
    controls.clear()
    for label in (controls.activity, controls.notice, controls.last_result):
        assert not label.text()
        assert not label.toolTip()
    assert_empty_progress(controls)
    assert not controls.test_button.isEnabled()
    assert not controls.cancel_button.isEnabled()
    controls.begin(release=False)
    assert not controls.notice.text(), "a cleared project's warning returned during the next build"
    assert controls.cancel_button.isEnabled()


def assert_empty_progress(controls: BuildControls) -> None:
    assert controls.progress.isHidden()
    assert controls.progress.minimum() == controls.progress.value() == 0
    assert controls.progress.maximum() == 1


def test_summary_without_log_is_explicit(controls: BuildControls) -> None:
    result = BuildSummary("succeeded", (), (), (), (), (), (), 0.5, None)
    controls.show_summary(result)
    assert "succeeded" in controls.last_result.text().lower()
    assert "unavailable" in controls.last_result.toolTip().lower()
    assert "None" not in controls.last_result.text()


@pytest.mark.parametrize(
    "error",
    [
        BuildError("archive", "<b>bad</b>"),
        RuntimeError(),
        ValueError("bad input"),
        KeyboardInterrupt(),
        SystemExit(),
    ],
)
def test_actionable_errors_reset_without_erasing_warning(
    controls: BuildControls, error: BaseException
) -> None:
    controls.show_notice("Keep this warning")
    controls.begin(release=False)
    controls.show_error(error)
    text = controls.notice.text()
    assert (str(error) or type(error).__name__) in text
    assert "Keep this warning" in text
    assert "retry" in text.lower()
    if not isinstance(error, Exception):
        assert "interrupt" in text.lower()
    if isinstance(error, CTStudioError):
        assert str(error) in text
    controls.show_notice("Replacement warning")
    assert (str(error) or type(error).__name__) in controls.notice.text()
    controls.set_state(enabled=True, running=False)
    controls.begin(release=True)
    assert controls.notice.text() == "Replacement warning"


def test_node_failure_shows_hint_not_private_details(controls: BuildControls) -> None:
    controls.begin(release=False)
    controls.show_event(BuildStarted(("archive",)))
    controls.show_event(NodeFailed("unknown", "ignore", None, False))
    assert not controls.notice.text()
    controls.show_event(
        NodeFailed("archive", "<b>Bad source</b>", "Fix source", False, details="PRIVATE stderr")
    )
    assert "<b>Bad source</b>" in controls.notice.text()
    assert "Fix source" in controls.notice.text()
    assert "PRIVATE" not in controls.notice.text()
    controls.show_summary(summary("failed"))
    assert "Fix source" in controls.notice.text()
    controls.begin(release=False)
    assert not controls.notice.text()


def test_shortcut_metadata(controls: BuildControls) -> None:
    for button, shortcut in (
        (controls.test_button, "Ctrl+B"),
        (controls.release_button, "Ctrl+Shift+B"),
        (controls.cancel_button, "Esc"),
    ):
        assert button.shortcut().toString() == shortcut
        assert shortcut in button.toolTip()
        assert shortcut in button.accessibleDescription()


def test_shortcuts_obey_visibility_and_run_state(controls: BuildControls, qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QApplication

    requested = QSignalSpy(controls.build_requested)
    cancelled = QSignalSpy(controls.cancel_requested)
    controls.activateWindow()
    controls.set_state(enabled=True, running=False)
    with qtbot.waitSignal(controls.build_requested):
        QTest.keyClick(controls, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert requested.count() == 1
    assert requested.at(0) == [False]
    controls.hide()
    QTest.keyClick(controls, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    controls.show()
    controls.set_state(enabled=False, running=False)
    QTest.keyClick(controls, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    controls.set_state(enabled=True, running=False)
    with qtbot.waitSignal(controls.build_requested):
        QTest.keyClick(
            controls,
            Qt.Key.Key_B,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
    assert requested.count() == 2
    assert requested.at(1) == [True]
    controls.begin(release=False)
    QTest.keyClick(controls, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    with qtbot.waitSignal(controls.cancel_requested):
        QTest.keyClick(controls, Qt.Key.Key_Escape)
    QTest.keyClick(controls, Qt.Key.Key_Escape)
    controls.set_state(enabled=True, running=True)
    assert cancelled.count() == 1
    assert requested.count() == 2
    assert not controls.cancel_button.isEnabled()


def test_labels_are_bounded_plain_text_with_full_tooltips(controls: BuildControls) -> None:
    text = "<b>source</b>/" + "é" * 2000
    controls.show_notice(text)
    controls.begin(release=False)
    controls.show_event(BuildStarted((text,)))
    controls.show_event(NodeStarted(text))
    controls.show_summary(BuildSummary("failed", (), (), (), (), (), (), 1, Path(text)))
    for label in (controls.activity, controls.notice, controls.last_result):
        assert label.textFormat() == Qt.TextFormat.PlainText
        assert label.wordWrap()
        assert label.maximumHeight() <= label.fontMetrics().lineSpacing() * 4 + 8
        assert label.text() in label.toolTip()
    assert text in controls.notice.toolTip()
    assert str(Path(text)) in controls.last_result.toolTip()
    assert controls.styleSheet() == ""


def test_build_controls_signal_state(qtbot: QtBot) -> None:
    assert find_spec("ctstudio.gui.views.build_controls") is not None, "BuildControls is missing"
    from ctstudio.gui.views.build_controls import BuildControls

    parent = QWidget()
    qtbot.addWidget(parent)
    controls = BuildControls(parent)
    parent.show()
    controls.show()
    requested = QSignalSpy(controls.build_requested)
    controls.set_state(enabled=False, running=False)
    controls.test_button.click()
    assert requested.count() == 0
    assert not controls.cancel_button.isEnabled()
    assert controls.progress.isHidden()
    controls.set_state(enabled=True, running=False)
    controls.test_button.click()
    controls.release_button.click()
    assert requested.count() == 2
    assert requested.at(0) == [False]
    assert requested.at(1) == [True]
    controls.set_state(enabled=False, running=True)
    assert_running(controls)


def assert_running(controls: BuildControls) -> None:
    assert not controls.test_button.isEnabled()
    assert not controls.release_button.isEnabled()
    assert controls.cancel_button.isEnabled()
    assert not controls.progress.isHidden()


def test_ancestor_disabled_state_is_not_cached(qtbot: QtBot) -> None:
    from ctstudio.gui.views.build_controls import BuildControls

    parent = QWidget()
    qtbot.addWidget(parent)
    controls = BuildControls(parent)
    parent.setEnabled(False)
    controls.set_state(enabled=True, running=False)
    parent.setEnabled(True)
    assert controls.test_button.isEnabled()
    assert controls.release_button.isEnabled()


def test_widget_names(controls: BuildControls) -> None:
    assert controls.test_button.text() == "Build test"
    assert controls.release_button.text() == "Build release"
    assert controls.cancel_button.text() == "Cancel build"
    for widget, name in (
        (controls.test_button, "buildTest"),
        (controls.release_button, "buildRelease"),
        (controls.cancel_button, "cancelBuild"),
        (controls.progress, "buildProgress"),
        (controls.notice, "buildNotice"),
        (controls.last_result, "buildLastResult"),
        (controls.activity, "buildActivity"),
    ):
        assert widget.objectName() == name
