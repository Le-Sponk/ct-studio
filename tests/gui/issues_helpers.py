"""Issues panel test setup (P5-T05b): an ``issues.json`` like the validate step writes.

The findings are the recorded real ``wszst check`` 2.42a output (its stdout only; no game
file), plus one missing-part error as ``wszst analyze`` reports it and one finding about the
whole track. All projects are temporary and synthetic.
"""

from __future__ import annotations

import json
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QScrollArea, QTreeWidget, QTreeWidgetItem
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.build.validate import ISSUES_FILE
from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.project.project import Project
from ctstudio.core.validation.issues import Issue, issue_to_json
from ctstudio.core.validation.wszst_check import parse_check
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.dashboard import Dashboard

RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a"
TRACK = "build/castle_course.szs"


def recorded_check() -> list[Issue]:
    rows: list[dict[str, Any]] = json.loads(
        (RECORDINGS / "windows-ops.json").read_text(encoding="utf-8")
    )
    row = next(row for row in rows if row["case"] == "check")
    return parse_check(row["stdout"], Path("t.szs"), exit_code=row["exit_code"])


def findings(root: Path) -> list[Issue]:
    """What a test build of a stage holding only KCL and KMP reports (validate's order)."""
    spec = COMPONENT_BY_ID["skybox"]
    missing = Issue(
        "error",
        "skybox",
        "VALIDATE_PART_MISSING",
        "Skybox (vrcorn_model.brres) is not in castle_course.szs, so the game cannot load"
        " the track.",
        "Choose its file on the dashboard, then build again.",
        "wszst analyze",
        root / TRACK,
        spec.wiki,
    )
    whole = Issue("info", "archive", "WSZST_INFO", "Signature: WiimmSZS v2.42", None, "wszst check")
    return [missing, *recorded_check(), whole]


def write_issues(root: Path, issues: Sequence[Issue] | None = None) -> Path:
    found = findings(root) if issues is None else issues
    data = {"format": 1, "track": TRACK, "issues": [issue_to_json(i, root) for i in found]}
    path = root / ISSUES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def rows(tree: QTreeWidget) -> list[tuple[str, list[str]]]:
    """Each group's text with its findings' texts, as shown."""
    out: list[tuple[str, list[str]]] = []
    for index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(index)
        assert group is not None
        out.append((group.text(0), [child(group, n).text(0) for n in range(group.childCount())]))
    return out


def child(group: QTreeWidgetItem, index: int) -> QTreeWidgetItem:
    item = group.child(index)
    assert item is not None, f"no finding {index} under {group.text(0)}"
    return item


def finding(tree: QTreeWidget, group_index: int, index: int) -> QTreeWidgetItem:
    group = tree.topLevelItem(group_index)
    assert group is not None, f"no group {group_index}"
    return child(group, index)


@contextmanager
def issues_dashboard(
    qtbot: QtBot, folder: Path, *, before: bool = True
) -> Generator[tuple[Dashboard, AppServices, Project, QScrollArea], None, None]:
    """A dashboard in a scroll area like the window's; ``before`` writes issues.json first."""
    services = quiet_services()
    project = Project.create(folder / "Pistë 日本", "Pistë 日本")
    if before:
        write_issues(project.root)
    services.adopt(project)
    try:
        page = Dashboard(services)
        area = QScrollArea()
        qtbot.addWidget(area)
        area.setWidgetResizable(True)
        area.setWidget(page)
        page.set_project(project)
        area.resize(900, 700)
        area.show()
        qtbot.waitUntil(lambda: not page.busy and not services.status.busy)
        yield page, services, project, area
    finally:
        assert services.shutdown(10)
