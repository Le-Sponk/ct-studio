"""Parse the measured, unstructured Wiimm SZS CHECK report.

A bare opening line is not proof of a validated track: the conservative fake emits
only that prefix. Require the summary and matching finding counts before returning.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import cast

from ctstudio.core.errors import ParseError
from ctstudio.core.validation.issues import Issue, Severity

_SECTION = re.compile(r"^\* CHECK (KCL|KMP|YAZ0\.U8|U8):")
_FINDING = re.compile(r"^\s*[+*\-] (WARNING|HINT|INFO):\s*(.+)$")
_MISSING = re.compile(r"^Missing file:\s+\./(.+?)(?: \(or .+\))?$")
_SUMMARY = re.compile(r"^\s*=> (\d+) warnings?(?:, (\d+) hints?)? and (\d+) info for ")
_EMPTY = re.compile(r"CHECK (?:YAZ0\.U8|U8):(.+)")


def _issue(finding: re.Match[str], component: str) -> Issue:
    severity = cast(Severity, finding.group(1).lower())
    message = finding.group(2).strip()
    missing = _MISSING.match(message)
    file = Path(missing.group(1)) if missing else None
    return Issue(
        severity=severity,
        component=file.stem if file is not None else component,
        code="WSZST_MISSING_FILE" if file is not None else f"WSZST_{severity.upper()}",
        message=message,
        hint="Add the missing file to the track stage and rebuild." if file else None,
        source="wszst check",
        file=file,
    )


def _component(section: re.Match[str]) -> str:
    name = section.group(1)
    return name.lower() if name in {"KCL", "KMP"} else "archive"


def _counts(summary: re.Match[str]) -> tuple[int, int, int]:
    return int(summary.group(1)), int(summary.group(2) or 0), int(summary.group(3))


def _read_report(stdout: str) -> tuple[list[Issue], tuple[int, int, int] | None]:
    issues: list[Issue] = []
    component = "archive"
    counts: tuple[int, int, int] | None = None
    for line in stdout.splitlines():
        if section := _SECTION.match(line):
            component = _component(section)
        elif finding := _FINDING.match(line):
            issues.append(_issue(finding, component))
        elif summary := _SUMMARY.match(line):
            counts = _counts(summary)
    return issues, counts


def _measured_empty(stdout: str, source: Path, exit_code: int | None) -> bool:
    """Wiimm 2.42a prints only ``CHECK U8:...`` for an empty stage/archive and exits 2.

    The fake prints the same prefix but exits 0; do not confuse the two.
    """
    empty = _EMPTY.fullmatch(stdout.strip())
    return exit_code == 2 and empty is not None and empty.group(1) == source.name


def parse_check(stdout: str, source: Path, *, exit_code: int | None = None) -> list[Issue]:
    """Return recorded warning/hint/info lines; never accept incomplete fake output."""
    issues, counts = _read_report(stdout)
    if counts is None:
        if _measured_empty(stdout, source, exit_code):
            return []
        raise ParseError(str(source), "wszst check summary is missing")
    actual = Counter(issue.severity for issue in issues)
    if (actual["warning"], actual["hint"], actual["info"]) != counts:
        raise ParseError(str(source), "wszst check summary does not match findings")
    return issues
