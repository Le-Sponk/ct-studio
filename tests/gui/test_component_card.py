"""The read-only dashboard card renders registry data without checking files."""

from __future__ import annotations

import builtins
import hashlib
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QPushButton, QWidget
from pytestqt.qtbot import QtBot

from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS, ComponentSpec
from ctstudio.core.components.state import GENERATED_DIR
from ctstudio.core.components.status import STATE_LABELS, ComponentStatus, State
from ctstudio.core.project.project import Project
from ctstudio.gui.views.component_card import ComponentCard

pytestmark = pytest.mark.gui


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "Circuit café 空", "Synthetic track") as opened:
        yield opened


@pytest.mark.parametrize("spec", COMPONENTS, ids=lambda spec: spec.id)
def test_initial_card_is_plain_registry_content(qtbot: QtBot, spec: ComponentSpec) -> None:
    card = ComponentCard(spec)
    qtbot.addWidget(card)
    assert card.objectName() == f"card_{spec.id}"
    assert (card.status_label.text(), card.summary.text()) == ("Not checked", spec.description)
    assert card.path is None
    assert not card.copy_button.isEnabled()
    assert (
        card.status_label.objectName(),
        card.summary.objectName(),
        card.mode_label.objectName(),
        card.copy_button.objectName(),
    ) == (f"{spec.id}State", f"{spec.id}Summary", f"{spec.id}Mode", f"{spec.id}CopyPath")
    assert card.copy_button.accessibleName() == f"Copy {spec.name} path"
    labels = card.findChildren(QLabel)
    assert spec.name in [label.text() for label in labels]
    assert all(label.textFormat() == Qt.TextFormat.PlainText for label in labels)
    assert all(not widget.styleSheet() for widget in [card, *labels, card.copy_button])


@pytest.mark.parametrize("state", list(State))
def test_each_status_has_core_words_and_a_native_icon(qtbot: QtBot, state: State) -> None:
    card = ComponentCard(COMPONENT_BY_ID["course_model"])
    qtbot.addWidget(card)
    reasons = ("First reason <b>not markup</b>", "Second reason", "Third reason")
    card.show_status(ComponentStatus(state, reasons))
    assert (card.status_label.text(), card.summary.text()) == (STATE_LABELS[state], reasons[0])
    icon = card.findChild(QLabel, "course_modelIcon")
    assert icon is not None
    assert not icon.pixmap().isNull()
    for reason in reasons:
        assert reason in card.summary.toolTip()
        assert reason in card.summary.accessibleDescription()
        assert reason in card.toolTip()
    assert card.status_label.textFormat() == Qt.TextFormat.PlainText
    assert card.summary.textFormat() == Qt.TextFormat.PlainText


@pytest.mark.parametrize("state", list(State))
def test_reasonless_status_uses_description_and_clears_old_reasons(
    qtbot: QtBot, state: State
) -> None:
    spec = COMPONENT_BY_ID["kmp"]
    card = ComponentCard(spec)
    qtbot.addWidget(card)
    card.show_status(ComponentStatus(State.ERROR, ("old reason",)))
    card.show_status(ComponentStatus(state))
    assert card.summary.text() == spec.description
    assert "old reason" not in card.summary.toolTip()
    card.show_status(None)
    assert (card.status_label.text(), card.summary.text()) == ("Not checked", spec.description)
    assert "old reason" not in card.summary.accessibleDescription()
    icon = card.findChild(QLabel, "kmpIcon")
    assert icon is not None
    assert icon.pixmap().isNull()


def test_markup_looking_registry_text_remains_plain(qtbot: QtBot) -> None:
    spec = replace(COMPONENT_BY_ID["kmp"], name="<b>Name</b>", description="<img src='x'>")
    card = ComponentCard(spec)
    qtbot.addWidget(card)
    labels = card.findChildren(QLabel)
    assert spec.name in [label.text() for label in labels]
    assert card.summary.text() == spec.description
    assert all(label.textFormat() == Qt.TextFormat.PlainText for label in labels)


