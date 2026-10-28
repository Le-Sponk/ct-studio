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
