"""Outside-edit banner contract before dashboard integration (P5-T06c2a)."""

from __future__ import annotations

# Direct slot injection tests the app gates that Qt's disabled-button dispatch would hide.
# pyright: reportPrivateUsage=false
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from pytestqt.qtbot import QtBot

from ctstudio.gui.views.outside_edit_banner import OutsideEditBanner, confirm_discard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize("edited", [False, True])
@pytest.mark.parametrize("eligible", [False, True])
def test_only_an_eligible_edited_part_emits_a_lock_request(
    qtbot: QtBot, edited: bool, eligible: bool
) -> None:
    banner = OutsideEditBanner()
    qtbot.addWidget(banner)
    assert banner.isHidden()
    banner.set_state(edited=edited, eligible=eligible)
    assert banner.isHidden() is not edited
    assert banner.lock_button.isEnabled() is (edited and eligible)
    assert banner.discard_button.isEnabled() is (edited and eligible)
    done = QSignalSpy(banner.requested)
    banner.lock_button.click()
    assert done.count() == int(edited and eligible)
    if done.count():
        assert done.at(0) == ["lock"]
    assert "outside CT Studio" in banner.title.text()
    assert banner.lock_button.accessibleName() and banner.lock_button.toolTip()
    assert banner.discard_button.accessibleName() and banner.discard_button.toolTip()


@pytest.mark.parametrize("accepted", [False, True])
@pytest.mark.parametrize("change", ["none", "disable", "rebind", "work"])
def test_discard_requires_a_fresh_confirmation(qtbot: QtBot, accepted: bool, change: str) -> None:
    banner = OutsideEditBanner()
    qtbot.addWidget(banner)
    banner.set_state(edited=True, eligible=True)
    asked: list[QWidget] = []

    def confirm(parent: QWidget) -> bool:
        asked.append(parent)
        if change == "disable":
            banner.set_state(edited=True, eligible=False)
        elif change == "work":
            banner.show_work("lock")
            banner.show_work(None)
        elif change == "rebind":
            banner.set_state(edited=False, eligible=False)
            banner.set_state(edited=True, eligible=True)
        return accepted

    banner.confirm = confirm
    done = QSignalSpy(banner.requested)
    banner.discard_button.click()
    assert asked == [banner]
    assert done.count() == int(accepted and change == "none")
    if done.count():
        assert done.at(0) == ["discard"]


@pytest.mark.parametrize("action", ["lock", "discard"])
def test_working_result_and_reset_do_not_leak_state(qtbot: QtBot, action: str) -> None:
    banner = OutsideEditBanner()
    qtbot.addWidget(banner)
    banner.set_state(edited=True, eligible=True)
    banner.show_note("Old result", "Old path")
    banner.show_work(action)
    assert not banner.lock_button.isEnabled() and not banner.discard_button.isEnabled()
    assert not banner.progress.isHidden() and banner.progress.maximum() == 0
    assert banner.activity.text() and banner.activity.toolTip() == banner.activity.text()
    assert banner.activity.accessibleDescription() == banner.activity.text()
    assert (
        banner.progress.toolTip()
        == banner.progress.accessibleDescription()
        == banner.activity.text()
    )
    assert not banner.note.text() and not banner.note.toolTip()
    banner.set_state(edited=False, eligible=False)  # a status refresh must not hide active work
    assert not banner.isHidden()
    banner.show_note("Kept <outside> edit", "D:/Pistë 日本/full path")
    banner.show_work(None)
    banner.set_state(
        edited=False, eligible=False
    )  # routine checks must not erase this producer's outcome
    assert not banner.isHidden() and not banner.note.isHidden()
    assert banner.note.textFormat() == Qt.TextFormat.PlainText
    assert banner.note.toolTip() == banner.note.accessibleDescription()
    assert "D:/Pistë 日本/full path" in banner.note.toolTip()
    assert not banner.activity.text() and not banner.activity.toolTip()
    assert not banner.activity.accessibleDescription() and banner.progress.isHidden()
    assert not banner.progress.toolTip() and not banner.progress.accessibleDescription()
    banner.clear()
    assert banner.isHidden() and not banner.note.text() and not banner.note.toolTip()
    assert not banner.note.accessibleDescription()
    banner.set_state(edited=True, eligible=True)
    assert banner.lock_button.isEnabled() and banner.discard_button.isEnabled()
    assert not banner.note.text() and banner.progress.isHidden()


