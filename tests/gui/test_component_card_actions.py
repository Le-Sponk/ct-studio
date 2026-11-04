"""Registry-driven card actions request edits without publishing draft state."""

from __future__ import annotations

import builtins
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QGridLayout, QMenu, QToolButton, QWidget
from pytestqt.qtbot import QtBot

from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS, ComponentSpec
from ctstudio.core.components.status import STATE_LABELS, ComponentStatus, State
from ctstudio.core.project.project import Project
from ctstudio.gui.views.component_card import ComponentCard

pytestmark = pytest.mark.gui
EDITABLE = tuple(spec for spec in COMPONENTS if len(spec.modes) > 1)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "Circuit café 空", "Synthetic track") as opened:
        yield opened


def set_mode(project: Project, component: str, mode: str) -> None:
    table = replace(getattr(project.manifest.components, component), mode=mode)
    project.manifest = replace(
        project.manifest, components=replace(project.manifest.components, **{component: table})
    )


def checked_modes(card: ComponentCard) -> list[str]:
    return [mode for mode, action in card.mode_actions.items() if action.isChecked()]


@pytest.mark.parametrize("spec", COMPONENTS, ids=lambda spec: spec.id)
def test_registry_controls_start_disabled(qtbot: QtBot, spec: ComponentSpec) -> None:
    card = ComponentCard(spec)
    qtbot.addWidget(card)
    editable = spec.id in {"course_model", "kcl", "minimap", "skybox", "posteffect"}
    assert_primary_contract(card, spec, editable)
    assert_overflow_contract(card, spec)
    assert_menu_contract(card, spec.modes if editable else ())
    for action in card.mode_actions.values():
        assert action.isCheckable()
        assert not action.isEnabled()


def assert_primary_contract(card: ComponentCard, spec: ComponentSpec, editable: bool) -> None:
    assert card.mode_button.text() == "Change mode…"
    assert card.mode_button.objectName() == f"{spec.id}ChangeMode"
    assert card.mode_button.isHidden() != editable
    assert not card.mode_button.isEnabled()
    assert card.mode_button.toolTip()
    assert card.mode_button.accessibleDescription() == card.mode_button.toolTip()


def assert_overflow_contract(card: ComponentCard, spec: ComponentSpec) -> None:
    assert isinstance(card.more_button, QToolButton)
    assert card.more_button.objectName() == f"{spec.id}MoreActions"
    assert card.more_button.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup
    assert card.more_button.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert card.more_button.accessibleName()
    assert not card.more_button.isEnabled()
    assert card.more_button.toolTip()
    assert card.more_button.accessibleDescription() == card.more_button.toolTip()


def assert_menu_contract(card: ComponentCard, modes: tuple[str, ...]) -> None:
    menu = card.more_button.menu()
    assert menu is not None
    assert_copy_entry(card, menu)
    assert list(card.mode_actions) == list(modes)
    submenus = [action.menu() for action in menu.actions() if isinstance(action.menu(), QMenu)]
    assert len(submenus) == int(bool(modes))
    if modes:
        assert isinstance(submenus[0], QMenu)
        assert submenus[0].title() == "Mode"
        assert submenus[0].actions() == list(card.mode_actions.values())


def assert_copy_entry(card: ComponentCard, menu: QMenu) -> None:
    assert menu.actions()[0] is card.copy_action
    assert card.copy_action.text() == "Copy path"
    assert not card.copy_action.isEnabled()


def test_primary_requires_explicit_gate_and_emits_dialog_current_mode(
    qtbot: QtBot, project: Project
) -> None:
    card = ComponentCard(COMPONENT_BY_ID["skybox"])
    qtbot.addWidget(card)
    spy = QSignalSpy(card.mode_requested)
    card.bind(project)
    assert not card.mode_button.isEnabled()
    card.mode_button.clicked.emit()
    assert spy.count() == 0
    card.set_actions_enabled(True)
    assert card.mode_button.isEnabled()
    assert card.more_button.isEnabled()
    card.mode_button.click()
    assert spy.count() == 1
    assert spy.at(0) == ["skybox", ""]
    card.set_actions_enabled(False)
    card.mode_button.clicked.emit()
    assert spy.count() == 1
    assert card.copy_button.isEnabled()
    assert card.more_button.isEnabled()


