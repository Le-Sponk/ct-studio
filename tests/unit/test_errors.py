"""P1-T04: typed, actionable errors with diagnostics kept separate from UI copy."""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.errors import (
    BuildError,
    Cancelled,
    CTStudioError,
    ManifestError,
    ParseError,
    ProjectError,
    ToolFailed,
    ToolNotFound,
)

pytestmark = pytest.mark.timeout(30)


def test_base_message_hint_and_details_are_separate() -> None:
    error = CTStudioError(
        "Could not open project.", hint="Choose a project folder.", details="private/path"
    )
    assert error.user_message == "Could not open project."
    assert error.hint == "Choose a project folder."
    assert error.details == "private/path"
    assert str(error) == "Could not open project.\nNext: Choose a project folder."
    assert "private/path" not in str(error)
    assert error.args == ("Could not open project.",)
    assert str(CTStudioError("No hint needed.")) == "No hint needed."


def test_tool_not_found_names_tool_and_gives_next_step() -> None:
    error = ToolNotFound("wszst")
    assert isinstance(error, CTStudioError)
    assert error.tool == "wszst"
    assert "wszst" in error.user_message
    assert "not found" in error.user_message.lower()
    assert error.hint and "install" in error.hint.lower()
    assert "Next:" in str(error)


def test_tool_failed_preserves_argv_exit_status_and_private_diagnostics(tmp_path: Path) -> None:
    log_path = tmp_path / "log é space.jsonl"
    error = ToolFailed(["rszst", "--input", "track é.dae"], 7, "SECRET: parse failed", log_path)
    assert isinstance(error, CTStudioError)
    assert error.cmd == ("rszst", "--input", "track é.dae")
    assert error.exit_code == 7
    assert error.stderr_tail == "SECRET: parse failed"
    assert error.log_path == log_path
    assert "rszst" in error.user_message and "7" in error.user_message
    assert error.hint and "log" in error.hint.lower()
    assert "SECRET" in error.details and str(log_path) in error.details
    assert "SECRET" not in str(error)


def test_tool_failed_without_log_does_not_claim_one_exists() -> None:
    error = ToolFailed(["wiimm"], 2, "bad input", None)
    assert error.log_path is None
    assert error.hint and "log" not in error.hint.lower()
    assert "bad input" in error.details


@pytest.mark.parametrize(
    ("error", "name", "attribute"),
    [
        (
            ProjectError("Project folder is missing.", hint="Select another folder."),
            "Project",
            None,
        ),
        (ManifestError("track.slot", "out of range"), "track.slot", "key_path"),
        (BuildError("assemble", "tool failed"), "assemble", "node_id"),
        (Cancelled("Build"), "Build", None),
        (ParseError("course.kmp", "bad header"), "course.kmp", None),
    ],
)
def test_other_typed_errors_explain_failure_and_next_step(
    error: CTStudioError, name: str, attribute: str | None
) -> None:
    assert isinstance(error, CTStudioError)
    assert name in error.user_message
    assert error.hint
    assert "Next:" in str(error)
    if attribute:
        assert getattr(error, attribute) == name
