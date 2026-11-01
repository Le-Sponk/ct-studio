"""P1-T07: CI network-test summary must never hide missing preconditions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ci_network import ExpectedSkip, load_expected, report_junit


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


def test_ci_exposes_exact_skip_as_public_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        '<testsuite tests="1"><testcase name="test_riistudio">'
        '<skipped message="wine not installed"/></testcase></testsuite>',
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert report_junit(xml, None) == 1
    output = capsys.readouterr().out
    assert (
        "::warning title=Network test skipped::SKIPPED test_riistudio: wine not installed" in output
    )


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


# --- P2-T08a: the integration run's list of skips that are allowed, per OS ---------------------

_TWO = (
    '<testsuite tests="3" skipped="2" failures="0" errors="0">'
    '<testcase classname="tests.integration.test_wine_editors" name="test_lorenzi">'
    '<skipped type="pytest.skip" message="needs Linux desktop, Wine, wmctrl">'
    "tests/integration/test_wine_editors.py:102: needs Linux desktop, Wine, wmctrl</skipped>"
    "</testcase>"
    '<testcase classname="" name="tests.integration.test_preview_stack">'
    '<skipped message="collection skipped">moderngl not installed</skipped></testcase>'
    '<testcase classname="tests.integration.test_wiimm_adapter" name="test_real"/>'
    "</testsuite>"
)


def _expected(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "expected é.toml"
    path.write_text(text, encoding="utf-8")
    return path


_LIST = """
[[skip]]
os = ["windows"]
test = "tests.integration.test_wine_editors::test_lorenzi"
reason = "needs Linux desktop"
why = "Wine editors are a Linux route."