@pytest.mark.parametrize(
    ("component", "mode", "planned"),
    [
        ("course_model", "auto", f"{GENERATED_DIR}/course_model.brres"),
        ("kcl", "auto", f"{GENERATED_DIR}/course.kcl"),
        ("minimap", "auto", f"{GENERATED_DIR}/map_model.brres"),
        ("skybox", "auto", f"{GENERATED_DIR}/vrcorn_model.brres"),
        ("kmp", "manual", None),
        ("posteffect", "template", f"{GENERATED_DIR}/posteffect"),
        ("track_info", "manual", "ctstudio.toml"),
        ("objects", "auto", None),
    ],
)
def test_default_paths_are_lexical_and_modes_explicit(
    qtbot: QtBot, project: Project, component: str, mode: str, planned: str | None
) -> None:
    card = ComponentCard(COMPONENT_BY_ID[component])
    qtbot.addWidget(card)
    card.bind(project)
    assert card.path == (None if planned is None else project.root / planned)
    assert card.mode_label.text() == f"Mode: {mode}"
    assert card.copy_button.isEnabled() == (planned is not None)
    if planned is not None:
        assert str(project.root / planned) in card.copy_button.toolTip()
        assert "may not" in card.copy_button.toolTip().lower()


@pytest.mark.parametrize(
    "component", ["course_model", "kcl", "minimap", "skybox", "kmp", "posteffect"]
)
@pytest.mark.parametrize("chosen", [None, "files/own café 空", "absolute"])
def test_manual_paths_use_chosen_file_not_generated_output(
    qtbot: QtBot, project: Project, tmp_path: Path, component: str, chosen: str | None
) -> None:
    file = str(tmp_path / "external café" / "own file") if chosen == "absolute" else chosen
    table = replace(getattr(project.manifest.components, component), mode="manual", file=file)
    project.manifest = replace(
        project.manifest, components=replace(project.manifest.components, **{component: table})
    )
    card = ComponentCard(COMPONENT_BY_ID[component])
    qtbot.addWidget(card)
    card.bind(project)
    assert card.path == (None if file is None else project.root / Path(file))
    assert card.copy_button.isEnabled() == (file is not None)
    assert card.mode_label.text() == "Mode: manual"


def test_template_mode_ignores_old_manual_file(qtbot: QtBot, project: Project) -> None:
    skybox = replace(project.manifest.components.skybox, mode="template", file="old.brres")
    project.manifest = replace(
        project.manifest, components=replace(project.manifest.components, skybox=skybox)
    )
    card = ComponentCard(COMPONENT_BY_ID["skybox"])
    qtbot.addWidget(card)
    card.bind(project)
    assert card.path == project.root / GENERATED_DIR / "vrcorn_model.brres"
    assert card.mode_label.text() == "Mode: template"


def test_rebind_clears_old_status_path_and_reasons(
    qtbot: QtBot, project: Project, tmp_path: Path
) -> None:
    first = replace(project.manifest.components.kmp, file="files/old.kmp")
    project.manifest = replace(
        project.manifest, components=replace(project.manifest.components, kmp=first)
    )
    card = ComponentCard(COMPONENT_BY_ID["kmp"])
    qtbot.addWidget(card)
    card.bind(project)
    card.show_status(ComponentStatus(State.ERROR, ("previous project reason",)))
    with Project.create(tmp_path / "New 空", "Second") as other:
        card.bind(other)
        assert card.path is None
        assert not card.copy_button.isEnabled()
        assert "old.kmp" not in card.copy_button.toolTip()
        assert card.status_label.text() == "Not checked"
        assert card.summary.text() == COMPONENT_BY_ID["kmp"].description
        assert "previous project reason" not in card.summary.accessibleDescription()
        second = replace(other.manifest.components.kmp, file="files/new.kmp")
        other.manifest = replace(
            other.manifest, components=replace(other.manifest.components, kmp=second)
        )
        card.bind(other)
        assert card.path == other.root / "files/new.kmp"
        assert card.copy_button.isEnabled()


