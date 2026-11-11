"""Literal text, cleared actions and direct help dispatch in the Issues panel."""

# pyright: reportPrivateUsage=false
# Direct slot calls deliberately bypass disabled-button dispatch in these guard tests.

from pathlib import Path

import pytest
from issues_helpers import finding, issues_dashboard, rows
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ctstudio.core.validation.issues import Issue
from ctstudio.core.validation.report import group_issues
from ctstudio.gui.views.issues_panel import IssuesPanel

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def test_multiline_diagnostics_are_folded_but_remain_literal(qtbot: QtBot, tmp_path: Path) -> None:
    panel = IssuesPanel()
    qtbot.addWidget(panel)
    report = group_issues(
        [Issue("warning", "kcl", "TEST", "<b>Not HTML</b>\nnext\t line", "Try\nthis.", "test")],
        root=tmp_path,
    )
    panel.show_report(report, None, "Track")
    panel.tree.setCurrentItem(finding(panel.tree, 0, 0))
    assert rows(panel.tree) == [("Collision — 1 warning", ["Warning: <b>Not HTML</b> next line"])]
    assert panel.detail.text() == (
        "Warning: <b>Not HTML</b> next line\nNext: Try this.\nPart: Collision"
    )
    assert panel.detail.toolTip() == panel.detail.text()
    assert panel.detail.accessibleDescription() == panel.detail.text()


def test_help_dispatch_without_a_page_does_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    opened: list[str] = []
    with issues_dashboard(qtbot, tmp_path) as (page, _services, _project, _area):
        panel = page.issues
        panel.open_url = opened.append
        panel.tree.setCurrentItem(finding(panel.tree, 5, 0))
        assert not panel.help_button.isEnabled()
        panel._open_help()  # bypass Qt's disabled-button dispatch to test the slot itself
        assert opened == []


def test_clearing_a_selected_finding_clears_all_its_details(qtbot: QtBot, tmp_path: Path) -> None:
    with issues_dashboard(qtbot, tmp_path) as (page, _services, _project, _area):
        panel = page.issues
        panel.tree.setCurrentItem(finding(panel.tree, 3, 0))
        assert panel.help_button.isEnabled()
        panel.clear()
        assert rows(panel.tree) == []
        assert (
            panel.detail.text()
            == panel.detail.toolTip()
            == panel.detail.accessibleDescription()
            == ""
        )
        assert panel.help_button.toolTip() == ""
        assert not panel.help_button.isEnabled()
        assert not panel.copy_button.isEnabled()
        QApplication.clipboard().setText("unchanged")
        panel._copy()
        assert QApplication.clipboard().text() == "unchanged"
