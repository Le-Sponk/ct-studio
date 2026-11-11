"""P5-T05b: the dashboard's Issues panel, from the recorded real ``wszst check`` output.

The report is read with each status check on the status thread (on open, on Refresh and
after every build); the panel groups it by part with plain counts, shows the selected
finding's next step and file, opens its help page and copies the whole report. A click or
Enter on a finding scrolls to that part's card and focuses it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from build_fakes import FakeBuilds
from issues_helpers import TRACK, finding, issues_dashboard, rows, write_issues
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.project.project import Project
from ctstudio.core.validation.report import IssueReport, load_report, report_text
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def no_tools(**_kwargs: object) -> tuple[()]:
    return ()


SHOWN = [
    ("Course model — 1 warning", ["Warning: Missing file: ./course_model.brres (or '_d' variant)"]),
    ("Collision — 1 note", ["Note: Signature: WiimmSZS v2.42"]),
    ("Minimap — 1 warning", ["Warning: Missing file: ./map_model.brres"]),
    (
        "Skybox — 1 error and 1 warning",
        [
            "Error: Skybox (vrcorn_model.brres) is not in castle_course.szs, so the game cannot"
            " load the track.",
            "Warning: Missing file: ./vrcorn_model.brres",
        ],
    ),
    (
        "Course data — 2 warnings and 2 hints",
        [
            "Warning: Invalid link to not existing opening camera #0 (max=#-1).",
            "Warning: Invalid link to not existing selection camera #0 (max=#-1).",
            "Hint: Missing a camera with type 0.",
            "Hint: Self linked item route.",
        ],
    ),
    ("Whole track — 1 note", ["Note: Signature: WiimmSZS v2.42"]),
]


def test_the_last_check_is_shown_grouped_by_part_when_the_project_opens(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with issues_dashboard(qtbot, tmp_path) as (page, _services, _project, _area):
        panel = page.issues
        assert rows(panel.tree) == SHOWN
        assert panel.summary.text() == (
            f"Last check of {TRACK}: 1 error, 5 warnings, 2 hints and 2 notes."
        )
        for n in range(len(SHOWN)):
            group = panel.tree.topLevelItem(n)
            assert group is not None and group.isExpanded()
        assert panel.copy_button.isEnabled()
        assert not panel.help_button.isEnabled()  # nothing selected yet
        assert panel.detail.text() == "Select a finding to see its next step and file."


def test_the_report_is_read_off_the_ui_thread(qtbot: QtBot, tmp_path: Path) -> None:
    import threading

    from ctstudio.gui.services import AppServices
    from ctstudio.gui.status_service import StatusService

    threads: list[threading.Thread] = []

    def loader(root: Path) -> IssueReport | None:
        threads.append(threading.current_thread())
        return load_report(root)

    status = StatusService(
        evaluate=lambda _p, _t: {}, find_tools=no_tools, load_issues=loader, delay_ms=1
    )
    services = AppServices(status=status)
    project = Project.create(tmp_path / "Threads", "Threads")
    write_issues(project.root)
    services.adopt(project)
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        assert rows(page.issues.tree) == SHOWN
        assert threads and all(thread is not threading.main_thread() for thread in threads)
    finally:
        assert services.shutdown(10)


def test_an_unexpected_read_failure_is_explained_and_statuses_still_show(
    qtbot: QtBot, tmp_path: Path
) -> None:
    from ctstudio.core.components.status import ComponentStatus, State
    from ctstudio.gui.services import AppServices
    from ctstudio.gui.status_service import StatusService

    def loader(_root: Path) -> IssueReport | None:
        raise PermissionError("locked by another program")

    def evaluate(_project: object, _tools: object) -> dict[str, ComponentStatus]:
        return {"kcl": ComponentStatus(State.MISSING, ("No collision file yet.",))}

    status = StatusService(evaluate=evaluate, find_tools=no_tools, load_issues=loader, delay_ms=1)
    services = AppServices(status=status)
    project = Project.create(tmp_path / "Locked", "Locked")
    services.adopt(project)
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        assert page.issues.summary.text() == (
            "The saved check results could not be read: locked by another program"
        )
        assert page.cards["kcl"].summary.text() == "No collision file yet."
    finally:
        assert services.shutdown(10)


def test_refresh_reads_the_report_again(qtbot: QtBot, tmp_path: Path) -> None:
    with issues_dashboard(qtbot, tmp_path, before=False) as (page, services, project, _area):
        panel = page.issues
        assert rows(panel.tree) == []
        assert panel.summary.text() == "Not checked yet: build the track to check it for problems."
        assert not panel.copy_button.isEnabled()
        write_issues(project.root)
        page.refresh_button.click()
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        assert rows(panel.tree) == SHOWN


class _CheckingBuilds(FakeBuilds):
    """A build whose validate step writes the report, as the real one does."""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def run(self, *args: Any, **kw: Any) -> Any:
        write_issues(self.root)
        return super().run(*args, **kw)


def test_each_build_brings_its_new_report(qtbot: QtBot, tmp_path: Path) -> None:
    project = Project.create(tmp_path / "Built", "Built")
    builds = _CheckingBuilds(project.root)
    services = quiet_services(builds)
    services.adopt(project)
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        assert rows(page.issues.tree) == []
        page.builds.controls.build_requested.emit(False)
        qtbot.waitUntil(lambda: not services.build.running)
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        assert rows(page.issues.tree) == SHOWN
    finally:
        assert services.shutdown(10)


def test_a_check_without_findings_says_so(qtbot: QtBot, tmp_path: Path) -> None:
    with issues_dashboard(qtbot, tmp_path, before=False) as (page, services, project, _area):
        write_issues(project.root, [])
        page.refresh_button.click()
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        assert rows(page.issues.tree) == []
        assert page.issues.summary.text() == f"The last check of {TRACK} found no issues."
        assert page.issues.copy_button.isEnabled()


def test_a_damaged_report_is_explained_and_nothing_old_is_shown(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with issues_dashboard(qtbot, tmp_path) as (page, services, project, _area):
        assert rows(page.issues.tree) == SHOWN
        (project.root / ".ctstudio" / "issues.json").write_text("not json", encoding="utf-8")
        page.refresh_button.click()
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        assert rows(page.issues.tree) == []
        assert page.issues.summary.text() == (
            "The saved check results (.ctstudio/issues.json) could not be read.\n"
            "Next: Build the track again to check it afresh."
        )
        assert not page.issues.copy_button.isEnabled()
        assert page.cards["kcl"].status_label.text() != ""  # statuses still shown


def test_a_failed_status_check_keeps_the_last_report(qtbot: QtBot, tmp_path: Path) -> None:
    with issues_dashboard(qtbot, tmp_path) as (page, services, _project, _area):
        page.refresh_button.click()
        services.status.clear()
        services.status.failed.emit(RuntimeError("disk unavailable"))
        assert "disk unavailable" in page.notice.text()
        assert rows(page.issues.tree) == SHOWN


def test_another_project_never_shows_this_projects_report(qtbot: QtBot, tmp_path: Path) -> None:
    with issues_dashboard(qtbot, tmp_path) as (page, services, _project, _area):
        other = Project.create(tmp_path / "Other", "Other")
        services.adopt(other)
        page.set_project(other)
        assert rows(page.issues.tree) == []  # at once, before its own check finishes
        assert page.issues.summary.text().startswith("Not checked yet")
        assert not page.issues.copy_button.isEnabled()
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        assert rows(page.issues.tree) == []


def test_the_selected_finding_shows_its_next_step_file_and_help_page(
    qtbot: QtBot, tmp_path: Path
) -> None:
    opened: list[str] = []
    with issues_dashboard(qtbot, tmp_path) as (page, _services, _project, _area):
        panel = page.issues
        panel.open_url = lambda url: opened.append(url)
        panel.tree.setCurrentItem(finding(panel.tree, 3, 0))  # the missing skybox
        assert panel.detail.text() == (
            "Error: Skybox (vrcorn_model.brres) is not in castle_course.szs, so the game cannot"
            " load the track.\n"
            "Next: Choose its file on the dashboard, then build again.\n"
            f"File: {TRACK}\n"
            "Part: Skybox"
        )
        skybox = COMPONENT_BY_ID["skybox"].wiki
        assert panel.help_button.isEnabled() and panel.help_button.toolTip() == skybox
        panel.help_button.click()
        assert opened == [skybox]
        panel.tree.setCurrentItem(finding(panel.tree, 4, 2))  # a KMP hint: the part's page
        assert panel.detail.text() == "Hint: Missing a camera with type 0.\nPart: Course data"
        assert panel.help_button.toolTip() == COMPONENT_BY_ID["kmp"].wiki
        panel.tree.setCurrentItem(finding(panel.tree, 5, 0))  # the whole track: no page
        assert panel.detail.text() == "Note: Signature: WiimmSZS v2.42\nAbout the whole track."
        assert not panel.help_button.isEnabled()
        panel.help_button.click()
        assert opened == [skybox]
        group = panel.tree.topLevelItem(4)
        assert group is not None
        panel.tree.setCurrentItem(group)
        assert panel.detail.text() == (
            "Course data: 2 warnings and 2 hints. Select a finding to see its details."
        )
        assert panel.help_button.isEnabled()


def test_copy_report_copies_the_whole_report(qtbot: QtBot, tmp_path: Path) -> None:
    with issues_dashboard(qtbot, tmp_path) as (page, _services, project, _area):
        QApplication.clipboard().setText("")
        page.issues.copy_button.click()
        report = load_report(project.root)
        assert report is not None
        assert QApplication.clipboard().text() == report_text(report, "Pistë 日本")


def _shown(area: QScrollArea, widget: QWidget) -> bool:
    inner = area.widget()
    assert inner is not None
    top = widget.mapTo(inner, QPoint(0, 0)).y()
    first = area.verticalScrollBar().value()
    return first <= top and top + widget.height() <= first + area.viewport().height()


def _jump(qtbot: QtBot, area: QScrollArea, page: Dashboard, act: Callable[[], None]) -> None:
    area.activateWindow()
    qtbot.waitUntil(area.isActiveWindow)
    area.ensureWidgetVisible(page.issues.tree)
    QApplication.processEvents()
    card = page.cards["course_model"]
    assert not _shown(area, card), "the course model card starts out of view"
    act()
    QApplication.processEvents()
    focus = QApplication.focusWidget()
    assert focus is card.mode_button, "the card's first control has the focus"
    assert _shown(area, card), "the card was scrolled into view"


def test_clicking_a_finding_goes_to_its_card(qtbot: QtBot, tmp_path: Path) -> None:
    with issues_dashboard(qtbot, tmp_path) as (page, _services, _project, area):
        tree = page.issues.tree

        def click() -> None:
            item = finding(tree, 0, 0)
            tree.scrollToItem(item)
            point = tree.visualItemRect(item).center()
            QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=point)

        _jump(qtbot, area, page, click)


def test_enter_on_a_finding_goes_to_its_card(qtbot: QtBot, tmp_path: Path) -> None:
    with issues_dashboard(qtbot, tmp_path) as (page, _services, _project, area):
        tree = page.issues.tree

        def enter() -> None:
            area.activateWindow()
            QApplication.processEvents()
            tree.setFocus()
            assert tree.hasFocus()
            tree.setCurrentItem(finding(tree, 0, 0))
            QTest.keyClick(tree, Qt.Key.Key_Return)

        _jump(qtbot, area, page, enter)


def test_a_whole_track_finding_or_a_group_goes_nowhere(qtbot: QtBot, tmp_path: Path) -> None:
    with issues_dashboard(qtbot, tmp_path) as (page, _services, _project, area):
        tree = page.issues.tree
        area.activateWindow()
        QApplication.processEvents()
        tree.setFocus()
        tree.setCurrentItem(finding(tree, 5, 0))
        QTest.keyClick(tree, Qt.Key.Key_Return)
        group = tree.topLevelItem(0)
        assert group is not None
        tree.setCurrentItem(group)
        QTest.keyClick(tree, Qt.Key.Key_Return)
        assert tree.hasFocus()
        assert not any(card.hasFocus() for card in page.cards.values())


def test_the_panel_is_on_the_keyboard_path(qtbot: QtBot, tmp_path: Path) -> None:
    with issues_dashboard(qtbot, tmp_path) as (page, _services, _project, area):
        panel = page.issues
        panel.tree.setCurrentItem(finding(panel.tree, 3, 0))
        area.activateWindow()
        QApplication.processEvents()
        panel.tree.setFocus()
        assert panel.tree.hasFocus()
        QTest.keyClick(panel.tree, Qt.Key.Key_Tab)
        assert panel.help_button.hasFocus()
        QTest.keyClick(panel.help_button, Qt.Key.Key_Tab)
        assert panel.copy_button.hasFocus()
        card = page.cards["kmp"]
        assert card.focusPolicy() == Qt.FocusPolicy.ClickFocus  # reachable, not a Tab stop
        assert card.accessibleName() == "Course data"