@pytest.mark.parametrize("read_only", [False, True])
@pytest.mark.parametrize("keyboard", [False, True])
def test_copy_uses_real_click_or_space_even_when_read_only(
    qtbot: QtBot, qapp: QApplication, project: Project, read_only: bool, keyboard: bool
) -> None:
    if read_only:
        project.close()
    card = ComponentCard(COMPONENT_BY_ID["course_model"])
    qtbot.addWidget(card)
    card.bind(project)
    card.show_status(ComponentStatus(State.ERROR, ("A build needs tools",)))
    clipboard = qapp.clipboard()
    previous = clipboard.text()
    try:
        clipboard.setText("untouched")
        card.show()
        if keyboard:
            card.copy_button.setFocus()
            qtbot.waitUntil(card.copy_button.hasFocus)
            QTest.keyClick(card.copy_button, Qt.Key.Key_Space)
        else:
            QTest.mouseClick(card.copy_button, Qt.MouseButton.LeftButton)
        assert clipboard.text() == str(project.root / GENERATED_DIR / "course_model.brres")
    finally:
        clipboard.setText(previous)


@pytest.mark.parametrize("component", ["kmp", "objects"])
def test_disabled_copy_does_not_clobber_clipboard(
    qtbot: QtBot, qapp: QApplication, project: Project, component: str
) -> None:
    card = ComponentCard(COMPONENT_BY_ID[component])
    qtbot.addWidget(card)
    card.bind(project)
    card.show()
    previous = qapp.clipboard().text()
    try:
        qapp.clipboard().setText("keep this")
        QTest.mouseClick(card.copy_button, Qt.MouseButton.LeftButton)
        QTest.keyClick(card.copy_button, Qt.Key.Key_Space)
        card.copy_button.clicked.emit()
        assert qapp.clipboard().text() == "keep this"
    finally:
        qapp.clipboard().setText(previous)


def test_copy_tracks_rebind_and_preserves_lexical_path(
    qtbot: QtBot, qapp: QApplication, project: Project
) -> None:
    card = ComponentCard(COMPONENT_BY_ID["kmp"])
    qtbot.addWidget(card)
    previous = qapp.clipboard().text()
    try:
        for file in ("files/../café 空.kmp", "files/<b>literal</b>.kmp"):
            kmp = replace(project.manifest.components.kmp, file=file)
            project.manifest = replace(
                project.manifest, components=replace(project.manifest.components, kmp=kmp)
            )
            card.bind(project)
            card.copy_button.click()
            assert qapp.clipboard().text() == str(project.root / file)
            assert str(project.root / file) in card.copy_button.toolTip()
            assert all(
                label.textFormat() == Qt.TextFormat.PlainText for label in card.findChildren(QLabel)
            )
    finally:
        qapp.clipboard().setText(previous)


@pytest.mark.parametrize("spec", COMPONENTS, ids=lambda spec: spec.id)
@pytest.mark.parametrize("manual", [False, True])
def test_bind_and_status_never_touch_files(
    qtbot: QtBot,
    project: Project,
    monkeypatch: pytest.MonkeyPatch,
    spec: ComponentSpec,
    manual: bool,
) -> None:
    if manual and spec.manifest_table not in (None, "project"):
        table = replace(
            getattr(project.manifest.components, spec.manifest_table),
            mode="manual",
            file="files/own",
        )
        project.manifest = replace(
            project.manifest,
            components=replace(project.manifest.components, **{spec.manifest_table: table}),
        )
    card = ComponentCard(spec)
    qtbot.addWidget(card)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Rendering must not access the filesystem")

    with monkeypatch.context() as blocked:
        for method in (
            "stat",
            "is_file",
            "is_dir",
            "exists",
            "resolve",
            "read_bytes",
            "read_text",
            "open",
            "write_bytes",
            "write_text",
            "mkdir",
            "iterdir",
        ):
            blocked.setattr(Path, method, forbidden)
        blocked.setattr(builtins, "open", forbidden)
        blocked.setattr(hashlib, "blake2b", forbidden)
        blocked.setattr(Project, "save", forbidden)
        card.bind(project)
        for state in State:
            card.show_status(ComponentStatus(state, ("No I/O",)))
        card.show_status(None)
    assert card.status_label.text() == "Not checked"


