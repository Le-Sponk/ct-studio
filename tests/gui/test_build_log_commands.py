"""P5-T03e33b: trusted CommandRun rows in the live log, and Copy command only for them.

Ordinary output stays literal, even when it looks like a command ("Ran: …", "$ …"); only the
structured ``CommandRun`` event from the process boundary makes a copyable row, and the copy is
the core command text exactly.
"""

import sys
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu
from pytestqt.qtbot import QtBot

from ctstudio.core.build.events import CommandRun, LogLine
from ctstudio.gui.build_log_model import BuildLogModel, LogRole
from ctstudio.gui.views.build_log import BuildLogPanel

pytestmark = [pytest.mark.gui, pytest.mark.timeout(15)]
SHIFT_CTRL = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier

TEXT = '"C:\\Tools\\wszst.exe" create "a b" ""'
COMMAND = CommandRun("stage:kcl", ("C:\\Tools\\wszst.exe", "create", "a b", ""), TEXT)
LOOKALIKES = [
    LogLine("stage:kcl", f"Ran: {TEXT}"),
    LogLine("stage:kcl", "$ rm -rf ~"),
    LogLine("command", "wszst create course.szs"),
]


@pytest.fixture
def clipboard(qapp: QApplication) -> Iterator[QApplication]:
    previous = qapp.clipboard().text()
    qapp.clipboard().setText("untouched")
    yield qapp
    qapp.clipboard().setText(previous)


@pytest.fixture
def panel(qtbot: QtBot) -> BuildLogPanel:
    widget = BuildLogPanel(model=BuildLogModel(max_rows=50, max_line_chars=200))
    qtbot.addWidget(widget)
    widget.resize(520, 260)
    widget.show()
    widget.toggle.click()
    return widget


def settle() -> None:
    for _ in range(6):
        QApplication.processEvents()


def copy_action(panel: BuildLogPanel) -> QAction:
    action = panel.findChild(QAction, "build_log_copy_command")
    assert action is not None, "the log needs a Copy command action"
    return action


def select(panel: BuildLogPanel, row: int) -> None:
    panel.activateWindow()
    settle()  # focus set before the window is active can be lost on activation
    panel.view.setFocus()
    panel.view.setCurrentIndex(panel.model.index(row))
    settle()
    assert panel.view.hasFocus(), "keyboard tests need the list focused"


def test_a_command_event_is_one_distinct_row_with_its_exact_text() -> None:
    model = BuildLogModel()
    model.append(LogLine("stage:kcl", "before"))
    model.append(COMMAND)
    model.append(LogLine("stage:kcl", "after"))
    assert model.rowCount() == 3
    row = model.index(1)
    assert row.data() == f"[stage:kcl] Ran: {TEXT}"
    assert model.data(row, LogRole.Command) == TEXT
    assert model.data(row, LogRole.Text) == f"Ran: {TEXT}"
    assert model.data(row, LogRole.Truncated) is False
    assert "command" in str(model.data(row, Qt.ItemDataRole.AccessibleTextRole)).lower()
    assert _bold(model, 1), "a trusted command row must stand out"
    assert [model.data(model.index(i), LogRole.Command) for i in (0, 2)] == [None, None]
    assert not _bold(model, 0) and not _bold(model, 2)


def _bold(model: BuildLogModel, row: int) -> bool:
    font = model.data(model.index(row), Qt.ItemDataRole.FontRole)
    assert font is None or isinstance(font, QFont)
    return font is not None and font.bold()


@pytest.mark.parametrize("event", LOOKALIKES, ids=["ran-prefix", "dollar", "command-node"])
def test_output_that_looks_like_a_command_is_never_copyable(event: LogLine) -> None:
    model = BuildLogModel()
    model.append(event)
    assert model.rowCount() == 1
    assert model.data(model.index(0), LogRole.Command) is None
    assert not _bold(model, 0)
    assert (
        "command run"
        not in str(model.data(model.index(0), Qt.ItemDataRole.AccessibleTextRole)).lower()
    )


def test_a_line_break_inside_an_argument_shows_on_one_row_but_copies_exactly() -> None:
    text = '"C:\\t.exe" "line one\nline two"'
    model = BuildLogModel()
    model.append(CommandRun("n", ("C:\\t.exe", "line one\nline two"), text))
    assert model.rowCount() == 1
    shown = str(model.data(model.index(0), LogRole.Text))
    assert "\n" not in shown and "\r" not in shown and "line two" in shown
    assert model.data(model.index(0), LogRole.Command) == text


