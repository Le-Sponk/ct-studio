"""Turn pytest's nightly JUnit report into a visible, non-vacuous CI result.

Without ``--expected`` (ADR-022): green only when at least one test ran and nothing
failed or skipped. With ``--expected LIST --os OS`` (P2-T08a): a skip is allowed only
when LIST names it for OS with the reason it gives; any other skip, any failure, a run
where nothing passed, or a listed skip that no longer happens (so the list cannot rot)
is red. Every skip is printed with its reason in the log and the job summary.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

OSES = ("linux", "windows")


@dataclass(frozen=True)
class ExpectedSkip:
    test: str  # fnmatch pattern over "classname::name" (the module, for collection skips)
    reason: str  # must appear in the skip's reason
    why: str  # shown in the summary: why this skip is fine on this OS


def _text(entry: dict[str, object], key: str, number: int) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"skip {number}: '{key}' must be a non-empty string")
    return value


def _oses(entry: dict[str, object], number: int) -> list[str]:
    value = entry.get("os")
    if not isinstance(value, list) or not value:
        raise ValueError(f"skip {number}: 'os' must be a list such as [\"linux\"]")
    unknown = [o for o in value if o not in OSES]
    if unknown:
        raise ValueError(f"skip {number}: unknown os {unknown}; use {list(OSES)}")
    return [str(o) for o in value]


def load_expected(path: Path, os_name: str) -> tuple[ExpectedSkip, ...]:
    """The skips allowed on os_name; a malformed entry raises ValueError."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path} is not valid TOML: {exc}") from exc
    found: list[ExpectedSkip] = []
    for number, entry in enumerate(data.get("skip", []), 1):
        oses = _oses(entry, number)
        skip = ExpectedSkip(
            _text(entry, "test", number),
            _text(entry, "reason", number),
            _text(entry, "why", number),
        )
        if os_name in oses:
            found.append(skip)
    return tuple(found)


def _emit(lines: list[str], summary_path: Path | None) -> None:
    report = "\n".join(lines) + "\n"
    print(report, end="")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for line in lines:
            escaped = line.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            if line.startswith("- SKIPPED "):
                print(f"::warning title=Network test skipped::{escaped[2:]}")
            elif line.startswith("FAIL: "):
                print(f"::error title=Network test report::{escaped}")
    if summary_path is not None:
        with summary_path.open("a", encoding="utf-8") as stream:
            stream.write(report)


def _read_cases(xml_path: Path) -> tuple[list[ET.Element], str | None]:
    if not xml_path.is_file():
        return [], f"FAIL: JUnit report missing: {xml_path}"
    try:
        root = ET.parse(xml_path).getroot()  # noqa: S314 - pytest generated this local JUnit file.
    except ET.ParseError as exc:
        return [], f"FAIL: JUnit report is invalid: {exc}"
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return [], "FAIL: JUnit report has no testsuite"
    cases = list(suite.iter("testcase"))
    declared = int(suite.get("tests", "-1"))
    if declared != len(cases):
        return [], f"FAIL: JUnit declares {declared} tests but contains {len(cases)} cases"
    return cases, None


def _skip_reason(skip: ET.Element) -> str:
    reason = (skip.get("message") or "no reason supplied").strip()
    if reason == "collection skipped" and skip.text:
        return f"{reason}: {skip.text.strip()}".replace("\r", " ").replace("\n", " ")
    return reason.replace("\r", " ").replace("\n", " ")


def _summarize(cases: list[ET.Element]) -> tuple[list[str], int]:
    passed = failed = selected_skips = collection_skips = 0
    reasons: list[str] = []
    for case in cases:
        skip = case.find("skipped")
        if skip is not None:
            reason = _skip_reason(skip)
            reasons.append(f"- SKIPPED {case.get('name', '?')}: {reason}")
            if skip.get("message") == "collection skipped":
                collection_skips += 1
            else:
                selected_skips += 1
        elif case.find("failure") is not None or case.find("error") is not None:
            failed += 1
        else:
            passed += 1
    lines = [
        f"Selected tests: {passed} passed, {selected_skips} skipped, {failed} failed; "
        f"{collection_skips} unrelated collection skips.",
        *reasons,
    ]
    return _outcome(cases, collection_skips, selected_skips, failed, lines)