def test_two_column_layout_fits_720_and_keyboard_tab_order(qtbot: QtBot, project: Project) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    layout = QGridLayout(host)
    cards: list[ComponentCard] = []
    for index, spec in enumerate(COMPONENTS):
        card = ComponentCard(spec)
        card.bind(project)
        card.show_status(ComponentStatus(State.EDITED_EXTERNALLY))
        layout.addWidget(card, index // 2, index % 2)
        cards.append(card)
    host.resize(720, 720)
    host.show()
    assert host.width() == 720
    for card in cards:
        assert card.width() <= host.width() // 2
        assert card.height() < 190
        assert card.copy_button.geometry().right() <= card.width()
        assert card.status_label.width() >= card.status_label.fontMetrics().horizontalAdvance(
            card.status_label.text()
        )
    cards[0].copy_button.setFocus()
    qtbot.waitUntil(cards[0].copy_button.hasFocus)
    QTest.keyClick(cards[0].copy_button, Qt.Key.Key_Tab)
    qtbot.waitUntil(cards[0].more_button.hasFocus)
    QTest.keyClick(cards[0].more_button, Qt.Key.Key_Tab)
    qtbot.waitUntil(cards[1].copy_button.hasFocus)
    assert len(host.findChildren(QPushButton)) == 2 * len(COMPONENTS)


def test_long_reason_does_not_make_an_enormous_card(qtbot: QtBot, project: Project) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    layout = QGridLayout(host)
    card = ComponentCard(COMPONENT_BY_ID["kmp"])
    card.bind(project)
    reason = "A very long missing path: " + "unbroken" * 100 + "\nmore details" * 30
    card.show_status(ComponentStatus(State.MISSING, (reason, "Other reason")))
    layout.addWidget(card, 0, 0)
    layout.addWidget(ComponentCard(COMPONENT_BY_ID["kcl"]), 0, 1)
    host.resize(720, 240)
    host.show()
    assert host.width() == 720
    assert host.height() <= 240
    assert card.summary.height() <= card.summary.fontMetrics().lineSpacing() * 3
    assert reason in card.summary.toolTip()
    assert "Other reason" in card.summary.accessibleDescription()


@pytest.mark.parametrize("dark", [False, True])
def test_inherits_parent_palette_without_stylesheets(qtbot: QtBot, dark: bool) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    palette = host.palette()
    palette.setColor(
        QPalette.ColorRole.Window, Qt.GlobalColor.black if dark else Qt.GlobalColor.white
    )
    palette.setColor(
        QPalette.ColorRole.WindowText, Qt.GlobalColor.white if dark else Qt.GlobalColor.black
    )
    host.setPalette(palette)
    card = ComponentCard(COMPONENT_BY_ID["kmp"], host)
    card.show_status(ComponentStatus(State.WARNING, ("A reason",)))
    assert card.parentWidget() is host
    for widget in (card, *card.findChildren(QLabel), card.copy_button):
        assert widget.palette().color(QPalette.ColorRole.Window) == palette.color(
            QPalette.ColorRole.Window
        )
        assert widget.palette().color(QPalette.ColorRole.WindowText) == palette.color(
            QPalette.ColorRole.WindowText
        )
        assert not widget.styleSheet()
