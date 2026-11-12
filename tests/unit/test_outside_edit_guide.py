"""P5-T06c2b2c1: user-facing outside-edit instructions and uncertain-start wording."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/user/PROJECT_NAVIGATION.md"
HEADING = "## Keeping or discarding an outside edit"


def _outside() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    assert HEADING in text, "The guide needs actionable outside-edit instructions"
    section = text.split(HEADING, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]
    return " ".join(section.replace("`", "").lower().split())


def test_intro_describes_available_assignment_without_promising_generation() -> None:
    intro = " ".join(GUIDE.read_text(encoding="utf-8").split("## New project")[0].split())
    assert "GUI file assignment are not ready" not in intro
    assert "file assignment are available" in intro
    assert "Automatic generation is not ready yet" in intro


@pytest.mark.parametrize(
    "wording",
    [
        "edited outside ct studio",
        "lock as manual",
        "discard…",
        "about two seconds",
        "project is open and its folders can be watched",
        "refresh statuses",
        "not for parts already using manual mode",
    ],
)
def test_guide_explains_when_choices_appear(wording: str) -> None:
    assert wording in _outside()


@pytest.mark.parametrize(
    "wording",
    [
        "exact copy",
        "files/",
        "manual",
        "ctstudio.toml",
        "different copy already in files/",
        "backed up",
        "identical copy",
    ],
)
def test_guide_explains_lock_and_existing_file_protection(wording: str) -> None:
    assert wording in _outside()


@pytest.mark.parametrize(
    "wording",
    [
        "discard outside edit?",
        "cancel is the default",
        "cancel changes nothing",
        ".ctstudio/backups/<utc time>/",
        "removes it from .ctstudio/stage/",
        "next build",
        "does not start a build",
    ],
)
def test_guide_explains_confirmed_discard_not_immediate_regeneration(wording: str) -> None:
    assert wording in _outside()


@pytest.mark.parametrize(
    "wording",
    [
        "read-only",
        "statuses are being checked",
        "build",
        "edit dialog",
        "launch",
        "project lock",
        "worker has finished and been joined",
        "each card has its own",
        "hover",
        "screen readers",
    ],
)
def test_guide_explains_busy_ownership_and_independent_outcomes(wording: str) -> None:
    assert wording in _outside()


@pytest.mark.parametrize(
    "wording",
    [
        "failure does not mean rollback",
        "may already have changed files",
        "reloads the actual saved project",
        "check this card before trying again",
        "saved project could not be read",
        "read-only while keeping its lock",
        "close ct studio and reopen this project",
        "fresh saved state",
    ],
)
def test_guide_explains_uncertain_start_and_unsafe_saved_state(wording: str) -> None:
    assert wording in _outside()


def test_guide_retains_keyboard_future_capture_and_linux_limits() -> None:
    text = _outside()
    for wording in ("tab", "space", "escape", "capture", "p7", "linux desktop appearance"):
        assert wording in text
    assert "not verified" in text
    assert "no capture button" in text


def test_start_docstring_does_not_treat_false_as_cancellation() -> None:
    tree = ast.parse((ROOT / "src/ctstudio/gui/launch_controller.py").read_text(encoding="utf-8"))
    controller = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LaunchController"
    )
    start = next(n for n in controller.body if isinstance(n, ast.FunctionDef) and n.name == "start")
    text = " ".join((ast.get_docstring(start) or "").lower().split())
    for wording in (
        "false",
        "not cancellation or rollback",
        "after dispatch",
        "busy",
        "joined",
        "completed",
    ):
        assert wording in text
