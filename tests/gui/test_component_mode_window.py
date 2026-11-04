"""P5-T03f: component controls use the window's modal project owner."""

from pathlib import Path

import pytest
from component_window_helpers import mode_window
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.project_details import ProjectDetailsDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def test_mode_entry_owns_project_and_cancel_retains_cards(qtbot: QtBot, tmp_path: Path) -> None:
    from test_dashboard_states import ready

    calls: list[tuple[str, str]] = []

    def make_mode(
        services: AppServices, component: str, mode: str, parent: QWidget
    ) -> ProjectDetailsDialog:
        calls.append((component, mode))
        return ProjectDetailsDialog(services, parent=parent)

    window = mode_window(qtbot, tmp_path, make_mode)
    project = window.services.project
    assert project is not None
    window.services.status.updated.emit(ready(project.root))
    before = project.manifest_path.read_bytes()
    window._edit_component("kcl", "manual")
    dialog = window.findChild(ProjectDetailsDialog, "projectDetailsDialog")
    assert dialog is not None
    try:
        qtbot.waitUntil(lambda: not dialog.busy)
        assert calls == [("kcl", "manual")]
        assert_edit_owned(window)
        dialog.reject()
        assert not window.services.editing
        assert window.dashboard.cards["kcl"].status_label.text() == "ready"
        assert project.manifest_path.read_bytes() == before
        assert window.open_project_action.isEnabled()
    finally:
        window.close()


def forbidden_factory(
    _services: AppServices, _component: str, _mode: str, _parent: QWidget
) -> ProjectDetailsDialog:
    raise AssertionError("A blocked component editor was constructed")


def test_main_close_cancels_idle_mode_editor(qtbot: QtBot, tmp_path: Path) -> None:
    window = mode_window(qtbot, tmp_path)
    project = window.services.project
    assert project is not None
    try:
        window.dashboard.cards["kcl"].mode_button.click()
        dialog = window.findChild(ProjectDetailsDialog)
        assert dialog is not None
        qtbot.waitUntil(lambda: not dialog.busy)
        assert window.close()
        assert not window.services.editing
        assert project.lock is None
        assert window.services.project is None
    finally:
        if window.services.editing:
            for editor in window.findChildren(ProjectDetailsDialog):
                qtbot.waitUntil(lambda active=editor: not active.busy)
                editor.reject()
        window.close()


def assert_edit_owned(window: MainWindow) -> None:
    assert window.services.editing
    assert not window.open_project_action.isEnabled()
    assert not window.home_action.isEnabled()
    assert not window.dashboard.refresh_button.isEnabled()
    assert_shutdown_refused(window.services)


def assert_shutdown_refused(services: AppServices) -> None:
    try:
        result: object = services.shutdown(0)
    except Exception as error:
        result = error
    assert result is False


def block_editor(
    window: MainWindow, project: Project, patch: pytest.MonkeyPatch, reason: str
) -> None:
    if reason == "no_project":
        patch.setattr(window.services, "project", None)
    elif reason == "readonly":
        patch.setattr(project, "lock", None)
    elif reason == "closed":
        project.close()
    elif reason == "building":
        patch.setattr(type(window.services.build), "running", property(lambda _self: True))
    elif reason == "checking":
        patch.setattr(window.dashboard, "_checking", True)
    elif reason == "welcome_busy":
        patch.setattr(type(window.welcome), "busy", property(lambda _self: True))
    elif reason == "editing":
        patch.setattr(window.services, "editing", True)


@pytest.mark.parametrize(
    "reason",
    ["no_project", "readonly", "closed", "building", "checking", "welcome_busy", "editing"],
)
def test_window_guards_refuse_direct_requests(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    window = mode_window(qtbot, tmp_path, forbidden_factory)
    project = window.services.project
    assert project is not None
    try:
        with monkeypatch.context() as patch:
            block_editor(window, project, patch, reason)
            window._navigation()
            window.dashboard._sync()
            assert not window.dashboard.cards["kcl"].mode_button.isEnabled()
            window._edit_component("kcl", "manual")
            window.dashboard.mode_requested.emit("kcl", "manual")
            assert window._details is None
    finally:
        window.close()


@pytest.mark.parametrize(
    ("component", "mode"),
    [
        ("unknown", ""),
        ("objects", "auto"),
        ("track_info", "manual"),
        ("kmp", "manual"),
        ("kcl", "template"),
        ("skybox", "AUTO"),
    ],
)
def test_window_rejects_unsupported_component_or_mode(
    qtbot: QtBot, tmp_path: Path, component: str, mode: str
) -> None:
    window = mode_window(qtbot, tmp_path, forbidden_factory)
    try:
        window._edit_component(component, mode)
        assert not window.services.editing
    finally:
        window.close()
