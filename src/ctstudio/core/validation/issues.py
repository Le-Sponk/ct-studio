"""Structured validation results shared by CLI and GUI without Qt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast, get_args

Severity = Literal["error", "warning", "hint", "info"]
_SEVERITIES: tuple[str, ...] = get_args(Severity)
_TEXT = ("component", "code", "message", "source")
_OPTIONAL = ("hint", "wiki")


@dataclass(frozen=True)
class Issue:
    severity: Severity
    component: str
    code: str
    message: str
    hint: str | None
    source: str
    file: Path | None = None
    wiki: str | None = None


def issue_to_json(issue: Issue, root: Path) -> dict[str, object]:
    """Plain JSON; a file inside ``root`` is stored relative to it ("/"), others absolute."""
    file = None
    if issue.file is not None:
        inside = issue.file.is_relative_to(root)
        file = issue.file.relative_to(root).as_posix() if inside else str(issue.file)
    return {
        "severity": issue.severity,
        **{name: getattr(issue, name) for name in _TEXT},
        "hint": issue.hint,
        "file": file,
        "wiki": issue.wiki,
    }


def issue_from_json(data: object, root: Path) -> Issue:
    """The ``Issue`` that ``issue_to_json`` wrote; TypeError/ValueError/KeyError if damaged."""
    if not isinstance(data, dict):
        raise TypeError("an issue is not a JSON object")
    fields = cast("dict[str, object]", data)
    severity = fields["severity"]
    if severity not in _SEVERITIES:
        raise ValueError(f"unknown severity {severity!r}")
    text = {name: _text(fields, name) for name in _TEXT}
    optional = {name: _optional(fields, name) for name in _OPTIONAL}
    file = _optional(fields, "file")
    if file == "":
        raise ValueError("an empty file path")
    return Issue(
        cast(Severity, severity),
        text["component"],
        text["code"],
        text["message"],
        optional["hint"],
        text["source"],
        None if file is None else root / file,  # an absolute path replaces root
        optional["wiki"],
    )


def _text(fields: dict[str, object], name: str) -> str:
    value = fields[name]
    if not isinstance(value, str):
        raise TypeError(f"{name} is not text")
    return value


def _optional(fields: dict[str, object], name: str) -> str | None:
    value = fields.get(name)
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{name} is not text")
    return value
