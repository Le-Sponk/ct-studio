"""Parse the measured, unstructured Wiimm SZS CHECK report.

A bare opening line is not proof of a validated track: the conservative fake emits
only that prefix. Require the summary and matching finding counts before returning.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from ctstudio.core.errors import ParseError
from ctstudio.core.validation.issues import Issue, Severity

_SECTION = re.compile(r"^\* CHECK (KCL|KMP|YAZ0\.U8|U8|BRRES):(.*)$")
# Measured on a retail disc's tracks (P4-T08): "WARNING/LE-CODE" counts as a warning,
# "HINT/LE-CODE" as a hint, "SLOT" as info, and "SUGGESTION" is not in the summary at all.
_FINDING = re.compile(r"^\s*[+*\-] (WARNING|HINT|INFO|SLOT|SUGGESTION)(/LE-CODE)?:\s*(.+)$")
_SEVERITY: dict[str, Severity] = {
    "WARNING": "warning",
    "HINT": "hint",
    "INFO": "info",
    "SLOT": "info",
    "SUGGESTION": "hint",
}
_UNCOUNTED = "WSZST_SUGGESTION"
ARCHIVE = "archive"  # the component of a finding about the whole SZS, not one file in it
_MISSING = re.compile(r"^Missing file:\s+\./(.+?)(?: \(or .+\))?$")
# "=> 5 warnings, 2 hints and 1 info for", "=> no warnings and 13 hints for", "=> 1 warning for":
# the kinds present, in this order, joined by ", " and a final " and " (all measured, P4-T08).
_SUMMARY = re.compile(r"^\s*=> (.+?) for ")
_PART = re.compile(r"(no|\d+) (warning|hint|info)s?")
_KINDS = ("warning", "hint", "info")
_EMPTY = re.compile(r"CHECK (?:YAZ0\.U8|U8):(.+)")


def _issue(finding: re.Match[str], component: str) -> Issue:
    kind = finding.group(1)
    severity = _SEVERITY[kind]
    message = finding.group(3).strip()
    missing = _MISSING.match(message)
    file = Path(missing.group(1)) if missing else None
    code = "WSZST_LE_CODE" if finding.group(2) else f"WSZST_{kind}"
    return Issue(
        severity=severity,
        component=file.stem if file is not None else component,
        code="WSZST_MISSING_FILE" if file is not None else code,
        message=message,
        hint="Add the missing file to the track stage and rebuild." if file else None,
        source="wszst check",
        file=file,
    )


def _component(section: re.Match[str]) -> str:
    name = section.group(1)
    if name == "BRRES":  # "* CHECK BRRES:course_model.brres": that model
        return Path(section.group(2).strip()).stem
    return name.lower() if name in {"KCL", "KMP"} else ARCHIVE


def _counts(summary: re.Match[str]) -> tuple[int, int, int] | None:
    """The warning, hint and info counts of a summary; None for a shape wszst does not print."""
    words = summary.group(1)
    found = list(_PART.finditer(words))
    if not found or words != _sentence([part.group(0) for part in found]):
        return None
    kinds = [part.group(2) for part in found]
    if kinds != sorted(set(kinds), key=_KINDS.index):  # each kind once, in wszst's order
        return None
    number = {part.group(2): 0 if part.group(1) == "no" else int(part.group(1)) for part in found}
    warning, hint, info = (number.get(kind, 0) for kind in _KINDS)
    return warning, hint, info


def _sentence(parts: list[str]) -> str:
    """``a``, ``a and b``, ``a, b and c``: how wszst joins the counts."""
    return " and ".join([", ".join(parts[:-1]), parts[-1]]) if len(parts) > 1 else parts[0]


def _read_report(stdout: str) -> tuple[list[Issue], tuple[int, int, int] | None]:
    issues: list[Issue] = []
    component = ARCHIVE
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
    actual = Counter(issue.severity for issue in issues if issue.code != _UNCOUNTED)
    if (actual["warning"], actual["hint"], actual["info"]) != counts:
        raise ParseError(str(source), "wszst check summary does not match findings")
    return issues
