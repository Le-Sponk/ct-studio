"""Parse measured Wiimm 2.42a CHECK text into typed, source-aware Issues."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from ctstudio.core.errors import ParseError

RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a"


def _row(name: str) -> dict[str, object]:
    import json

    rows = json.loads((RECORDINGS / "windows-ops.json").read_text(encoding="utf-8"))
    return next(row for row in rows if row["case"] == name)


def test_check_warnings_keep_component_source_and_severity() -> None:
    from ctstudio.core.validation.wszst_check import parse_check

    source = Path("track.szs")
    issues = parse_check(str(_row("check")["stdout"]), source)
    assert Counter(issue.severity for issue in issues) == {
        "warning": 5,
        "hint": 2,
        "info": 1,
    }
    assert all(issue.source == "wszst check" for issue in issues)
    assert any(issue.component == "kmp" and "opening camera" in issue.message for issue in issues)
    missing = [issue for issue in issues if issue.code == "WSZST_MISSING_FILE"]
    assert {issue.file for issue in missing} == {
        Path("course_model.brres"),
        Path("map_model.brres"),
        Path("vrcorn_model.brres"),
    }
    assert all(issue.hint for issue in missing)


def test_check_brief_drops_hints_but_preserves_warnings() -> None:
    from ctstudio.core.validation.wszst_check import parse_check

    issues = parse_check(str(_row("check brief")["stdout"]), Path("track.szs"))
    assert Counter(issue.severity for issue in issues) == {"warning": 5, "info": 1}


def test_prefix_only_fake_check_is_incomplete_not_success() -> None:
    from ctstudio.core.validation.wszst_check import parse_check

    with pytest.raises(ParseError, match="summary"):
        parse_check("\nCHECK YAZ0.U8:track.szs\n", Path("track.szs"), exit_code=0)


def test_real_empty_report_has_no_summary_but_exit_two() -> None:
    from ctstudio.core.validation.wszst_check import parse_check

    # 2.42a outputs only the CHECK prefix for an empty U8 directory/archive.
    for name, source in (("check empty directory", "empty"), ("check empty archive", "empty.szs")):
        record = _row(name)
        assert record["exit_code"] == 2
        assert parse_check(str(record["stdout"]), Path(source), exit_code=2) == []
    with pytest.raises(ParseError, match="summary"):
        parse_check("\nCHECK U8:empty\nextra output\n", Path("empty"), exit_code=2)
    with pytest.raises(ParseError, match="summary"):
        parse_check("\nCHECK U8:other\n", Path("empty"), exit_code=2)


def test_summary_count_mismatch_is_rejected() -> None:
    from ctstudio.core.validation.wszst_check import parse_check

    stdout = str(_row("check")["stdout"]).replace("=> 5 warnings", "=> 4 warnings")
    with pytest.raises(ParseError, match="does not match"):
        parse_check(stdout, Path("track.szs"))


def _report(warnings: int, hints: int, info: int, summary: str) -> str:
    lines = ["", "CHECK YAZ0.U8:track.szs", "* CHECK KMP:track.szs/course.kmp"]
    lines += [f"    + WARNING: Problem {i}." for i in range(warnings)]
    lines += [f"    - HINT: Idea {i}." for i in range(hints)]
    lines += [f"    * INFO: Fact {i}." for i in range(info)]
    return "\n".join([*lines, f" => {summary} for YAZ0.U8:track.szs", ""])


# Every summary shape wszst 2.42a printed for the tracks of a retail disc, plain and --brief
# (measured 2026-11-03, P4-T08; only these counting words are kept, nothing else from it).
MEASURED_SUMMARIES = [
    (1, 10, 0, "1 warning and 10 hints"),
    (1, 3, 1, "1 warning, 3 hints and 1 info"),
    (13, 10, 0, "13 warnings and 10 hints"),
    (7, 1, 0, "7 warnings and 1 hint"),
    (0, 13, 0, "no warnings and 13 hints"),
    (0, 4, 1, "no warnings, 4 hints and 1 info"),
    (1, 0, 0, "1 warning"),
    (16, 0, 0, "16 warnings"),
    (1, 0, 1, "1 warning and 1 info"),
    (5, 2, 1, "5 warnings, 2 hints and 1 info"),
    (6, 2, 0, "6 warnings and 2 hints"),  # also a synthetic stage with only course.kmp
]


@pytest.mark.parametrize(("warnings", "hints", "info", "summary"), MEASURED_SUMMARIES)
def test_every_measured_summary_shape_is_read(
    warnings: int, hints: int, info: int, summary: str
) -> None:
    from ctstudio.core.validation.wszst_check import parse_check

    issues = parse_check(_report(warnings, hints, info, summary), Path("track.szs"), exit_code=2)
    assert (
        Counter(issue.severity for issue in issues)
        == Counter({"warning": warnings, "hint": hints, "info": info}) - Counter()
    )


@pytest.mark.parametrize(
    "summary",
    [
        "2 warnings and 10 hints",  # one warning too many
        "1 warning and 9 hints",  # one hint too few
        "1 warning, 10 hints and 2 info",  # info that is not there
        "no warnings and 10 hints",  # a warning that is there
    ],
)
def test_a_summary_that_disagrees_with_the_findings_is_rejected(summary: str) -> None:
    from ctstudio.core.validation.wszst_check import parse_check

    with pytest.raises(ParseError, match="does not match"):
        parse_check(_report(1, 10, 0, summary), Path("track.szs"), exit_code=2)


@pytest.mark.parametrize(
    "summary",
    [
        "1 warning and 10 notes",  # a kind wszst does not print
        "1 warning and 10",
        "some warnings",
        "1 warning, and 10 hints",
        "1 warning, 10 hints",  # wszst joins the last two with " and "
        "1 warning and 10 hints and 1 info",  # ... and the others with ", "
        "10 hints and 1 warning",  # always warnings, then hints, then info
        "1 warning, 5 hints and 5 hints",  # each kind once
        "",
    ],
)
def test_a_summary_in_an_unknown_shape_is_not_read(summary: str) -> None:
    from ctstudio.core.validation.wszst_check import parse_check

    with pytest.raises(ParseError, match="summary is missing"):
        parse_check(_report(1, 10, 0, summary), Path("track.szs"), exit_code=2)


def test_le_code_slot_and_suggestion_lines_are_read_as_wszst_counts_them() -> None:
    """Measured on a retail disc's tracks (P4-T08): ``WARNING/LE-CODE`` counts as a warning,
    ``HINT/LE-CODE`` as a hint, ``SLOT`` as info; a ``SUGGESTION`` is not counted at all."""
    from ctstudio.core.validation.wszst_check import parse_check

    stdout = "\n".join(
        [
            "",
            "CHECK YAZ0.U8:track.szs",
            "* CHECK BRRES:course_model.brres",
            "    + WARNING: A model problem.",
            "* CHECK KMP:track.szs/course.kmp",
            "    + WARNING/LE-CODE: Distance KTPT #0 and CKPT #0 is large.",
            "    - HINT/LE-CODE: Distance KTPT #0 and CKPT #0 is small.",
            "    - HINT: A hint.",
            "    * SLOT: Track will only run at some slots.",
            "    * SUGGESTION: Try something.",
            " => 2 warnings, 2 hints and 1 info for YAZ0.U8:track.szs",
            "",
        ]
    )
    issues = parse_check(stdout, Path("track.szs"), exit_code=2)
    found = {(i.severity, i.code, i.component, i.message) for i in issues}
    assert found == {
        ("warning", "WSZST_WARNING", "course_model", "A model problem."),
        ("warning", "WSZST_LE_CODE", "kmp", "Distance KTPT #0 and CKPT #0 is large."),
        ("hint", "WSZST_LE_CODE", "kmp", "Distance KTPT #0 and CKPT #0 is small."),
        ("hint", "WSZST_HINT", "kmp", "A hint."),
        ("info", "WSZST_SLOT", "kmp", "Track will only run at some slots."),
        ("hint", "WSZST_SUGGESTION", "kmp", "Try something."),
    }
    assert len(issues) == 6


def test_a_suggestion_does_not_make_the_counts_disagree() -> None:
    from ctstudio.core.validation.wszst_check import parse_check

    stdout = _report(1, 0, 0, "1 warning").replace(
        " => ", "    * SUGGESTION: Try something.\n    * SUGGESTION: Or this.\n => "
    )
    issues = parse_check(stdout, Path("track.szs"), exit_code=2)
    assert [i.code for i in issues] == ["WSZST_WARNING", "WSZST_SUGGESTION", "WSZST_SUGGESTION"]
    with pytest.raises(ParseError, match="does not match"):  # suggestions are not hints
        parse_check(stdout.replace("=> 1 warning", "=> 1 warning and 2 hints"), Path("track.szs"))
