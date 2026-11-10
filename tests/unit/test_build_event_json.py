"""P4-T07b: build events as JSON lines (``core/build/event_json.py``) and the documented schema.

The schema is read from ``docs/dev/CLI.md`` itself, so the document and the output cannot
drift apart. ``json_schema_check`` is checked here too: a schema checker that passed
everything would make the rest meaningless.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from json_schema_check import errors, schema_from_doc

from ctstudio.core.build.event_json import event_to_json
from ctstudio.core.build.events import (
    BuildEvent,
    BuildFinished,
    BuildStarted,
    BuildSummary,
    CommandRun,
    LogLine,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
)
from ctstudio.core.validation.issues import Issue

CLI_DOC = Path(__file__).resolve().parents[2] / "docs" / "dev" / "CLI.md"
SCHEMA = schema_from_doc(CLI_DOC, "build-events-schema")
ROOT = Path("C:/Tracks/Pistë 日本") if Path("C:/").drive else Path("/tracks/Pistë 日本")
FOUND = Issue(
    "warning",
    "minimap",
    "WSZST_WARNING",
    "Missing bones 'posLD' and 'posRU' in minimap MDL.",
    "Open map_model.brres in an editor and fix the reported problem.",
    "wszst check",
    ROOT / "build" / "castle_course.szs",
)
SUMMARY = BuildSummary(
    "failed",
    ("stage:kcl",),
    ("stage:kmp",),
    ("validate",),
    (),
    (),
    (FOUND,),
    1.23456,
    ROOT / ".ctstudio" / "logs" / "build-1.log",
)
EVERY_EVENT: list[BuildEvent] = [
    BuildStarted(("stage:kcl", "stage:kmp", "assemble", "validate")),
    NodeStarted("stage:kcl"),
    LogLine("assemble", "castle_course.szs: 2 files"),
    CommandRun("assemble", ("C:/T/wszst.exe", "create", "a b"), 'C:/T/wszst.exe create "a b"'),
    NodeSkipped("stage:kmp", (FOUND,)),
    NodeSkipped("stage:kmp"),
    NodeFinished("stage:kcl", 0.0204, ()),
    NodeFailed("validate", "castle_course.szs has 1 error.", "Fix it.", False, (FOUND,)),
    NodeFailed("assemble", "Wiimm was cancelled.", None, True),
    BuildFinished(SUMMARY),
    BuildFinished(BuildSummary("cancelled", (), (), (), ("a",), ("b",), (), 0.0, None)),
]


@pytest.mark.parametrize("event", EVERY_EVENT, ids=lambda e: type(e).__name__)
def test_every_event_matches_the_documented_schema(event: BuildEvent) -> None:
    assert errors(event_to_json(event, ROOT), SCHEMA) == []


def test_the_fields_of_each_event() -> None:
    finished = event_to_json(BuildFinished(SUMMARY), ROOT)
    assert finished == {
        "format": 1,
        "event": "build_finished",
        "outcome": "failed",
        "ran": ["stage:kcl"],
        "skipped": ["stage:kmp"],
        "failed": ["validate"],
        "cancelled": [],
        "not_run": [],
        "issues": [
            {
                "severity": "warning",
                "component": "minimap",
                "code": "WSZST_WARNING",
                "message": "Missing bones 'posLD' and 'posRU' in minimap MDL.",
                "hint": "Open map_model.brres in an editor and fix the reported problem.",
                "source": "wszst check",
                "file": "build/castle_course.szs",
                "wiki": None,
            }
        ],
        "duration": 1.235,
        "log": ".ctstudio/logs/build-1.log",
    }
    outside = BuildSummary("succeeded", (), (), (), (), (), (), 0, Path("/elsewhere/b.log"))
    assert event_to_json(BuildFinished(outside), ROOT)["log"] == str(Path("/elsewhere/b.log"))
    assert event_to_json(NodeFinished("a", 0.0204, ()), ROOT) == {
        "format": 1,
        "event": "step_finished",
        "step": "a",
        "duration": 0.02,
        "issues": [],
    }
    assert event_to_json(NodeFailed("v", "m", "h", True), ROOT) == {
        "format": 1,
        "event": "step_failed",
        "step": "v",
        "message": "m",
        "hint": "h",
        "cancelled": True,
        "issues": [],
    }
    assert event_to_json(LogLine("s", "t"), ROOT) == {
        "format": 1,
        "event": "log",
        "step": "s",
        "text": "t",
    }
    assert event_to_json(NodeStarted("s"), ROOT) == {
        "format": 1,
        "event": "step_started",
        "step": "s",
    }
    skipped = event_to_json(NodeSkipped("s", (FOUND,)), ROOT)
    assert skipped["event"] == "step_skipped" and len(skipped["issues"]) == 1  # type: ignore[arg-type]
    started = event_to_json(BuildStarted(("a", "b")), ROOT)
    assert started == {"format": 1, "event": "build_started", "steps": ["a", "b"]}


def test_a_command_event_keeps_the_argv_and_its_text() -> None:
    command = CommandRun("s", ("/t/wszst", "x y", "<redacted>"), "/t/wszst 'x y' '<redacted>'")
    assert event_to_json(command, ROOT) == {
        "format": 1,
        "event": "command",
        "step": "s",
        "argv": ["/t/wszst", "x y", "<redacted>"],
        "text": "/t/wszst 'x y' '<redacted>'",
    }


BAD: list[tuple[str, dict[str, Any]]] = [
    ("no format", {"event": "step_started", "step": "a"}),
    ("format 2", {"format": 2, "event": "step_started", "step": "a"}),
    ("unknown event", {"format": 1, "event": "step_paused", "step": "a"}),
    ("extra field", {"format": 1, "event": "step_started", "step": "a", "x": 1}),
    ("step not text", {"format": 1, "event": "step_started", "step": 5}),
    (
        "negative time",
        {"format": 1, "event": "step_finished", "step": "a", "duration": -1, "issues": []},
    ),
    (
        "true as a number",
        {"format": 1, "event": "step_finished", "step": "a", "duration": True, "issues": []},
    ),
    (
        "bad severity",
        {
            "format": 1,
            "event": "step_skipped",
            "step": "a",
            "issues": [
                {
                    "severity": "fatal",
                    "component": "a",
                    "code": "C",
                    "message": "m",
                    "hint": None,
                    "source": "s",
                    "file": None,
                    "wiki": None,
                }
            ],
        },
    ),
    (
        "issue missing a field",
        {"format": 1, "event": "step_skipped", "step": "a", "issues": [{"severity": "error"}]},
    ),
    (
        "outcome",
        {
            "format": 1,
            "event": "build_finished",
            "outcome": "ok",
            "ran": [],
            "skipped": [],
            "failed": [],
            "cancelled": [],
            "not_run": [],
            "issues": [],
            "duration": 0,
            "log": None,
        },
    ),
]


@pytest.mark.parametrize(("why", "line"), BAD, ids=[why for why, _ in BAD])
def test_the_schema_checker_refuses_a_broken_line(why: str, line: dict[str, Any]) -> None:
    assert errors(line, SCHEMA), why


def test_the_schema_checker_refuses_keywords_it_does_not_know() -> None:
    with pytest.raises(ValueError, match="pattern"):
        errors("x", {"type": "string", "pattern": "^a"})
