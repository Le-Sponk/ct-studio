"""P5-T04b: a card takes one dropped file or folder, or offers Choose file… (signals only)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from assign_helpers import ATTACHABLE, drag_enter, drop, local
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS, ComponentSpec
from ctstudio.core.project.project import Project
from ctstudio.gui.views.component_card import ComponentCard

pytestmark = pytest.mark.gui
NOT_ATTACHABLE = tuple(spec.id for spec in COMPONENTS if spec.id not in ATTACHABLE)
DROP_ONE = "Drop one file or folder from this computer. Nothing was changed."


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "Circuit café 空", "Synthetic track") as opened:
        yield opened


def card_for(qtbot: QtBot, part: str, project: Project, *, enabled: bool = True) -> ComponentCard:
    card = ComponentCard(COMPONENT_BY_ID[part])
    qtbot.addWidget(card)
    card.bind(project)
    card.set_actions_enabled(enabled)
    return card


def requests(card: ComponentCard) -> QSignalSpy:
    return QSignalSpy(card.assign_requested)


def emitted(spy: QSignalSpy) -> list[list[object]]:
    return [spy.at(index) for index in range(spy.count())]


class Chooser:
    def __init__(self, answer: Path | None, during: object = None) -> None:
        self.answer = answer
        self.during = during
        self.calls: list[tuple[QWidget, ComponentSpec, Path]] = []

    def __call__(self, parent: QWidget, spec: ComponentSpec, start: Path) -> Path | None:
        self.calls.append((parent, spec, start))
        if callable(self.during):
            self.during()
        return self.answer


def test_the_registry_says_which_parts_take_a_file() -> None:
    attachable = tuple(
        spec.id
        for spec in COMPONENTS
        if "manual" in spec.modes and spec.manifest_table not in (None, "project")
    )
    assert attachable == ATTACHABLE


@pytest.mark.parametrize("part", ATTACHABLE)
def test_one_dropped_local_file_requests_a_copy(
    qtbot: QtBot, project: Project, tmp_path: Path, part: str
) -> None:
    card = card_for(qtbot, part, project)
    spy = requests(card)
    source = tmp_path / "Mes fichiers 日本" / "piste déjà.bin"
    assert card.acceptDrops()
    assert drag_enter(card, local(source))
    assert drop(card, local(source))
    assert emitted(spy) == [[part, source, False]]
    assert card.assign_note.isHidden(), "the dashboard reports the result, not the card itself"


@pytest.mark.parametrize("part", NOT_ATTACHABLE)
def test_parts_without_a_file_take_no_drop_and_offer_no_file_actions(
    qtbot: QtBot, project: Project, tmp_path: Path, part: str
) -> None:
    card = card_for(qtbot, part, project)
    spy = requests(card)
    menu = card.more_button.menu()
    assert menu is not None
    assert not card.acceptDrops()
    assert not drag_enter(card, local(tmp_path / "x.kcl"))
    assert not drop(card, local(tmp_path / "x.kcl"))
    assert card.choose_action not in menu.actions()
    assert card.reference_action not in menu.actions()
    assert not card.choose_action.isEnabled() and not card.reference_action.isEnabled()
    card.choose = Chooser(tmp_path / "x.kcl")
    card.choose_action.trigger()
    assert spy.count() == 0


@pytest.mark.parametrize("read_only", [False, True])
def test_unavailable_cards_refuse_drops_and_file_actions(
    qtbot: QtBot, project: Project, tmp_path: Path, read_only: bool
) -> None:
    if read_only:
        with Project.open(project.root) as other:
            assert other.read_only
            card = card_for(qtbot, "kcl", other)
            assert_refuses(card, tmp_path)
    else:
        assert_refuses(card_for(qtbot, "kcl", project, enabled=False), tmp_path)


def assert_refuses(card: ComponentCard, tmp_path: Path) -> None:
    spy = requests(card)
    chooser = Chooser(tmp_path / "x.kcl")
    card.choose = chooser
    assert not drag_enter(card, local(tmp_path / "x.kcl"))
    assert not drop(card, local(tmp_path / "x.kcl"))
    assert not card.choose_action.isEnabled() and not card.reference_action.isEnabled()
    card.choose_action.trigger()
    card.reference_action.trigger()
    assert chooser.calls == [] and spy.count() == 0


@pytest.mark.parametrize(
    "urls",
    [
        lambda tmp: local(tmp / "a.kcl", tmp / "b.kcl"),
        lambda tmp: [QUrl("https://example.com/course.kcl")],
        lambda tmp: [],
    ],
    ids=["two-files", "web-link", "no-file"],
)
def test_anything_but_one_local_file_is_explained_on_the_card(
    qtbot: QtBot, project: Project, tmp_path: Path, urls: object
) -> None:
    card = card_for(qtbot, "kcl", project)
    spy = requests(card)
    assert callable(urls)
    assert not drop(card, urls(tmp_path))
    assert spy.count() == 0
    assert card.assign_note.text() == DROP_ONE
    assert not card.assign_note.isHidden()
    assert card.assign_note.toolTip() == DROP_ONE
    assert card.assign_note.accessibleDescription() == DROP_ONE
    card.bind(project)
    assert card.assign_note.text() == "" and card.assign_note.isHidden()
    assert card.assign_note.accessibleDescription() == ""


@pytest.mark.parametrize("reference", [False, True])
def test_menu_actions_use_the_injected_chooser(
    qtbot: QtBot, project: Project, tmp_path: Path, reference: bool
) -> None:
    card = card_for(qtbot, "kcl", project)
    spy = requests(card)
    chosen = tmp_path / "Choisi 日本.kcl"
    chooser = Chooser(chosen)
    card.choose = chooser
    (card.reference_action if reference else card.choose_action).trigger()
    assert [(parent, spec.id, start) for parent, spec, start in chooser.calls] == [
        (card, "kcl", project.root)
    ]
    assert emitted(spy) == [["kcl", chosen, reference]]


def test_a_cancelled_chooser_requests_nothing(
    qtbot: QtBot, project: Project, tmp_path: Path
) -> None:
    card = card_for(qtbot, "kcl", project)
    spy = requests(card)
    card.choose = Chooser(None)
    card.choose_action.trigger()
    card.reference_action.trigger()
    assert spy.count() == 0


def test_a_card_that_became_unavailable_while_choosing_requests_nothing(
    qtbot: QtBot, project: Project, tmp_path: Path
) -> None:
    card = card_for(qtbot, "kcl", project)
    spy = requests(card)
    card.choose = Chooser(tmp_path / "x.kcl", during=lambda: card.set_actions_enabled(False))
    card.choose_action.trigger()
    assert spy.count() == 0


def test_a_card_rebound_while_choosing_requests_nothing(
    qtbot: QtBot, project: Project, tmp_path: Path
) -> None:
    card = card_for(qtbot, "kcl", project)
    spy = requests(card)
    with Project.create(tmp_path / "Autre", "Other") as other:
        card.choose = Chooser(tmp_path / "x.kcl", during=lambda: card.bind(other))
        card.choose_action.trigger()
    assert spy.count() == 0


@pytest.mark.parametrize("part", ATTACHABLE)
def test_labels_say_file_or_folder_and_explain_copy_and_reference(
    qtbot: QtBot, project: Project, part: str
) -> None:
    card = card_for(qtbot, part, project)
    noun = "folder" if part == "posteffect" else "file"
    menu = card.more_button.menu()
    assert menu is not None
    actions = menu.actions()
    start = actions.index(card.reveal_action) + 1
    choose, reference = card.choose_action, card.reference_action
    assert actions[start : start + 2] == [choose, reference]
    assert [(a.text(), a.objectName(), a.isEnabled()) for a in (choose, reference)] == [
        (f"Choose {noun}…", f"{part}ChooseFile", True),
        (f"Reference {noun} in place…", f"{part}ReferenceFile", True),
    ]
    assert ["backed up" in choose.toolTip(), "nothing is copied" in reference.toolTip()] == [
        True,
        True,
    ]
    assert card.more_button.isEnabled()


def test_a_part_with_only_manual_mode_still_offers_the_file_actions(
    qtbot: QtBot, project: Project
) -> None:
    card = card_for(qtbot, "kmp", project)
    assert card.path is None and card.mode_button.isHidden()
    assert card.more_button.isEnabled()
    card.set_actions_enabled(False)
    assert not card.more_button.isEnabled()


def test_keyboard_reaches_choose_file_through_the_more_menu(
    qtbot: QtBot, qapp: QApplication, project: Project, tmp_path: Path
) -> None:
    card = card_for(qtbot, "kcl", project)
    card.show()
    qtbot.waitExposed(card)
    card.activateWindow()
    QApplication.processEvents()
    spy = requests(card)
    chosen = tmp_path / "clavier.kcl"
    card.choose = Chooser(chosen)
    card.copy_button.setFocus()
    assert card.copy_button.hasFocus()
    QTest.keyClick(card.copy_button, Qt.Key.Key_Tab)
    assert card.more_button.hasFocus()
    menu = card.more_button.menu()
    assert menu is not None
    opened: list[bool] = []

    def choose() -> None:
        opened.append(menu.isVisible())
        try:
            menu.setActiveAction(card.choose_action)
            QTest.keyClick(menu, Qt.Key.Key_Return)
        finally:
            menu.hide()

    QTimer.singleShot(0, choose)
    QTest.keyClick(card.more_button, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: bool(opened))
    assert opened == [True]
    assert emitted(spy) == [["kcl", chosen, False]]


def test_a_card_disabled_during_a_drag_refuses_the_drop(
    qtbot: QtBot, project: Project, tmp_path: Path
) -> None:
    card = card_for(qtbot, "kcl", project)
    spy = requests(card)
    urls = local(tmp_path / "x.kcl")
    assert drag_enter(card, urls)
    card.set_actions_enabled(False)  # e.g. a build started while the file was being dragged
    assert not drop(card, urls)
    assert spy.count() == 0
    assert not drag_enter(card, urls)
    assert card.assign_note.text() == ""


def test_a_long_note_wraps_within_the_card(qtbot: QtBot, project: Project) -> None:
    card = card_for(qtbot, "kcl", project)
    card.resize(340, 400)
    card.show()
    card.show_assign_note("A long explanation " * 12)
    QApplication.processEvents()
    note = card.assign_note
    assert note.wordWrap()
    assert note.width() <= card.width()
    assert note.height() >= 2 * note.fontMetrics().lineSpacing(), "it wraps onto more lines"
    assert note.height() <= 4 * note.fontMetrics().lineSpacing(), "but stays a few lines"


def test_a_drag_without_files_is_not_offered(qtbot: QtBot, project: Project) -> None:
    card = card_for(qtbot, "kcl", project)
    data = QMimeData()
    data.setText("C:/somewhere/course.kcl")  # plain text, e.g. dragged from an editor
    event = QDragEnterEvent(
        QPoint(5, 5),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(card, event)
    assert not event.isAccepted()


@pytest.mark.parametrize(
    "modifier", [Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.NoModifier]
)
def test_a_drop_is_always_a_copy_so_the_original_is_never_moved(
    qtbot: QtBot, project: Project, tmp_path: Path, modifier: Qt.KeyboardModifier
) -> None:
    card = card_for(qtbot, "kcl", project)
    spy = requests(card)
    data = QMimeData()
    data.setUrls(local(tmp_path / "x.kcl"))
    actions = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction | Qt.DropAction.LinkAction
    enter = QDragEnterEvent(QPoint(5, 5), actions, data, Qt.MouseButton.LeftButton, modifier)
    QApplication.sendEvent(card, enter)
    event = QDropEvent(QPointF(5, 5), actions, data, Qt.MouseButton.LeftButton, modifier)
    QApplication.sendEvent(card, event)
    assert (enter.isAccepted(), enter.dropAction()) == (True, Qt.DropAction.CopyAction)
    assert (event.isAccepted(), event.dropAction()) == (True, Qt.DropAction.CopyAction)
    assert spy.count() == 1


def test_a_drag_that_can_only_move_is_not_offered(
    qtbot: QtBot, project: Project, tmp_path: Path
) -> None:
    card = card_for(qtbot, "kcl", project)
    spy = requests(card)
    data = QMimeData()
    data.setUrls(local(tmp_path / "x.kcl"))
    move = Qt.DropAction.MoveAction
    nm = Qt.KeyboardModifier.NoModifier
    enter = QDragEnterEvent(QPoint(5, 5), move, data, Qt.MouseButton.LeftButton, nm)
    QApplication.sendEvent(card, enter)
    event = QDropEvent(QPointF(5, 5), move, data, Qt.MouseButton.LeftButton, nm)
    QApplication.sendEvent(card, event)
    assert (enter.isAccepted(), event.isAccepted(), spy.count()) == (False, False, 0)
    # The drop itself also refuses it (not only the drag-enter), e.g. when a platform skips it.
    direct = QDropEvent(QPointF(5, 5), move, data, Qt.MouseButton.LeftButton, nm)
    card.dropEvent(direct)
    assert (direct.isAccepted(), spy.count()) == (False, 0)