def test_a_command_too_long_to_show_whole_is_not_copyable_and_says_where_it_is() -> None:
    model = BuildLogModel(max_line_chars=40)
    long = "C:\\t.exe " + "x" * 200
    model.append(CommandRun("n", ("C:\\t.exe", "x" * 200), long))
    row = model.index(0)
    shown = str(model.data(row, LogRole.Text))
    assert len(shown) <= 40 and shown.startswith("Ran: C:\\t.exe") and shown.endswith("…")
    assert model.data(row, LogRole.Truncated) is True
    assert model.data(row, LogRole.Command) is None
    assert "too long to copy from this list" in str(model.data(row, Qt.ItemDataRole.ToolTipRole))


def test_the_kept_command_counts_against_the_budget_and_leaves_with_its_row() -> None:
    model = BuildLogModel(max_rows=2)
    model.append(COMMAND)
    assert model.retained_chars == len(f"Ran: {TEXT}") + len(TEXT)
    model.append(LogLine("n", "one"))
    model.append(LogLine("n", "two"))
    assert [model.data(model.index(i), LogRole.Command) for i in range(2)] == [None, None]
    assert model.retained_chars == len("one") + len("two")


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_the_tooltip_names_the_command_line_form(
    monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    model = BuildLogModel()
    model.append(COMMAND)
    monkeypatch.setattr(sys, "platform", platform)
    tip = str(model.data(model.index(0), Qt.ItemDataRole.ToolTipRole))
    assert TEXT in tip and "Ctrl+Shift+C" in tip
    if platform == "win32":
        assert "PowerShell" in tip and "cmd.exe" in tip
    else:
        assert "shell" in tip and "PowerShell" not in tip


def test_keyboard_copy_command_copies_the_exact_text(
    panel: BuildLogPanel, clipboard: QApplication
) -> None:
    panel.append(LogLine("n", "before"))
    panel.append(COMMAND)
    select(panel, 1)
    action = copy_action(panel)
    assert action.text() == "Copy command"
    assert action.shortcut() == QKeySequence("Ctrl+Shift+C")
    assert action.isEnabled()
    QTest.keyClick(
        panel.view,
        Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert clipboard.clipboard().text() == TEXT


@pytest.mark.parametrize("event", LOOKALIKES, ids=["ran-prefix", "dollar", "command-node"])
def test_ordinary_output_cannot_enable_or_perform_a_copy(
    panel: BuildLogPanel, clipboard: QApplication, event: LogLine
) -> None:
    panel.append(event)
    select(panel, 0)
    action = copy_action(panel)
    assert not action.isEnabled()
    QTest.keyClick(
        panel.view,
        Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    action.trigger()
    assert clipboard.clipboard().text() == "untouched"


def test_native_line_copy_is_unchanged(panel: BuildLogPanel, clipboard: QApplication) -> None:
    panel.append(COMMAND)
    select(panel, 0)
    QTest.keyClick(panel.view, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert clipboard.clipboard().text() == f"[stage:kcl] Ran: {TEXT}"


def _menu_at(qtbot: QtBot, panel: BuildLogPanel, row: int) -> QMenu:
    settle()
    centre = panel.view.visualRect(panel.model.index(row)).center()
    panel.view.customContextMenuRequested.emit(QPoint(centre))
    menu = panel.findChild(QMenu, "build_log_menu")
    assert menu is not None, "right-click must open the log menu"
    qtbot.waitUntil(menu.isVisible)
    return menu


def test_context_menu_copies_the_command_under_the_pointer(
    qtbot: QtBot, panel: BuildLogPanel, clipboard: QApplication
) -> None:
    panel.append(LogLine("n", "$ not this"))
    panel.append(COMMAND)
    select(panel, 0)
    menu = _menu_at(qtbot, panel, 1)
    assert panel.view.currentIndex().row() == 1
    action = copy_action(panel)
    assert action in menu.actions() and action.isEnabled()
    menu.setActiveAction(action)
    QTest.keyClick(menu, Qt.Key.Key_Return)
    assert clipboard.clipboard().text() == TEXT
    assert not menu.isVisible()


def test_context_menu_on_ordinary_output_offers_a_disabled_copy(
    qtbot: QtBot, panel: BuildLogPanel, clipboard: QApplication
) -> None:
    panel.append(COMMAND)
    panel.append(LogLine("n", f"Ran: {TEXT}"))
    menu = _menu_at(qtbot, panel, 1)
    action = copy_action(panel)
    assert action in menu.actions() and not action.isEnabled()
    menu.close()
    assert clipboard.clipboard().text() == "untouched"


def test_clear_and_eviction_leave_no_stale_copy(qtbot: QtBot, clipboard: QApplication) -> None:
    panel = BuildLogPanel(model=BuildLogModel(max_rows=3))
    qtbot.addWidget(panel)
    panel.show()
    panel.toggle.click()
    panel.append(COMMAND)
    select(panel, 0)
    action = copy_action(panel)
    assert action.isEnabled()
    for number in range(3):
        panel.append(LogLine("n", f"line {number}"))
    settle()
    assert not action.isEnabled()
    action.trigger()
    assert clipboard.clipboard().text() == "untouched"
    panel.append(COMMAND)
    select(panel, 2)
    assert action.isEnabled()
    panel.clear()
    assert not action.isEnabled()
    action.trigger()
    assert clipboard.clipboard().text() == "untouched"


def test_evicting_rows_above_keeps_the_current_command_copyable(
    qtbot: QtBot, clipboard: QApplication
) -> None:
    panel = BuildLogPanel(model=BuildLogModel(max_rows=4))
    qtbot.addWidget(panel)
    panel.show()
    panel.toggle.click()
    panel.append(LogLine("n", "old"))
    panel.append(COMMAND)
    select(panel, 1)
    for number in range(3):
        panel.append(LogLine("n", f"line {number}"))
    settle()
    assert panel.view.currentIndex().data(LogRole.Command) == TEXT
    assert copy_action(panel).isEnabled()
    QTest.keyClick(panel.view, Qt.Key.Key_C, SHIFT_CTRL)
    assert clipboard.clipboard().text() == TEXT


def test_right_click_below_the_rows_offers_no_copy(
    qtbot: QtBot, panel: BuildLogPanel, clipboard: QApplication
) -> None:
    panel.append(COMMAND)
    select(panel, 0)
    settle()
    below = panel.view.viewport().rect().bottomLeft() + QPoint(4, -4)
    assert not panel.view.indexAt(below).isValid()
    panel.view.customContextMenuRequested.emit(below)
    menu = panel.findChild(QMenu, "build_log_menu")
    assert menu is not None
    qtbot.waitUntil(menu.isVisible)
    assert not copy_action(panel).isEnabled(), "nothing is under the pointer"
    copy_action(panel).trigger()
    menu.close()
    assert clipboard.clipboard().text() == "untouched"


def test_the_menu_never_copies_a_different_command_after_its_row_leaves(
    qtbot: QtBot, clipboard: QApplication
) -> None:
    panel = BuildLogPanel(model=BuildLogModel(max_rows=2))
    qtbot.addWidget(panel)
    panel.show()
    panel.toggle.click()
    other = CommandRun("n", ("C:\\other.exe",), '"C:\\other.exe"')
    panel.append(COMMAND)
    panel.append(other)
    menu = _menu_at(qtbot, panel, 0)
    panel.append(LogLine("n", "streaming output pushes the clicked command out"))
    settle()
    assert panel.view.currentIndex().data(LogRole.Command) == other.text
    assert not copy_action(panel).isEnabled(), "the clicked command has gone"
    copy_action(panel).trigger()
    menu.close()
    assert clipboard.clipboard().text() == "untouched"
    qtbot.waitUntil(lambda: not menu.isVisible())
    select(panel, 0)  # `other` is row 0 now; offscreen Qt does not refocus after a popup
    assert copy_action(panel).isEnabled(), "after the menu, the current row counts again"
    QTest.keyClick(panel.view, Qt.Key.Key_C, SHIFT_CTRL)
    assert clipboard.clipboard().text() == other.text


def test_a_command_over_the_character_budget_is_shown_unaltered_but_not_copyable() -> None:
    model = BuildLogModel(max_chars=60, max_line_chars=60)
    text = '"C:\\t.exe" ' + "y" * 30
    model.append(CommandRun("n", ("C:\\t.exe", "y" * 30), text))
    assert model.data(model.index(0), LogRole.Text) == f"Ran: {text}"
    assert model.data(model.index(0), LogRole.Truncated) is False
    assert model.data(model.index(0), LogRole.Command) is None
    tip = str(model.data(model.index(0), Qt.ItemDataRole.ToolTipRole))
    assert "too long to copy from this list" in tip and "disk" in tip