def _outcome(
    cases: list[ET.Element],
    collection_skips: int,
    selected_skips: int,
    failed: int,
    lines: list[str],
) -> tuple[list[str], int]:
    if len(cases) == collection_skips:
        lines.append("FAIL: no network-marked tests were collected.")
        return lines, 1
    if selected_skips or failed:
        lines.append("FAIL: network tests did not all run and pass; inspect the reasons above.")
        return lines, 1
    return lines, 0


def _case_id(case: ET.Element) -> str:
    classname, name = case.get("classname") or "", case.get("name", "?")
    return f"{classname}::{name}" if classname else name


def _match(case_id: str, reason: str, expected: Sequence[ExpectedSkip]) -> ExpectedSkip | None:
    return next(
        (e for e in expected if fnmatch.fnmatchcase(case_id, e.test) and e.reason in reason), None
    )


@dataclass
class _Tally:
    passed: int = 0
    failed: int = 0
    unlisted: list[str] = field(default_factory=lambda: [])
    listed: list[str] = field(default_factory=lambda: [])
    used: set[ExpectedSkip] = field(default_factory=lambda: set())


def _tally(cases: list[ET.Element], expected: Sequence[ExpectedSkip]) -> _Tally:
    tally = _Tally()
    for case in cases:
        skip = case.find("skipped")
        if skip is None:
            bad = case.find("failure") is not None or case.find("error") is not None
            tally.failed += bad
            tally.passed += not bad
            continue
        case_id, reason = _case_id(case), _skip_reason(skip)
        entry = _match(case_id, reason, expected)
        if entry is None:
            tally.unlisted.append(f"- SKIPPED {case_id}: {reason}")
        else:
            tally.used.add(entry)
            tally.listed.append(f"- expected skip {case_id}: {reason} ({entry.why})")
    return tally


def _against_list(
    cases: list[ET.Element], expected: Sequence[ExpectedSkip]
) -> tuple[list[str], int]:
    tally = _tally(cases, expected)
    unlisted, listed, used = tally.unlisted, tally.listed, tally.used
    state = f"{len(unlisted)} not expected" if unlisted else "all expected"
    lines = [
        f"Tests: {tally.passed} passed, {len(unlisted) + len(listed)} skipped ({state}), "
        f"{tally.failed} failed.",
        *unlisted,
        *listed,
    ]
    failures = []
    if unlisted:
        verb = "skip is" if len(unlisted) == 1 else "skips are"
        failures.append(f"FAIL: {len(unlisted)} {verb} not in the expected list.")
    stale = [e.test for e in expected if e not in used]
    if stale:
        noun = "expected skip" if len(stale) == 1 else "expected skips"
        failures.append(
            f"FAIL: {len(stale)} {noun} did not happen; remove them from the list: "
            + ", ".join(stale)
        )
    if tally.failed or not tally.passed:
        failures.append("FAIL: tests failed, or none ran; inspect the report above.")
    return [*lines, *failures], int(bool(failures))


def report_junit(
    xml_path: Path, summary_path: Path | None, *, expected: Sequence[ExpectedSkip] | None = None
) -> int:
    """Return 0 only for a run with passes and no failures or unexplained skips."""
    title = "### Nightly network tests" if expected is None else "### Nightly integration tests"
    cases, error = _read_cases(xml_path)
    if error is not None:
        _emit([title, error], summary_path)
        return 1
    lines, exit_code = _summarize(cases) if expected is None else _against_list(cases, expected)
    _emit([title, *lines], summary_path)
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report a nightly JUnit run for CI.")
    parser.add_argument("junit_xml", type=Path)
    parser.add_argument("--expected", type=Path, help="TOML list of allowed skips")
    parser.add_argument("--os", choices=OSES, help="which entries of --expected apply")
    args = parser.parse_args(argv)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    summary_path = Path(summary) if summary else None
    if args.expected is None:
        return report_junit(args.junit_xml, summary_path)
    if args.os is None:
        parser.error("--expected needs --os")
    try:
        expected = load_expected(args.expected, args.os)
    except (OSError, ValueError) as exc:
        _emit(["### Nightly integration tests", f"FAIL: expected-skip list: {exc}"], summary_path)
        return 1
    return report_junit(args.junit_xml, summary_path, expected=expected)


if __name__ == "__main__":
    sys.exit(main())