@pytest.mark.parametrize("spec", EDITABLE, ids=lambda spec: spec.id)
def test_every_menu_mode_requests_only_and_restores_persisted_check_before_emitting(
    qtbot: QtBot, project: Project, spec: ComponentSpec
) -> None:
    card = ComponentCard(spec)
    qtbot.addWidget(card)
    card.set_actions_enabled(True)
    spy = QSignalSpy(card.mode_requested)
    observed: list[list[str]] = []

    def observe(_component: str, _mode: str) -> None:
        observed.append(checked_modes(card))

    card.mode_requested.connect(observe)
    original_bytes = project.manifest_path.read_bytes()
    for persisted in spec.modes:
        set_mode(project, spec.id, persisted)
        snapshot = project.manifest
        card.bind(project)
        card.show_status(ComponentStatus(State.ERROR, ("Retain this diagnosis", "Details")))
        path = card.path
        assert checked_modes(card) == [persisted]
        for requested in spec.modes:
            before = spy.count()
            card.mode_actions[requested].trigger()
            assert spy.count() == before + 1
            assert spy.at(before) == [spec.id, requested]
            assert observed[-1] == [persisted]
            assert_retained(card, project, snapshot, persisted, path)
        card.set_actions_enabled(False)
        assert checked_modes(card) == [persisted]
        assert card.summary.text() == "Retain this diagnosis"
        card.set_actions_enabled(True)
    assert project.manifest_path.read_bytes() == original_bytes


def assert_retained(
    card: ComponentCard, project: Project, snapshot: object, mode: str, path: Path | None
) -> None:
    assert checked_modes(card) == [mode]
    assert card.mode_label.text() == f"Mode: {mode}"
    assert card.path == path
    assert card.status_label.text() == STATE_LABELS[State.ERROR]
    assert card.summary.text() == "Retain this diagnosis"
    assert "Details" in card.summary.accessibleDescription()
    assert project.manifest is snapshot


@pytest.mark.parametrize("state", ["unbound", "busy", "read_only", "closed"])
def test_disabled_mode_requests_recheck_live_eligibility(
    qtbot: QtBot, project: Project, state: str
) -> None:
    card = ComponentCard(COMPONENT_BY_ID["skybox"])
    qtbot.addWidget(card)
    card.set_actions_enabled(True)
    spy = QSignalSpy(card.mode_requested)
    if state != "unbound":
        card.bind(project)
    if state == "busy":
        card.set_actions_enabled(False)
    elif state == "read_only":
        with Project.open(project.root) as reader:
            assert reader.read_only
            card.bind(reader)
            card.set_actions_enabled(True)
            assert_mode_disabled(card)
    elif state == "closed":
        project.close()  # No rebind: a stale enabled widget still cannot emit.
    card.mode_button.setEnabled(True)
    card.mode_button.clicked.emit()
    for action in card.mode_actions.values():
        action.setEnabled(True)
        action.trigger()
    assert spy.count() == 0
    assert checked_modes(card) == ["auto"]


def assert_mode_disabled(card: ComponentCard) -> None:
    assert not card.mode_button.isEnabled()
    assert all(not action.isEnabled() for action in card.mode_actions.values())


