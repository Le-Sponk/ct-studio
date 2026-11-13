"""G03: real backend replacement/close, plus explicitly injected obsolete deliveries."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# Observe native watcher ownership and inject old callbacks; no public ready/stale API exists.
import threading
from collections.abc import Generator
from pathlib import Path

import pytest
from assign_helpers import kcl_bytes, write
from outside_flow_helpers import all_tools, change_stage
from PySide6.QtCore import QCoreApplication
from pytestqt.qtbot import QtBot
from reconcile_helpers import outcome, settled

from ctstudio.core.components.state import ProjectState, record, save_state
from ctstudio.core.components.status import settings_key
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project
from ctstudio.core.project.watch import ProjectWatcher
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(45)]


def ready_project(folder: Path) -> Project:
    project = Project.create(folder / "Pistë 日本", folder.name)
    stage = write(project.root / ".ctstudio/stage/course.kcl", kcl_bytes())
    entry = record(project.root, settings_key(project.manifest, "kcl"), [stage], [])
    save_state(project.root, ProjectState({"kcl": entry}))
    return project


@pytest.fixture
def owned_window(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[MainWindow, Project, Project, list[threading.Thread]], None, None]:
    old, new = ready_project(tmp_path / "Old é"), ready_project(tmp_path / "New 日本")
    services = AppServices(status=StatusService(find_tools=all_tools))
    joined: list[threading.Thread] = []
    native_join = threading.Thread.join

    def join(thread: threading.Thread, timeout: float | None = None) -> None:
        native_join(thread, timeout)
        joined.append(thread)

    monkeypatch.setattr(threading.Thread, "join", join)
    try:
        assert outcome(lambda: services.adopt(old)) is None
        window = MainWindow(services)
        qtbot.addWidget(window)
        window.show()
        assert settled(qtbot, lambda: not window.welcome.busy and not window.dashboard.busy)
        assert window.dashboard.cards["kcl"].status_label.text() == "ready"
        yield window, old, new, joined
    finally:
        stopped = outcome(lambda: services.shutdown(10))
        old.close()
        new.close()
        assert stopped is True, f"lifecycle cleanup failed: {stopped!r}"


def registered(services: AppServices) -> ProjectWatcher:
    watcher = services.watcher._watcher
    assert isinstance(watcher, ProjectWatcher)
    assert outcome(lambda: watcher.wait_ready(10)) is True, "real backend never registered"
    assert watcher.intact and watcher._threads
    assert all(thread.is_alive() for thread in watcher._threads)
    return watcher


def inject_obsolete(watcher: ProjectWatcher, services: AppServices) -> None:
    """Synthetic callbacks on the real object's captured relay, NOT real backend events."""
    delivered: list[object] = []
    changes: list[object] = []
    failures: list[object] = []
    on_change, on_failure = changes.append, failures.append
    services.watcher.changed.connect(on_change)
    services.watcher.failed.connect(on_failure)

    def deliver() -> None:
        watcher._on_change(frozenset({watcher.plan.root / ".ctstudio/stage/course.kcl"}))
        watcher._on_error(ProjectError("injected obsolete watch failure"))

    try:
        thread = threading.Thread(target=lambda: delivered.append(outcome(deliver)))
        thread.start()
        thread.join(10)
        assert not thread.is_alive() and delivered == [None], (
            f"injected delivery failed: {delivered!r}"
        )
        QCoreApplication.sendPostedEvents()
        QCoreApplication.processEvents()
        assert changes == [], "retired watcher change escaped the bridge's generation guard"
        assert failures == [], "retired watcher failure escaped the bridge's generation guard"
    finally:
        services.watcher.changed.disconnect(on_change)
        services.watcher.failed.disconnect(on_failure)


def view_state(page: Dashboard) -> tuple[object, ...]:
    return (
        page._project,
        page.folder_label.text(),
        page.notice.text(),
        page.busy,
        page.watch.notice.text(),
        page.watch.notice.toolTip(),
        page.watch.notice.accessibleDescription(),
        tuple(
            (key, card.status_label.text(), card.outside.note.text())
            for key, card in page.cards.items()
        ),
    )


def test_real_switch_releases_old_lock_and_isolates_current_dashboard(
    qtbot: QtBot, owned_window: tuple[MainWindow, Project, Project, list[threading.Thread]]
) -> None:
    window, old, new, joined = owned_window
    services, page = window.services, window.dashboard
    first = registered(services)
    old_threads = tuple(first._threads)
    change_stage(old)
    assert settled(qtbot, page.cards["kcl"].outside.lock_button.isEnabled)
    assert outcome(lambda: services.adopt(new)) is None
    window._show_project()
    second = registered(services)
    assert second is not first and services.watcher.watching == new.root
    # Adoption stops asynchronously; join the exact retired watcher, not name-based threads.
    assert first._stop.is_set(), "adoption did not ask the retired backend to stop"
    assert outcome(lambda: first.join(10)) is True
    assert all(any(thread is item for item in joined) for thread in old_threads)
    assert settled(qtbot, lambda: not first.alive and not page.busy and not services.status.busy)
    assert all(not thread.is_alive() for thread in old_threads)
    assert not any(
        thread is old_thread for thread in threading.enumerate() for old_thread in old_threads
    )
    with Project.open(old.root) as reopened, Project.open(new.root) as contender:
        assert not reopened.read_only, "switch did not release the actual old project lock"
        assert contender.read_only, "switch lost the current project's actual writer lock"
    assert services.project is new and page._project is new
    assert page.folder_label.text() == str(new.root)
    assert page.cards["kcl"].status_label.text() == "ready"
    before = view_state(page)
    inject_obsolete(first, services)
    assert view_state(page) == before and not services.status.busy
    change_stage(new)
    assert settled(qtbot, page.cards["kcl"].outside.lock_button.isEnabled)
    assert page.cards["kcl"].status_label.text() == "edited outside CT Studio"
    current_threads = tuple(second._threads)
    assert outcome(lambda: services.shutdown(10)) is True
    assert all(not thread.is_alive() for thread in old_threads + current_threads)
    assert all(any(thread is item for item in joined) for thread in current_threads)
    assert services.project is None and services.watcher.watching is None
    with Project.open(new.root) as reopened:
        assert not reopened.read_only


def test_native_close_joins_real_watcher_and_drops_injected_late_deliveries(
    qtbot: QtBot, owned_window: tuple[MainWindow, Project, Project, list[threading.Thread]]
) -> None:
    window, project, _unused, joined = owned_window
    services, page = window.services, window.dashboard
    watcher = registered(services)
    threads = tuple(watcher._threads)
    change_stage(project)
    assert settled(qtbot, page.cards["kcl"].outside.lock_button.isEnabled)
    assert settled(qtbot, lambda: not page.busy and not services.status.busy)
    with Project.open(project.root) as contender:
        assert contender.read_only, "the live window must retain its real writer lock"
    before = view_state(page)
    assert outcome(window.close) is True, "native window close was refused or raised"
    assert not window.isVisible()
    assert services.project is None and services.watcher.watching is None
    assert all(not thread.is_alive() for thread in threads)
    assert all(any(thread is item for item in joined) for thread in threads)
    assert not any(thread is owned for thread in threading.enumerate() for owned in threads)
    with Project.open(project.root) as reopened:
        assert not reopened.read_only, "native close retained the actual writer lock"
    inject_obsolete(watcher, services)
    assert view_state(page) == before and not services.status.busy
