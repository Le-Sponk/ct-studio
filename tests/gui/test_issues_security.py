"""Saved reports may name help pages, never local files or protocol handlers."""

from pathlib import Path

import pytest
from issues_helpers import finding, issues_dashboard, write_issues
from pytestqt.qtbot import QtBot

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.validation.issues import Issue
from ctstudio.core.validation.report import group_issues
from ctstudio.gui.views.issues_panel import IssuesPanel

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]

UNSAFE = [
    "file:///C:/review-only/not-executed.cmd",
    "custom-handler:review-only",
    "javascript:alert(1)",
    "data:text/html,review-only",
    "C:/review-only/not-executed.cmd",
    "//mkwiiki.org/wiki/Collision",
    "http://mkwiiki.org/wiki/Collision",
    "https://example.org/wiki/Collision",
    "https://mkwiiki.org.example.org/wiki/Collision",
    "https://mkwiiki.org@example.org/wiki/Collision",
    "https://example.org@mkwiiki.org/wiki/Collision",
    "https://mkwiiki.org:8443/wiki/Collision",
    "https://mkwiiki.org/wiki/%zz",
    "https://mkwiiki.org/wiki/a b",
    "https://mkwiiki.org/other",
    "https://mkwiiki.org\\@example.org/wiki/Collision",
]


@pytest.mark.parametrize("wiki", UNSAFE)
@pytest.mark.parametrize("component", ["archive", "kcl"])
def test_a_help_link_cannot_launch_anything_but_the_wiki(
    qtbot: QtBot, tmp_path: Path, wiki: str, component: str
) -> None:
    opened: list[str] = []
    panel = IssuesPanel()
    qtbot.addWidget(panel)
    issue = Issue("warning", component, "TEST", "A finding", None, "test", wiki=wiki)
    panel.show_report(group_issues([issue], root=tmp_path), None, "Track")
    panel.open_url = opened.append
    panel.tree.setCurrentItem(finding(panel.tree, 0, 0))
    if component == "archive":
        assert not panel.help_button.isEnabled()
        assert panel.help_button.toolTip() == ""
        panel.help_button.click()
        assert opened == []
    else:
        expected = COMPONENT_BY_ID[component].wiki
        assert panel.help_button.isEnabled()
        assert panel.help_button.toolTip() == expected
        panel.help_button.click()
        assert opened == [expected]


def test_a_saved_https_wiki_page_is_used(qtbot: QtBot, tmp_path: Path) -> None:
    wiki = "https://mkwiiki.org/wiki/KCL_(File_Format)#Introduction"
    opened: list[str] = []
    with issues_dashboard(qtbot, tmp_path, before=False) as (page, services, project, _area):
        write_issues(
            project.root, [Issue("warning", "kcl", "TEST", "A finding", None, "test", wiki=wiki)]
        )
        page.refresh_button.click()
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        panel = page.issues
        panel.open_url = opened.append
        panel.tree.setCurrentItem(finding(panel.tree, 0, 0))
        assert panel.help_button.isEnabled()
        panel.help_button.click()
        assert opened == [wiki]


def test_a_saved_local_file_link_is_never_dispatched(qtbot: QtBot, tmp_path: Path) -> None:
    opened: list[str] = []
    with issues_dashboard(qtbot, tmp_path, before=False) as (page, services, project, _area):
        issue = Issue(
            "warning",
            "archive",
            "TEST",
            "A finding",
            None,
            "test",
            wiki="file:///C:/review-only/not-executed.cmd",
        )
        write_issues(project.root, [issue])
        page.refresh_button.click()
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        panel = page.issues
        panel.open_url = opened.append
        panel.tree.setCurrentItem(finding(panel.tree, 0, 0))
        assert not panel.help_button.isEnabled()
        panel.help_button.click()
        assert opened == []