[[skip]]
os = ["windows", "linux"]
test = "tests.integration.test_preview_stack"
reason = "moderngl not installed"
why = "The preview stack is optional until Phase 9."
"""


def test_listed_skips_with_their_reasons_are_green(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(_TWO, encoding="utf-8")
    summary = tmp_path / "summary.md"
    expected = load_expected(_expected(tmp_path, _LIST), "windows")
    assert report_junit(xml, summary, expected=expected) == 0
    text = summary.read_text(encoding="utf-8")
    assert "1 passed, 2 skipped (all expected), 0 failed" in text
    assert "- expected skip tests.integration.test_wine_editors::test_lorenzi" in text
    assert "Wine editors are a Linux route." in text


def test_an_unlisted_skip_is_red(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(_TWO, encoding="utf-8")
    expected = load_expected(_expected(tmp_path, _LIST), "linux")  # lorenzi is Windows-only
    summary = tmp_path / "summary.md"
    assert report_junit(xml, summary, expected=expected) == 1
    text = summary.read_text(encoding="utf-8")
    assert "- SKIPPED tests.integration.test_wine_editors::test_lorenzi: needs Linux" in text
    assert "FAIL: 1 skip is not in the expected list" in text


def test_a_listed_skip_with_another_reason_is_red(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(_TWO.replace("moderngl not installed", "no GL context"), encoding="utf-8")
    expected = load_expected(_expected(tmp_path, _LIST), "windows")
    assert report_junit(xml, None, expected=expected) == 1


def test_a_listed_skip_that_no_longer_happens_is_red_so_the_list_cannot_rot(
    tmp_path: Path,
) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        '<testsuite tests="1"><testcase classname="tests.integration.test_wiimm_adapter"'
        ' name="test_real"/></testsuite>',
        encoding="utf-8",
    )
    summary = tmp_path / "summary.md"
    expected = load_expected(_expected(tmp_path, _LIST), "windows")
    assert report_junit(xml, summary, expected=expected) == 1
    text = summary.read_text(encoding="utf-8")
    assert "FAIL: 2 expected skips did not happen; remove them from the list:" in text
    assert "tests.integration.test_preview_stack" in text


def test_a_run_where_everything_skips_is_still_red(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        _TWO.replace('tests="3" skipped="2"', 'tests="2" skipped="2"').replace(
            '<testcase classname="tests.integration.test_wiimm_adapter" name="test_real"/>', ""
        ),
        encoding="utf-8",
    )
    expected = load_expected(_expected(tmp_path, _LIST), "windows")
    assert report_junit(xml, None, expected=expected) == 1


def test_patterns_cover_parametrised_tests(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        '<testsuite tests="3"><testcase classname="tests.integration.test_x" name="test_a[1]">'
        '<skipped message="slow tool"/></testcase>'
        '<testcase classname="tests.integration.test_x" name="test_a[2]">'
        '<skipped message="slow tool"/></testcase>'
        '<testcase classname="tests.integration.test_y" name="test_b"/></testsuite>',
        encoding="utf-8",
    )
    listed = _expected(
        tmp_path,
        '[[skip]]\nos = ["linux"]\ntest = "tests.integration.test_x::test_a[[]*]"\n'
        'reason = "slow tool"\nwhy = "Not on CI."\n',
    )
    assert report_junit(xml, None, expected=load_expected(listed, "linux")) == 0


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ('[[skip]]\nos = ["windows"]\ntest = "t"\nreason = "r"\n', "why"),
        ('[[skip]]\nos = ["mac"]\ntest = "t"\nreason = "r"\nwhy = "w"\n', "mac"),
        ('[[skip]]\nos = "linux"\ntest = "t"\nreason = "r"\nwhy = "w"\n', "'os' must be a list"),
        ('[[skip]]\nos = ["linux"]\ntest = ""\nreason = "r"\nwhy = "w"\n', "test"),
        ('[[skip]]\nos = ["linux"]\ntest = "t"\nreason = 3\nwhy = "w"\n', "reason"),
        ("not toml [", "TOML"),
    ],
)
def test_a_bad_list_is_rejected_with_the_reason(tmp_path: Path, text: str, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        load_expected(_expected(tmp_path, text), "linux")


def test_load_keeps_only_this_os(tmp_path: Path) -> None:
    linux = load_expected(_expected(tmp_path, _LIST), "linux")
    assert linux == (
        ExpectedSkip(
            "tests.integration.test_preview_stack",
            "moderngl not installed",
            "The preview stack is optional until Phase 9.",
        ),
    )


def test_the_command_line_takes_the_list_and_the_os(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ci_network import main

    xml = tmp_path / "results.xml"
    xml.write_text(_TWO, encoding="utf-8")
    listed = _expected(tmp_path, _LIST)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert main([str(xml), "--expected", str(listed), "--os", "windows"]) == 0
    assert main([str(xml), "--expected", str(listed), "--os", "linux"]) == 1
    assert main([str(xml), "--expected", str(tmp_path / "missing.toml"), "--os", "linux"]) == 1


def test_the_same_reason_on_another_test_is_not_covered(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        '<testsuite tests="2"><testcase classname="tests.integration.test_other" name="test_a">'
        '<skipped message="moderngl not installed"/></testcase>'
        '<testcase classname="tests.integration.test_y" name="test_b"/></testsuite>',
        encoding="utf-8",
    )
    listed = _expected(
        tmp_path,
        '[[skip]]\nos = ["linux"]\ntest = "tests.integration.test_preview_stack"\n'
        'reason = "moderngl not installed"\nwhy = "Optional."\n',
    )
    summary = tmp_path / "summary.md"
    assert report_junit(xml, summary, expected=load_expected(listed, "linux")) == 1
    text = summary.read_text(encoding="utf-8")
    assert "- SKIPPED tests.integration.test_other::test_a" in text
    assert "FAIL: 1 skip is not in the expected list." in text


def test_a_failure_is_red_even_when_every_skip_is_listed(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        _TWO.replace('tests="3"', 'tests="4"').replace(
            "</testsuite>",
            '<testcase classname="tests.integration.test_z" name="test_c">'
            '<failure message="boom"/></testcase></testsuite>',
        ),
        encoding="utf-8",
    )
    summary = tmp_path / "summary.md"
    expected = load_expected(_expected(tmp_path, _LIST), "windows")
    assert report_junit(xml, summary, expected=expected) == 1
    text = summary.read_text(encoding="utf-8")
    assert "Tests: 1 passed, 2 skipped (all expected), 1 failed." in text
    assert "FAIL: tests failed, or none ran" in text