def test_unknown_mode_is_displayed_but_never_offered_or_emitted(
    qtbot: QtBot, project: Project
) -> None:
    set_mode(project, "skybox", "future-mode")
    card = ComponentCard(COMPONENT_BY_ID["skybox"])
    qtbot.addWidget(card)
    card.bind(project)
    card.set_actions_enabled(True)
    assert card.mode_label.text() == "Mode: future-mode"
    assert checked_modes(card) == []
    spy = QSignalSpy(card.mode_requested)
    action = card.mode_actions["manual"]
    action.setData("future-mode")
    action.trigger()
    assert spy.count() == 0
    assert checked_modes(card) == []
    card.mode_button.click()
    assert spy.count() == 1
    assert spy.at(0) == ["skybox", ""]


@pytest.mark.parametrize("spec", COMPONENTS, ids=lambda spec: spec.id)
@pytest.mark.parametrize("enabled", [False, True])
def test_bound_registry_gate_leaves_copy_independent(
    qtbot: QtBot, project: Project, spec: ComponentSpec, enabled: bool
) -> None:
    card = ComponentCard(spec)
    qtbot.addWidget(card)
    card.bind(project)
    card.set_actions_enabled(enabled)
    editable = spec in EDITABLE and enabled
    copyable = spec.id not in {"objects", "kmp"}
    assert card.mode_button.isEnabled() == editable
    assert all(action.isEnabled() == editable for action in card.mode_actions.values())
    assert card.copy_button.isEnabled() == copyable
    assert card.copy_action.isEnabled() == copyable
    assert card.copy_action.toolTip() == card.copy_button.toolTip()
    assert card.more_button.isEnabled() == (copyable or editable)
    spy = QSignalSpy(card.mode_requested)
    card.mode_button.clicked.emit()
    assert spy.count() == int(editable)


@pytest.mark.parametrize("table", [None, "project"])
def test_multiple_modes_without_a_component_table_are_not_editable(
    qtbot: QtBot, project: Project, table: str | None
) -> None:
    spec = replace(COMPONENT_BY_ID["skybox"], manifest_table=table)
    card = ComponentCard(spec)
    qtbot.addWidget(card)
    card.bind(project)
    card.set_actions_enabled(True)
    assert card.mode_button.isHidden()
    assert not card.mode_button.isEnabled()
    assert not card.mode_actions
    spy = QSignalSpy(card.mode_requested)
    card.mode_button.clicked.emit()
    assert spy.count() == 0


@pytest.mark.parametrize("state", ["writable", "busy", "read_only", "closed"])
@pytest.mark.parametrize("chosen", [None, "files/../café 空.brres"])
def test_overflow_copy_mirrors_primary_without_filesystem_checks(
    qtbot: QtBot, qapp: QApplication, project: Project, state: str, chosen: str | None
) -> None:
    table = replace(project.manifest.components.course_model, mode="manual", file=chosen)
    project.manifest = replace(
        project.manifest, components=replace(project.manifest.components, course_model=table)
    )
    card = ComponentCard(COMPONENT_BY_ID["course_model"])
    qtbot.addWidget(card)
    if state in {"read_only", "closed"}:
        project.close()
    card.bind(project)
    card.set_actions_enabled(state != "busy")
    assert card.copy_action.isEnabled() == card.copy_button.isEnabled() == (chosen is not None)
    assert card.copy_action.toolTip() == card.copy_button.toolTip()
    assert card.more_button.isEnabled() == (chosen is not None or state == "writable")
    previous = qapp.clipboard().text()
    try:
        qapp.clipboard().setText("Retain clipboard")
        card.copy_action.trigger()
        expected = "Retain clipboard" if chosen is None else str(project.root / chosen)
        assert qapp.clipboard().text() == expected
    finally:
        qapp.clipboard().setText(previous)


