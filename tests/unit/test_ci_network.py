"""P1-T07: CI network-test summary must never hide missing preconditions."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ci_network import report_junit


def test_reports_passed_network_test_and_writes_job_summary(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        '<testsuites><testsuite tests="1" skipped="0" failures="0" errors="0">'
        '<testcase classname="tests.network" name="test_endpoint"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    summary = tmp_path / "summary.md"
    assert report_junit(xml, summary) == 0
    text = summary.read_text(encoding="utf-8")
    assert "1 passed" in text and "0 skipped" in text


def test_skip_reason_is_in_summary_and_exit_is_nonzero(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        '<testsuites><testsuite tests="2" skipped="1" failures="0" errors="0">'
        '<testcase classname="tests.network" name="test_endpoint">'
        '<skipped message="RiiStudio update endpoint unreachable"/></testcase>'
        '<testcase classname="tests.network" name="test_other"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    summary = tmp_path / "summary.md"
    assert report_junit(xml, summary) == 1
    text = summary.read_text(encoding="utf-8")
    assert "RiiStudio update endpoint unreachable" in text
    assert "test_endpoint" in text and "1 skipped" in text


def test_unrelated_collection_skip_is_shown_but_does_not_hide_a_network_pass(
    tmp_path: Path,
) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        '<testsuite tests="2" skipped="1" failures="0" errors="0">'
        '<testcase name="tests.integration.test_preview_stack">'
        '<skipped message="collection skipped">moderngl not installed</skipped></testcase>'
        '<testcase name="test_network"/></testsuite>',
        encoding="utf-8",
    )
    summary = tmp_path / "summary.md"
    assert report_junit(xml, summary) == 0
    text = summary.read_text(encoding="utf-8")
    assert "1 passed, 0 skipped" in text
    assert "moderngl not installed" in text


def test_empty_or_missing_report_is_not_green(tmp_path: Path) -> None:
    xml = tmp_path / "empty.xml"
    xml.write_text('<testsuite tests="0" skipped="0" failures="0" errors="0"/>', encoding="utf-8")
    assert report_junit(xml, None) == 1
    assert report_junit(tmp_path / "missing.xml", None) == 1


def test_failure_and_mismatched_totals_are_not_green(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        '<testsuite tests="1" skipped="0" failures="1" errors="0">'
        '<testcase name="test_failure"><failure message="failed"/></testcase></testsuite>',
        encoding="utf-8",
    )
    assert report_junit(xml, None) == 1
    xml.write_text('<testsuite tests="2"><testcase name="only_one"/></testsuite>', encoding="utf-8")
    assert report_junit(xml, None) == 1