def test_modal_approval_cannot_dispatch_another_request(qtbot: QtBot) -> None:
    banner = OutsideEditBanner()
    qtbot.addWidget(banner)
    banner.set_state(edited=True, eligible=True)
    inside: list[bool] = []

    def confirm(_parent: QWidget) -> bool:
        inside.append(banner.lock_button.isEnabled() or banner.discard_button.isEnabled())
        banner.lock_button.click()
        banner._request("lock")  # also refuse queued/programmatic activation during the modal loop
        return True

    banner.confirm = confirm
    done = QSignalSpy(banner.requested)
    banner.discard_button.click()
    assert inside == [False], "the pending confirmation must gate both actions"
    assert done.count() == 1 and done.at(0) == ["discard"]
    assert banner.lock_button.isEnabled() and banner.discard_button.isEnabled()


@pytest.mark.parametrize(
    "edited,eligible", [(False, False), (False, True), (True, False), (True, True)]
)
@pytest.mark.parametrize("work", [None, "lock", "discard"])
@pytest.mark.parametrize("action", ["lock", "discard"])
def test_slot_guard_is_not_only_button_disable(
    qtbot: QtBot,
    edited: bool,
    eligible: bool,
    work: str | None,
    action: str,
) -> None:
    banner = OutsideEditBanner()
    qtbot.addWidget(banner)
    banner.set_state(edited=edited, eligible=eligible)
    banner.show_work(work)
    asked: list[QWidget] = []

    def confirm(parent: QWidget) -> bool:
        asked.append(parent)
        return True

    banner.confirm = confirm
    done = QSignalSpy(banner.requested)
    banner._request(action)  # direct slot injection must still obey all eligibility gates
    allowed = edited and eligible and work is None
    assert done.count() == int(allowed)
    assert bool(asked) is (allowed and action == "discard")
    if allowed:
        assert done.at(0) == [action]


@pytest.mark.parametrize("choice", ["enter", "escape", "discard", "close"])
def test_real_confirmation_defaults_to_cancel_and_cleans_up(qtbot: QtBot, choice: str) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    observed: list[tuple[bool, bool, bool]] = []

    def answer() -> None:
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, QMessageBox):
            return
        cancel = next(
            b for b in dialog.buttons() if dialog.buttonRole(b) == QMessageBox.ButtonRole.RejectRole
        )
        discard = next(
            b
            for b in dialog.buttons()
            if dialog.buttonRole(b) == QMessageBox.ButtonRole.DestructiveRole
        )
        observed.append(
            (
                dialog.defaultButton() is cancel,
                dialog.escapeButton() is cancel,
                "backup" in dialog.text() and "next build" in dialog.text(),
            )
        )
        if choice == "discard":
            discard.click()
        elif choice == "close":
            dialog.close()
        else:
            QTest.keyClick(dialog, Qt.Key.Key_Return if choice == "enter" else Qt.Key.Key_Escape)

    QTimer.singleShot(0, answer)
    assert confirm_discard(parent) is (choice == "discard")
    assert observed == [(True, True, True)]
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not parent.findChildren(QMessageBox)


def test_native_confirmation_error_still_cleans_up(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    def fail_exec(_dialog: QMessageBox) -> int:
        raise RuntimeError("native dialog interrupted")

    monkeypatch.setattr(QMessageBox, "exec", fail_exec)
    error: Exception | None = None
    try:
        confirm_discard(parent)
    except Exception as exc:
        error = exc  # retaining its traceback must not retain a live child dialog
    assert isinstance(error, RuntimeError)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not parent.findChildren(QMessageBox), "failed modal execution must release the prompt"


def test_ancestor_enable_recovery_and_keyboard_scroll_path(qtbot: QtBot) -> None:
    area, content = QScrollArea(), QWidget()
    qtbot.addWidget(area)
    layout = QVBoxLayout(content)
    first = QPushButton("Before banner", content)
    banner = OutsideEditBanner(content)
    layout.addWidget(first)
    layout.addSpacing(800)
    layout.addWidget(banner)
    area.setWidget(content)
    area.setWidgetResizable(True)
    area.resize(360, 280)
    content.setEnabled(False)
    banner.set_state(edited=True, eligible=True)
    content.setEnabled(True)
    assert banner.lock_button.isEnabled() and banner.discard_button.isEnabled()
    area.show()
    area.activateWindow()
    QApplication.processEvents()
    first.setFocus()
    QTest.keyClick(first, Qt.Key.Key_Tab)
    assert banner.lock_button.hasFocus() and area.verticalScrollBar().value() > 0
    done = QSignalSpy(banner.requested)
    QTest.keyClick(banner.lock_button, Qt.Key.Key_Space)
    QTest.keyClick(banner.lock_button, Qt.Key.Key_Tab)
    assert banner.discard_button.hasFocus()

    def approve(_parent: QWidget) -> bool:
        return True

    banner.confirm = approve
    QTest.keyClick(banner.discard_button, Qt.Key.Key_Space)
    assert [done.at(i) for i in range(done.count())] == [["lock"], ["discard"]]