def test_bind_gate_and_requests_never_access_files(
    qtbot: QtBot, project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = ComponentCard(COMPONENT_BY_ID["skybox"])
    qtbot.addWidget(card)
    spy = QSignalSpy(card.mode_requested)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Card actions must not access files")

    with monkeypatch.context() as blocked:
        methods = "stat is_file is_dir exists resolve read_bytes read_text open"
        for method in (methods + " write_bytes write_text mkdir iterdir").split():
            blocked.setattr(Path, method, forbidden)
        blocked.setattr(builtins, "open", forbidden)
        blocked.setattr(Project, "save", forbidden)
        card.bind(project)
        card.set_actions_enabled(True)
        card.mode_button.click()
        card.mode_actions["manual"].trigger()
        card.set_actions_enabled(False)
    assert spy.count() == 2
    assert card.mode_label.text() == "Mode: auto"


def test_keyboard_primary_tab_and_native_overflow_copy(
    qtbot: QtBot, qapp: QApplication, project: Project
) -> None:
    card = ComponentCard(COMPONENT_BY_ID["course_model"])
    qtbot.addWidget(card)
    card.bind(project)
    card.set_actions_enabled(True)
    card.show()
    spy = QSignalSpy(card.mode_requested)
    card.mode_button.setFocus()
    qtbot.waitUntil(card.mode_button.hasFocus)
    QTest.keyClick(card.mode_button, Qt.Key.Key_Space)
    assert spy.count() == 1
    assert spy.at(0) == ["course_model", ""]
    QTest.keyClick(card.mode_button, Qt.Key.Key_Tab)
    assert card.copy_button.hasFocus()
    QTest.keyClick(card.copy_button, Qt.Key.Key_Tab)
    assert card.more_button.hasFocus()
    menu = card.more_button.menu()
    assert menu is not None
    opened: list[bool] = []

    def choose_copy() -> None:
        opened.append(menu.isVisible())
        try:
            menu.setActiveAction(card.copy_action)
            QTest.keyClick(menu, Qt.Key.Key_Return)
        finally:
            menu.hide()

    previous = qapp.clipboard().text()
    try:
        qapp.clipboard().setText("before keyboard menu")
        QTimer.singleShot(0, choose_copy)
        QTest.keyClick(card.more_button, Qt.Key.Key_Space)
        qtbot.waitUntil(lambda: bool(opened))
        assert opened == [True]
        assert qapp.clipboard().text() == str(card.path)
        menu.popup(card.more_button.mapToGlobal(card.more_button.rect().bottomLeft()))
        QTest.keyClick(menu, Qt.Key.Key_Escape)
        assert not menu.isVisible()
        assert spy.count() == 1  # Dismissal does not request or publish a draft mode.
    finally:
        qapp.clipboard().setText(previous)


@pytest.mark.parametrize("dark", [False, True])
def test_actions_keep_native_palette_and_two_column_width(
    qtbot: QtBot, project: Project, dark: bool
) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    palette = host.palette()
    palette.setColor(
        QPalette.ColorRole.Window, Qt.GlobalColor.black if dark else Qt.GlobalColor.white
    )
    host.setPalette(palette)
    layout = QGridLayout(host)
    for index, spec in enumerate(COMPONENTS):
        card = ComponentCard(spec)
        card.bind(project)
        card.set_actions_enabled(True)
        layout.addWidget(card, index // 2, index % 2)
        for widget in (card, card.mode_button, card.copy_button, card.more_button):
            assert not widget.styleSheet()
    host.resize(720, 720)
    host.show()
    assert host.width() == 720
    for card in host.findChildren(ComponentCard):
        assert card.width() <= 360
        assert card.height() < 190
        assert card.more_button.geometry().right() <= card.width()
        assert_native_palette(card, palette)


def assert_native_palette(card: ComponentCard, palette: QPalette) -> None:
    menu = card.more_button.menu()
    assert menu is not None
    assert not menu.styleSheet()
    assert menu.palette().color(QPalette.ColorRole.Window) == QApplication.palette().color(
        QPalette.ColorRole.Window
    )
    for widget in (card.mode_button, card.more_button):
        assert widget.palette().color(QPalette.ColorRole.Window) == palette.color(
            QPalette.ColorRole.Window
        )
