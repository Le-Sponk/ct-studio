"""P5-T03b: freshness boundaries, errors, read-only/build states and UI-thread work."""

import threading
from pathlib import Path

import pytest
from build_fakes import FakeBuilds
from dashboard_helpers import overview
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.components.status import ComponentStatus, State
from ctstudio.core.project.project import Project
from ctstudio.gui.status_service import StatusResult
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def ready(root: Path) -> StatusResult:
    return StatusResult(root, {"kcl": ComponentStatus(State.READY, ("Checked output",))})


def test_old_project_result_cannot_replace_current_cards_or_end_current_check(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with overview(qtbot, tmp_path) as (page, services, project):
        services.status.updated.emit(ready(project.root))
        page.refresh()
        services.status.updated.emit(
            StatusResult(
                tmp_path / "Other",
                {"kcl": ComponentStatus(State.ERROR, ("This is not our project",))},
            )
        )
        assert page.cards["kcl"].status_label.text() == "ready"
        assert page.busy and not page.refresh_button.isEnabled()
        services.status.updated.emit(ready(project.root))
        assert not page.busy


def test_results_after_close_are_not_shown(qtbot: QtBot, tmp_path: Path) -> None:
    with overview(qtbot, tmp_path) as (page, services, project):
        before = page.cards["kcl"].status_label.text()
        services.close_project()
        services.status.updated.emit(ready(project.root))
        assert page.cards["kcl"].status_label.text() == before


def test_switching_project_resets_header_cards_and_inflight_check(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with overview(qtbot, tmp_path) as (page, services, project):
        services.status.updated.emit(ready(project.root))
        page.refresh()
        replacement = Project.create(tmp_path / "Second", "Second")
        services.adopt(replacement)
        page.set_project(replacement)
        assert page.name_label.text() == "Second"
        assert page.cards["kcl"].status_label.text() == "Not checked"
        qtbot.waitUntil(lambda: not page.busy)
        assert "Second" in str(page.cards["kcl"].path)


def test_settings_problem_is_visible_with_valid_statuses_then_clears(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with overview(qtbot, tmp_path) as (page, services, project):
        result = StatusResult(project.root, ready(project.root).statuses, "Repair <settings> first")
        services.status.updated.emit(result)
        assert page.notice.text() == "Repair <settings> first"
        assert page.notice.textFormat() == Qt.TextFormat.PlainText
        assert page.cards["kcl"].status_label.text() == "ready"
        services.status.updated.emit(ready(project.root))
        assert "Repair" not in page.notice.text()
        assert (
            "not checked" in page.notice.text().lower()
        )  # incomplete result is not called all-clear


def assert_building_controls(page: Dashboard) -> None:
    assert not page.refresh_button.isEnabled()
    assert "build" in page.work_label.text().lower()
    assert page.copy_project.isEnabled()
    assert page.cards["kcl"].copy_button.isEnabled()
    assert page.work_label.isVisible()


@pytest.mark.parametrize("fails", [False, True])
def test_build_disables_refresh_but_not_copy_and_refreshes_after_end(
    qtbot: QtBot, tmp_path: Path, fails: bool
) -> None:
    fake = FakeBuilds()
    gate = threading.Event()
    fake.gate = gate
    if fails:
        fake.run_error = RuntimeError("synthetic failed build")
    with overview(qtbot, tmp_path, fake) as (page, services, project):
        try:
            assert services.build.start(project)
            assert_building_controls(page)
            services.status.updated.emit(ready(project.root))
            page.set_project(project)  # Ctrl+D during a build must retain the last checked results
            page.refresh()  # direct callers cannot bypass the disabled refresh button
            assert page.cards["kcl"].status_label.text() == "ready"
            assert not page.busy
            signal = services.build.failed if fails else services.build.finished
            with qtbot.waitSignal(signal):
                gate.set()
            assert page.busy
            qtbot.waitUntil(lambda: not page.busy)
            assert page.refresh_button.isEnabled()
        finally:
            gate.set()


def test_read_only_is_explicit_and_copy_does_not_write(qtbot: QtBot, tmp_path: Path) -> None:
    services = quiet_services()
    with Project.create(tmp_path / "Held", "Held"):
        opened = Project.open(tmp_path / "Held")
        services.adopt(opened)
        try:
            page = Dashboard(services)
            qtbot.addWidget(page)
            page.set_project(opened)
            page.show()
            assert "read-only" in page.access_label.text().lower()
            reason = opened.read_only_reason
            assert reason is not None and reason in page.access_label.text()
            page.copy_project.click()
            assert QApplication.clipboard().text() == str(opened.root)
            assert opened.read_only
        finally:
            assert services.shutdown(10)


def test_presenting_and_copying_header_never_reads_files(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with overview(qtbot, tmp_path) as (page, _services, project):

        def forbidden(*_args: object, **_kw: object) -> None:
            pytest.fail("filesystem operation on the UI thread")

        with monkeypatch.context() as patcher:
            for name in ("stat", "read_bytes", "resolve"):
                patcher.setattr(Path, name, forbidden)
            page.set_project(project)
            page.copy_project.click()
        assert QApplication.clipboard().text() == str(project.root)


def test_blocked_status_check_keeps_qt_responsive(qtbot: QtBot, tmp_path: Path) -> None:
    from PySide6.QtCore import QTimer

    from ctstudio.gui.services import AppServices
    from ctstudio.gui.status_service import StatusService

    gate = threading.Event()
    began = threading.Event()
    ticks: list[bool] = []

    def evaluate(_project: object, _tools: object) -> dict[str, ComponentStatus]:
        began.set()
        assert gate.wait(10)
        return {}

    services = AppServices(
        status=StatusService(evaluate=evaluate, find_tools=lambda **_kw: (), delay_ms=1)
    )
    project = Project.create(tmp_path / "Busy", "Busy")
    services.adopt(project)
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        page.show()
        qtbot.waitUntil(began.is_set)
        QTimer.singleShot(0, lambda: ticks.append(True))
        qtbot.waitUntil(lambda: bool(ticks))
        assert page.busy and page.checking.isVisible()
        assert not page.refresh_button.isEnabled()
        assert "Checking" in page.notice.text()
        gate.set()
        qtbot.waitUntil(lambda: not page.busy)
        assert not page.checking.isVisible()
    finally:
        gate.set()
        assert services.shutdown(10)


def test_closed_project_ignores_failure_and_cannot_copy_old_path(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with overview(qtbot, tmp_path) as (page, services, _project):
        message = page.notice.text()
        services.close_project()
        services.status.failed.emit(RuntimeError("old project failure"))
        QApplication.clipboard().setText("unchanged")
        page._copy_project()
        assert page.notice.text() == message
        assert QApplication.clipboard().text() == "unchanged"


def test_empty_dashboard_cannot_refresh(qtbot: QtBot) -> None:
    services = quiet_services()
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.refresh()
        assert not page.busy and not page.refresh_button.isEnabled()
    finally:
        assert services.shutdown(10)
