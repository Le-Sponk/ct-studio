"""P5-T05a: issues grouped under the track part (card) they belong to, for the Issues panel.

Built from the recorded real ``wszst check`` output (2.42a) and from an ``issues.json`` the
validate step writes. Each finding belongs to the part named by its id, by one of the part's
files (including ``_d`` variants and files inside a folder part), or by the model a check
section names; the rest are about the whole track. Within a part: errors, warnings, hints,
then notes, otherwise in the order found.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest
from test_build_validate import CHECK, Wiimm, run

from ctstudio.core.build.validate import ISSUES_FILE
from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.errors import ProjectError
from ctstudio.core.validation.issues import Issue
from ctstudio.core.validation.report import (
    IssueReport,
    counts_text,
    group_issues,
    load_report,
    report_text,
)

pytestmark = pytest.mark.timeout(60)


def issue(
    severity: str = "warning",
    component: str = "archive",
    message: str = "Something.",
    *,
    file: Path | None = None,
    hint: str | None = None,
    wiki: str | None = None,
) -> Issue:
    return Issue(severity, component, "X", message, hint, "test", file, wiki)  # type: ignore[arg-type]


def parts(report: IssueReport) -> list[str | None]:
    return [group.part for group in report.groups]


def test_the_recorded_check_lands_under_each_part_in_dashboard_order() -> None:
    report = group_issues(CHECK)
    assert parts(report) == ["course_model", "kcl", "minimap", "skybox", "kmp"]
    by_part = {group.part: group for group in report.groups}
    assert [i.severity for i in by_part["kmp"].issues] == ["warning", "warning", "hint", "hint"]
    assert "opening camera" in by_part["kmp"].issues[0].message
    assert [i.severity for i in by_part["kcl"].issues] == ["info"]
    for part, name in (
        ("course_model", "course_model"),
        ("minimap", "map_model"),
        ("skybox", "vrcorn_model"),
    ):
        [missing] = by_part[part].issues
        assert missing.file == Path(f"{name}.brres")
    assert sum(len(group.issues) for group in report.groups) == len(CHECK) == 8


def test_each_group_has_the_cards_name_and_wiki_page() -> None:
    report = group_issues(CHECK)
    for group in report.groups:
        assert group.part is not None
        spec = COMPONENT_BY_ID[group.part]
        assert (group.title, group.wiki) == (spec.name, spec.wiki)


def test_errors_come_first_then_warnings_hints_and_notes_in_the_order_found() -> None:
    found = [
        issue("info", "kmp", "n1"),
        issue("hint", "kmp", "h1"),
        issue("warning", "kmp", "w1"),
        issue("error", "kmp", "e1"),
        issue("warning", "kmp", "w2"),
        issue("error", "kmp", "e2"),
    ]
    [group] = group_issues(found).groups
    assert [i.message for i in group.issues] == ["e1", "e2", "w1", "w2", "h1", "n1"]
    later_first = [issue("error", "kmp", "zz"), issue("error", "kmp", "aa")]
    assert [i.message for i in group_issues(later_first).groups[0].issues] == ["zz", "aa"]


@pytest.mark.parametrize(
    ("path", "span"),
    [
        ("My  Track/x.kcl", "`My  Track/x.kcl`"),  # inner spacing kept, so it pastes back
        (" lead.kcl", "`  lead.kcl `"),  # a space at an end is padded so it survives
        ("trail.kcl ", "` trail.kcl  `"),
        ("`a", "`` `a ``"),  # a backtick at an end is padded too
        ("a`", "`` a` ``"),
        ("a``b", "```a``b```"),  # the fence is longer than any run inside
        ("two\r\nlines\nx", "`two lines x`"),  # line breaks become spaces
        ("x\n", "` x  `"),  # padding is judged after line breaks become spaces...
        ("\n`", "``  ` ``"),  # ...so this one stays balanced
    ],
)
def test_a_file_is_a_code_span_that_reads_back_as_the_same_path(path: str, span: str) -> None:
    file = PurePosixPath(path)  # every character kept as written, on any system
    text = report_text(group_issues([issue("warning", "kcl", "m", file=file)]), "T")  # type: ignore[arg-type]
    assert f"  File: {span}\n" in text


@pytest.mark.parametrize(
    ("track", "fields"),
    [
        ('"build/\\ud800.szs"', ""),
        ('"build/t.szs"', ', "file": "a\\u0000b.kcl"'),
        ('"build/t.szs"', ', "hint": "\\udc00"'),
        ('"build/t.szs"', ', "wiki": "https://x.org/\\ud800"'),
        ('"build/t.szs"', ', "file": "\\ud800.kcl"'),
    ],
    ids=["track", "nul-file", "hint", "wiki", "file"],
)
def test_text_utf_8_cannot_hold_or_a_nul_in_a_path_is_refused(
    tmp_path: Path, track: str, fields: str
) -> None:
    item = '{"severity": "warning", "component": "kcl", "code": "X", "message": "m"'
    item += ', "source": "s"' + fields + "}"
    saved = tmp_path / ISSUES_FILE
    saved.parent.mkdir(parents=True)
    saved.write_text('{"format": 1, "track": ' + track + ', "issues": [' + item + "]}", "utf-8")
    with pytest.raises(ProjectError, match="could not be read"):
        load_report(tmp_path)


def test_a_message_utf_8_cannot_hold_is_refused(tmp_path: Path) -> None:
    item = '{"severity": "warning", "component": "kcl", "code": "X", "message": "\\ud800"'
    saved = tmp_path / ISSUES_FILE
    saved.parent.mkdir(parents=True)
    body = '{"format": 1, "track": "build/t.szs", "issues": [' + item + ', "source": "s"}]}'
    saved.write_text(body, "utf-8")
    with pytest.raises(ProjectError, match="could not be read"):
        load_report(tmp_path)


def test_grouping_judges_folders_only_inside_the_project() -> None:
    root = Path("C:/mods/posteffect")  # a project kept in a folder called "posteffect"
    stop = issue("error", "assemble", "stop", file=root / "ctstudio.toml")
    [group] = group_issues([stop], root=root).groups
    assert group.part is None


def test_whole_track_findings_come_last_with_no_wiki_page() -> None:
    report = group_issues([issue(component="validate", message="stop"), *CHECK])
    last = report.groups[-1]
    assert (last.part, last.title, last.wiki) == (None, "Whole track", None)
    assert [i.message for i in last.issues] == ["stop"]


def test_counts_are_said_in_plain_words() -> None:
    assert counts_text(group_issues(CHECK)) == "5 warnings, 2 hints and 1 note"
    one_each = group_issues([issue("error"), issue("warning"), issue("hint"), issue("info")])
    assert counts_text(one_each) == "1 error, 1 warning, 1 hint and 1 note"
    assert counts_text(group_issues([issue("error"), issue("error")])) == "2 errors"
    assert counts_text(group_issues([])) == "no issues"
    assert group_issues([]).groups == ()


def test_the_report_text_is_markdown_with_hints_files_and_wiki_links() -> None:
    found = [
        issue(
            "error",
            "kcl",
            "Collision is missing.",
            hint="Choose its file.",
            file=Path("course.kcl"),
        ),
        issue("warning", "kcl", "Odd *flags* here."),
        issue("info", "archive", "Signature: WiimmSZS v2.42"),
    ]
    report = group_issues(found, track="build/castle_course.szs")
    assert report_text(report, "Pistë 日本") == (
        "# Issues: Pistë 日本\n"
        "\n"
        "Track: `build/castle_course.szs`  \n"
        "1 error, 1 warning and 1 note\n"
        "\n"
        "## Collision\n"
        "\n"
        f"Help: {COMPONENT_BY_ID['kcl'].wiki}\n"
        "\n"
        "- **Error:** Collision is missing.  \n"
        "  Next: Choose its file.  \n"
        "  File: `course.kcl`\n"
        "- **Warning:** Odd \\*flags\\* here.\n"
        "\n"
        "## Whole track\n"
        "\n"
        "- **Note:** Signature: WiimmSZS v2.42\n"
    )


def test_an_issue_with_its_own_wiki_page_names_it() -> None:
    page = "https://mkwiiki.org/wiki/Elsewhere"
    text = report_text(group_issues([issue("warning", "kmp", "Hm.", wiki=page)]), "T")
    assert f"  Help: {page}" in text
    same = COMPONENT_BY_ID["kmp"].wiki
    assert text.count(same) == 1  # the part's page once, under its heading
    again = report_text(group_issues([issue("warning", "kmp", "Hm.", wiki=same)]), "T")
    assert again.count(same) == 1


def test_an_empty_report_says_so() -> None:
    assert report_text(group_issues([]), "T") == "# Issues: T\n\nNo issues found.\n"


def test_the_validate_steps_issues_json_is_read_back_grouped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from build_runner_helpers import make_root

    root = make_root(tmp_path)
    (root / "build").mkdir()
    (root / "build" / "castle_course.szs").write_bytes(b"Yaz0 built")
    Wiimm(monkeypatch)
    run(root)
    report = load_report(root)
    assert report is not None
    assert report.track == "build/castle_course.szs"
    by_part = {group.part: group for group in report.groups}
    # analyze reports the course, minimap and skybox missing: one error each, then check's own
    assert parts(report) == ["course_model", "kcl", "minimap", "skybox", "kmp"]
    for part in ("course_model", "minimap", "skybox"):
        assert [i.code for i in by_part[part].issues] == ["VALIDATE_PART_MISSING"]
    assert counts_text(report) == "3 errors, 2 warnings, 2 hints and 1 note"
    text = report_text(report, "T")
    assert "  File: `build/castle_course.szs`\n" in text  # inside the project: relative, "/"
    assert "Course model (course_model.brres) is not in castle_course.szs" in text


def test_a_file_outside_the_project_is_shown_in_full(tmp_path: Path) -> None:
    root, elsewhere = tmp_path / "project", tmp_path / "elsewhere" / "course.kcl"
    found = [
        issue("warning", "kcl", "a", file=root / "sub" / "x.kcl"),
        issue("warning", "kcl", "b", file=elsewhere),
    ]
    text = report_text(group_issues(found, root=root), "T")
    assert "  File: `sub/x.kcl`\n" in text
    assert f"  File: `{elsewhere}`\n" in text
    assert f"  File: `{root / 'sub' / 'x.kcl'}`\n" in report_text(group_issues(found), "T")


def test_text_cannot_break_the_report_layout() -> None:
    found = [
        issue("warning", "kcl", "Two\nlines\r\n# not a heading", hint="  spaced\tout  "),
        issue("warning", "kcl", "<b>bold</b> [link](x) `code` back\\slash _under_score_"),
        issue("warning", "kcl", "Path", file=Path("C:\\Tracks\\_old_\\course.kcl")),
        issue("warning", "kcl", "Tick", file=Path("a`b.kcl")),
        issue("warning", "kcl", "Odd name", file=Path("odd\nname.kcl")),
        issue("warning", "kcl", "Own page", wiki="https://x.org/a\n# injected"),
        issue("warning", "kcl", "Empty hint", hint=""),
    ]
    text = report_text(group_issues(found), "My\n# injected *name*")
    assert text.startswith("# Issues: My # injected \\*name\\*\n\n")
    assert "- **Warning:** Two lines # not a heading  \n  Next: spaced out\n" in text
    assert (
        "- **Warning:** \\<b>bold\\</b> \\[link\\](x) \\`code\\` back\\\\slash _under_score_\n"
        in text
    )
    assert f"  File: `{Path('C:\\Tracks\\_old_\\course.kcl')}`\n" in text
    assert "  File: ``a`b.kcl``\n" in text
    assert "  File: `odd name.kcl`\n" in text
    assert "  Help: https://x.org/a # injected\n" in text
    assert "- **Warning:** Empty hint\n" in text  # no empty "Next:" line
    assert [line for line in text.splitlines() if line.startswith("#")] == [
        "# Issues: My # injected \\*name\\*",
        "## Collision",
    ]


def test_no_checked_build_yet_is_none_not_an_error(tmp_path: Path) -> None:
    try:
        result: object = load_report(tmp_path)
    except ProjectError as error:  # a project never built must not show a read failure
        result = error
    assert result is None


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        json.dumps({"format": 2, "track": "build/t.szs", "issues": []}),
        json.dumps({"format": 1, "track": "build/t.szs", "issues": [{"severity": "loud"}]}),
        json.dumps({"format": 1, "track": 5, "issues": []}),
        json.dumps({"format": 1, "track": "build/t.szs", "issues": {}}),
        json.dumps({"format": True, "track": "build/t.szs", "issues": []}),
        json.dumps({"format": 1.0, "track": "build/t.szs", "issues": []}),
        json.dumps({"format": 1, "track": "", "issues": []}),
        json.dumps({"format": 1, "track": "build/t.szs", "issues": [{"severity": "error"}]}),
        '{"format": 1, "track": "b", "issues": ' + "[" * 100_000 + "]" * 100_000 + "}",
    ],
    ids=[
        "text",
        "list",
        "format",
        "issue",
        "track",
        "issues",
        "true",
        "float",
        "empty",
        "key",
        "deep",
    ],
)
def test_a_damaged_issues_file_is_a_plain_project_error(tmp_path: Path, content: str) -> None:
    report = tmp_path / ISSUES_FILE
    report.parent.mkdir(parents=True)
    report.write_text(content, encoding="utf-8")
    with pytest.raises(Exception) as caught:
        load_report(tmp_path)
    error = caught.value
    assert isinstance(error, ProjectError)
    assert error.user_message == (
        "The saved check results (.ctstudio/issues.json) could not be read."
    )
    assert error.hint == "Build the track again to check it afresh."


def test_an_unreadable_issues_file_is_a_plain_project_error(tmp_path: Path) -> None:
    (tmp_path / ISSUES_FILE).mkdir(parents=True)  # a folder where the file should be
    with pytest.raises(ProjectError, match="could not be read"):
        load_report(tmp_path)
