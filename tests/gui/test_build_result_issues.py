"""P5-GATE review: a build the check found errors in does not say "succeeded", and a
build error states its next step once."""

from __future__ import annotations

import pytest
from build_fakes import summary
from pytestqt.qtbot import QtBot

from ctstudio.core.errors import CTStudioError, ProjectError
from ctstudio.core.validation.issues import Issue
from ctstudio.gui.views.build_controls import BuildControls

pytestmark = [pytest.mark.gui, pytest.mark.timeout(20)]


def issue(severity: str) -> Issue:
    return Issue(severity, "kcl", "X", f"a {severity}", None, "wszst check")  # type: ignore[arg-type]


@pytest.fixture
def controls(qtbot: QtBot) -> BuildControls:
    widget = BuildControls()
    qtbot.addWidget(widget)
    return widget


def test_errors_found_by_the_check_are_named_instead_of_success(controls: BuildControls) -> None:
    errors = (issue("error"), issue("error"), issue("warning"), issue("error"))
    controls.show_summary(summary(issues=errors))
    text = controls.last_result.text()
    assert "succeeded" not in text, text
    assert text.startswith("Build finished in 0.50 s"), text
    assert "the check found 3 errors" in text and "See Issues" in text, text


def test_one_error_is_singular(controls: BuildControls) -> None:
    controls.show_summary(summary(issues=(issue("error"), issue("hint"))))
    assert "the check found 1 error:" in controls.last_result.text()


@pytest.mark.parametrize("severity", ["warning", "hint", "info"])
def test_findings_that_are_not_errors_leave_a_success(
    controls: BuildControls, severity: str
) -> None:
    controls.show_summary(summary(issues=(issue(severity),)))
    assert controls.last_result.text() == "Build succeeded in 0.50 s."


def test_a_failed_build_still_says_failed(controls: BuildControls) -> None:
    controls.show_summary(summary("failed", issues=(issue("error"),)))
    assert controls.last_result.text() == "Build failed in 0.50 s."


def test_an_error_with_its_own_next_step_is_not_told_to_retry_twice(
    controls: BuildControls,
) -> None:
    controls.show_error(ProjectError("The disk is full.", hint="Free some space, then retry."))
    text = controls.notice.text()
    assert "Next: Free some space, then retry." in text, text
    assert "Review the problem" not in text, text


@pytest.mark.parametrize("error", [CTStudioError("No hint here."), RuntimeError("boom")])
def test_an_error_without_a_next_step_gets_the_general_one(
    controls: BuildControls, error: Exception
) -> None:
    controls.show_error(error)
    assert "Review the problem and retry the build." in controls.notice.text()
