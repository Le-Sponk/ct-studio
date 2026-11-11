"""Issues grouped under the track part (dashboard card) they belong to (P5-T05a).

The Issues panel and its "Copy report" read this; it never runs a tool. Which part a
finding is about is ``issue_parts.part_of``; the whole track comes last. Within a part:
errors, warnings, hints, then notes, otherwise in the order found.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ctstudio.core.build.validate import FORMAT, ISSUES_FILE
from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS
from ctstudio.core.errors import ProjectError
from ctstudio.core.validation.issue_parts import part_of
from ctstudio.core.validation.issues import Issue, Severity, issue_from_json

_ORDER: tuple[Severity, ...] = ("error", "warning", "hint", "info")
_LABEL: dict[Severity, tuple[str, str]] = {
    "error": ("Error", "error"),
    "warning": ("Warning", "warning"),
    "hint": ("Hint", "hint"),
    "info": ("Note", "note"),
}
_MARKDOWN = str.maketrans({c: f"\\{c}" for c in "\\*`[]<"})  # "_" inside a word is plain text
WHOLE_TRACK = "Whole track"


@dataclass(frozen=True)
class IssueGroup:
    part: str | None  # the card's component id; None for the whole track
    title: str
    wiki: str | None
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class IssueReport:
    groups: tuple[IssueGroup, ...]
    track: str | None = None  # the checked SZS, project-relative ("build/<slot>.szs")
    root: Path | None = None  # files inside it are shown relative to it


def group_issues(
    issues: Iterable[Issue], *, track: str | None = None, root: Path | None = None
) -> IssueReport:
    """Group by part in dashboard order (the whole track last), each sorted by severity."""
    found: dict[str | None, list[Issue]] = {}
    for issue in issues:
        found.setdefault(part_of(issue, root), []).append(issue)
    order = [spec.id for spec in COMPONENTS if spec.id in found]
    groups = [_group(part, found[part]) for part in order]
    if None in found:
        groups.append(_group(None, found[None]))
    return IssueReport(tuple(groups), track, root)


def _group(part: str | None, issues: list[Issue]) -> IssueGroup:
    ranked = tuple(sorted(issues, key=lambda issue: _ORDER.index(issue.severity)))
    if part is None:
        return IssueGroup(None, WHOLE_TRACK, None, ranked)
    spec = COMPONENT_BY_ID[part]
    return IssueGroup(part, spec.name, spec.wiki, ranked)


def counts_text(report: IssueReport) -> str:
    """``"1 error, 5 warnings and 2 notes"``; ``"no issues"`` when there are none."""
    counts = Counter(issue.severity for group in report.groups for issue in group.issues)
    words = [
        _count(counts[severity], _LABEL[severity][1]) for severity in _ORDER if counts[severity]
    ]
    if not words:
        return "no issues"
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _count(number: int, word: str) -> str:
    return f"{number} {word}{'s' if number != 1 else ''}"


def report_text(report: IssueReport, project_name: str) -> str:
    """The "Copy report" text: Markdown with every finding, its hint, file and help page."""
    lines = [f"# Issues: {_escape(project_name)}", ""]
    if report.track is not None:
        lines.append(f"Track: {_code(report.track)}  ")
    lines.append(counts_text(report) if report.groups else "No issues found.")
    for group in report.groups:
        lines += ["", f"## {group.title}", ""]
        if group.wiki is not None:
            lines += [f"Help: {group.wiki}", ""]
        lines += [_item(issue, group, report.root) for issue in group.issues]
    return "\n".join(lines) + "\n"


def _item(issue: Issue, group: IssueGroup, root: Path | None) -> str:
    parts = [f"- **{_LABEL[issue.severity][0]}:** {_escape(issue.message)}"]
    if issue.hint:
        parts.append(f"  Next: {_escape(issue.hint)}")
    if issue.file is not None:
        parts.append(f"  File: {_code(shown_file(issue.file, root))}")
    if issue.wiki and issue.wiki != group.wiki:
        parts.append(f"  Help: {_one_line(issue.wiki)}")
    return "  \n".join(parts)


def _escape(text: str) -> str:
    return " ".join(text.split()).translate(_MARKDOWN)


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _code(text: str) -> str:
    """A path as a Markdown code span that reads back as the same path: backslashes, "_" and
    inner spacing kept; line breaks become spaces. CommonMark drops one space at each end of
    a span, so one is added when an end is a space or a backtick."""
    flat = re.sub(r"\r\n|[\r\n]", " ", text)
    fence = "`" * (max(map(len, re.findall("`+", flat)), default=0) + 1)
    pad = " " if flat[:1] in ("`", " ") or flat[-1:] in ("`", " ") else ""
    return f"{fence}{pad}{flat}{pad}{fence}"


def shown_file(file: Path, root: Path | None) -> str:
    """A file inside the project relative to it ("/"), any other in full."""
    if root is not None and file.is_relative_to(root):
        return file.relative_to(root).as_posix()
    return str(file)


def load_report(root: Path) -> IssueReport | None:
    """The last check's findings from ``.ctstudio/issues.json``; None before the first one."""
    path = root / ISSUES_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        track, issues = _fields(data)
        found = [issue_from_json(item, root) for item in issues]
        _sound(track, found)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:  # e.g. deep JSON
        # (UnicodeError is a ValueError)
        raise ProjectError(
            f"The saved check results ({ISSUES_FILE}) could not be read.",
            hint="Build the track again to check it afresh.",
            details=f"{path}: {exc}",
        ) from exc
    return group_issues(found, track=track, root=root)


def _fields(data: object) -> tuple[str, list[object]]:
    if not isinstance(data, dict):
        raise TypeError("not a JSON object")
    fields = cast("dict[str, object]", data)
    form = fields.get("format")
    if type(form) is not int or form != FORMAT:  # not True or 1.0
        raise ValueError(f"unknown format {form!r}")
    track, issues = fields.get("track"), fields.get("issues")
    if not isinstance(track, str) or not track or not isinstance(issues, list):
        raise TypeError("track or issues has the wrong type")
    return track, cast("list[object]", issues)


def _sound(track: str, found: list[Issue]) -> None:
    """Text the report must hold: UTF-8 (no lone surrogates) and paths without NUL."""
    track.encode("utf-8")
    for issue in found:
        for text in (issue.message, issue.hint or "", issue.wiki or "", str(issue.file or "")):
            text.encode("utf-8")
        if "\0" in str(issue.file or ""):
            raise ValueError("a file path holds a NUL character")
