"""P5-T03b: the dashboard displays the opened project's real header."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.project.project import Project

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_project_header_is_shown(qtbot: QtBot, tmp_path: Path) -> None:
    from ctstudio.gui.views.dashboard import Dashboard

    services = quiet_services()
    project = Project.create(tmp_path / "Piste é", "Piste <é>", blend=tmp_path / "source.blend")
    services.adopt(project)
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        page.show()
        label = page.findChild(QLabel, "dashboardName")
        assert label is not None and label.text() == "Piste <é>"
        assert page.folder_label.text() == str(project.root)
        assert project.manifest.project.slot in page.slot_label.text()
        assert "source.blend" in page.source_label.text()
    finally:
        assert services.shutdown(10)


def test_cards_follow_background_status_results(qtbot: QtBot, tmp_path: Path) -> None:
    import threading

    from ctstudio.core.components.registry import COMPONENTS
    from ctstudio.core.components.status import ComponentStatus, State
    from ctstudio.gui.services import AppServices
    from ctstudio.gui.status_service import StatusService
    from ctstudio.gui.views.dashboard import Dashboard

    threads: list[threading.Thread] = []

    def evaluate(_project: object, _tools: object) -> dict[str, ComponentStatus]:
        threads.append(threading.current_thread())
        return {spec.id: ComponentStatus(State.READY, ("Output checked",)) for spec in COMPONENTS}

    services = AppServices(
        status=StatusService(evaluate=evaluate, find_tools=lambda **_kw: (), delay_ms=1)
    )
    project = Project.create(tmp_path / "Live é", "Live é")
    services.adopt(project)
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        page.show()
        qtbot.waitUntil(lambda: page.cards["kcl"].status_label.text() == "ready")
        assert list(page.cards) == [spec.id for spec in COMPONENTS]
        assert all(card.summary.text() == "Output checked" for card in page.cards.values())
        assert threads and all(t is not threading.main_thread() for t in threads)
        assert not page.busy and page.refresh_button.isEnabled()
    finally:
        assert services.shutdown(10)


def test_refresh_failure_keeps_last_good_status(qtbot: QtBot, tmp_path: Path) -> None:
    from ctstudio.core.components.status import ComponentStatus, State
    from ctstudio.gui.status_service import StatusResult
    from ctstudio.gui.views.dashboard import Dashboard

    services = quiet_services()
    project = Project.create(tmp_path / "Errors", "Errors")
    services.adopt(project)
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        qtbot.waitUntil(lambda: not page.busy)
        services.status.updated.emit(
            StatusResult(project.root, {"kcl": ComponentStatus(State.READY)})
        )
        page.refresh_button.click()
        assert page.busy and not page.refresh_button.isEnabled()
        services.status.failed.emit(RuntimeError("disk unavailable"))
        assert "disk unavailable" in page.notice.text()
        assert "Refresh" in page.notice.text()
        assert page.cards["kcl"].status_label.text() == "ready"
        assert not page.busy and page.refresh_button.isEnabled()
    finally:
        assert services.shutdown(10)
