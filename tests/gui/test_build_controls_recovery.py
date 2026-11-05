"""Outcome recovery and complete accessible state for the standalone build bar."""

import pytest
from test_build_controls import controls, summary

from ctstudio.gui.views.build_controls import BuildControls

pytestmark = [pytest.mark.gui, pytest.mark.timeout(10)]
__all__ = ["controls"]


def test_error_is_visible_before_a_long_warning(controls: BuildControls) -> None:
    controls.begin(False)
    controls.show_notice("Old warning: " + "long folder/" * 100)
    controls.show_error(RuntimeError("Permission denied"))
    assert controls.notice.text().startswith("Build failed: Permission denied")
    assert "Old warning" in controls.notice.toolTip()
    assert "retry" in controls.notice.text()
    assert not controls.activity.text(), "a finished failure must not still say Planning"


def test_accessibility_tracks_notice_result_retry_and_clear(controls: BuildControls) -> None:
    controls.show_notice("Path warning")
    assert controls.notice.accessibleDescription() == controls.notice.toolTip()
    controls.show_summary(summary())
    assert controls.last_result.accessibleDescription() == controls.last_result.toolTip()
    controls.begin(False)
    assert not controls.last_result.accessibleDescription()
    controls.show_error(RuntimeError("Failed to plan"))
    assert not controls.activity.accessibleDescription()
    assert controls.notice.accessibleDescription() == controls.notice.toolTip()
    controls.clear()
    for label in (controls.activity, controls.notice, controls.last_result):
        assert not label.accessibleDescription(), "old project diagnostics survive in accessibility"


def test_summary_clears_the_active_step_accessibly(controls: BuildControls) -> None:
    controls.begin(False)
    assert controls.activity.accessibleDescription()
    controls.show_summary(summary())
    assert not controls.activity.text()
    assert not controls.activity.accessibleDescription()
