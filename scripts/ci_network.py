"""Turn pytest's nightly network JUnit report into a visible, non-vacuous CI result."""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path


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


def report_junit(xml_path: Path, summary_path: Path | None) -> int:
    """Return 0 only when at least one network test ran and none failed or skipped."""
    cases, error = _read_cases(xml_path)
    if error is not None:
        _emit(["### Nightly network tests", error], summary_path)
        return 1
    lines, exit_code = _summarize(cases)
    _emit(["### Nightly network tests", *lines], summary_path)
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit_xml", type=Path)
    args = parser.parse_args(argv)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    return report_junit(args.junit_xml, Path(summary) if summary else None)


if __name__ == "__main__":
    sys.exit(main())
