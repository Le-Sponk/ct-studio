"""P5-T07f1: Settings → Editors… picks which built-in editor Open in… lists first.

Every test drives the real main window and the real settings file (synthetic contents).
"""

from __future__ import annotations

import threading

import pytest
from editor_request_helpers import settled
from editor_settings_helpers import (
    HeldPreferences,
    backups,
    choose,
    combo,
    editors_page,
    editors_window,
    saved,
    settings_file,
    texts,
    write_settings,
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel
from pytestqt.qtbot import QtBot

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import settings
from ctstudio.gui.editor_settings import KIND_LABELS, KINDS, EditorPreferencesService

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def test_each_kind_with_a_choice_of_editors_is_listed(qtbot: QtBot) -> None:
    held = HeldPreferences()
    with editors_window(qtbot, held) as (_window, page):
        assert KINDS == (".brres", ".szs", ".kmp")
        assert set(KIND_LABELS) == set(KINDS)
        assert list(page.combos) == list(KINDS)
        brres = combo(page, ".brres")
        assert texts(brres) == ["Default order (BrawlCrate first)", "BrawlCrate", "RiiStudio"]
        kmp = texts(combo(page, ".kmp"))
        assert kmp == [
            "Default order (Lorenzi's KMP Editor first)",
            "Lorenzi's KMP Editor",
            "KMP Cloud",
        ]
        form = page.findChild(QFormLayout, "editorsForm")
        assert form is not None, "the choices are not in a form"
        for kind in KINDS:
            box = combo(page, kind)
            assert box.currentIndex() == 0 and box.isEnabled(), f"{kind} not idle at default"
            label = form.labelForField(box)
            assert isinstance(label, QLabel) and label.text() == f"{KIND_LABELS[kind]}:"
            assert label.buddy() is box, f"{kind}: the label does not lead to its choice"
        assert not page.banner.isVisible() and not page.busy_bar.isVisible()
        assert held.threads, "nothing was read"
        assert all(t is not threading.main_thread() for t in held.threads), "read on UI thread"
        assert not settings_file().exists(), "opening the window wrote a settings file"


def test_a_choice_is_saved_with_a_backup_and_every_unknown_field(qtbot: QtBot) -> None:
    before = write_settings(
        {
            "format": 1,
            "tools": {"riistudio": "C:/Tools/RiiStudio é.exe"},
            "future_key": {"kept": [1, 2]},
            "editor_preferences": {".kmp": "kmp_cloud", "future_kind": {"x": 1}},
        }
    )
    held = HeldPreferences()
    with editors_window(qtbot, held) as (_window, page):
        assert combo(page, ".kmp").currentText() == "KMP Cloud", "the saved choice not shown"
        held.threads.clear()
        choose(qtbot, page, ".brres", "RiiStudio")
        assert held.threads and held.threads[0] is not threading.main_thread()
        data = saved()
        assert data["editor_preferences"] == {
            ".kmp": "kmp_cloud",
            "future_kind": {"x": 1},
            ".brres": "riistudio",
        }
        assert data["future_key"] == {"kept": [1, 2]}
        assert data["tools"] == {"riistudio": "C:/Tools/RiiStudio é.exe"}
        copies = backups()
        assert len(copies) == 1 and copies[0].read_bytes() == before, "no exact backup"
        assert page.note.text() == "Saved. Open in… now lists RiiStudio first for .brres files."
        assert not page.banner.isVisible()
        assert settings.load().editor_order(".brres") == ("riistudio", "brawlcrate")


def test_default_order_resets_the_choice(qtbot: QtBot) -> None:
    write_settings(
        {"format": 1, "editor_preferences": {".brres": "riistudio", ".szs": "riistudio"}}
    )
    with editors_window(qtbot) as (_window, page):
        assert combo(page, ".brres").currentText() == "RiiStudio"
        choose(qtbot, page, ".brres", "Default order (BrawlCrate first)")
        assert saved()["editor_preferences"] == {".szs": "riistudio"}
        assert settings.load().editor_order(".brres") == ("brawlcrate", "riistudio")
        assert page.note.text() == "Saved. Open in… now uses the default order for .brres files."
        assert combo(page, ".brres").currentIndex() == 0


def test_choosing_what_is_saved_already_writes_nothing(qtbot: QtBot) -> None:
    before = write_settings({"format": 1, "editor_preferences": {".kmp": "kmp_cloud"}})
    with editors_window(qtbot) as (_window, page):
        choose(qtbot, page, ".kmp", "KMP Cloud")
        choose(qtbot, page, ".szs", "Default order (BrawlCrate first)")
        assert settings_file().read_bytes() == before and not backups(), "a no-op was saved"


def test_reopening_reads_the_file_again(qtbot: QtBot) -> None:
    with editors_window(qtbot) as (window, page):
        dialog = window.editors_window.dialog
        assert dialog is not None and dialog.isVisible()
        assert dialog.windowModality() == Qt.WindowModality.WindowModal, "not window-modal"
        dialog.reject()
        write_settings({"format": 1, "editor_preferences": {".szs": "riistudio"}})
        window.editors_action.trigger()
        assert window.editors_window.dialog is dialog and editors_page(window) is page
        assert dialog.isVisible(), "the window did not open again"
        assert settled(qtbot, lambda: combo(page, ".szs").currentText() == "RiiStudio")
        assert not page.busy


def test_a_reopen_during_a_read_starts_no_second_read(qtbot: QtBot) -> None:
    held = HeldPreferences()
    held.gate.clear()
    with editors_window(qtbot, held, wait=False) as (window, page):
        assert settled(qtbot, lambda: held.loads == 1), "the first read never started"
        assert page.busy and page.busy_bar.isVisible()
        assert not any(box.isEnabled() for box in page.combos.values()), "editable while reading"
        window.editors_action.trigger()
        page.reload()
        held.gate.set()
        assert settled(qtbot, lambda: not page.busy), "the read never finished"
        assert held.loads == 1, f"{held.loads} reads for one open"
        assert all(box.isEnabled() for box in page.combos.values())
        assert not page.busy_bar.isVisible()


def test_choices_are_off_while_a_save_runs(qtbot: QtBot) -> None:
    held = HeldPreferences()
    with editors_window(qtbot, held) as (_window, page):
        held.gate = threading.Event()
        box = combo(page, ".kmp")
        box.setCurrentIndex(2)
        box.activated.emit(2)
        assert page.busy and page.busy_bar.isVisible()
        assert not any(b.isEnabled() for b in page.combos.values()), "editable while saving"
        other = combo(page, ".brres")
        other.activated.emit(2)  # a direct pick while saving must not start a second save
        held.gate.set()
        assert settled(qtbot, lambda: not page.busy), "the save never finished"
        assert held.saves == [(".kmp", "kmp_cloud")], f"saves asked for: {held.saves}"
        assert saved()["editor_preferences"] == {".kmp": "kmp_cloud"}, "the second pick saved"
        assert all(b.isEnabled() for b in page.combos.values())


@pytest.mark.parametrize(
    "damaged",
    [
        "{not json",
        '{"format": 99}',
        '{"format": 1, "editor_preferences": {".brres": "notepad"}}',
    ],
    ids=["not-json", "newer", "bad-choice"],
)
def test_a_damaged_settings_file_is_shown_and_never_overwritten(qtbot: QtBot, damaged: str) -> None:
    before = write_settings(damaged)
    held = HeldPreferences()
    with editors_window(qtbot, held) as (_window, page):
        assert page.banner.isVisible(), "the damaged file was not shown"
        assert "cannot be used" in page.banner.text()
        assert not any(box.isEnabled() for box in page.combos.values()), "editable on damage"
        combo(page, ".brres").activated.emit(2)  # past Qt's disabling: still no save
        assert settled(qtbot, lambda: not page.busy)
        assert held.saves == [], f"a save was tried on a damaged file: {held.saves}"
        assert settings_file().read_bytes() == before and not backups(), "overwritten"
        error = None
        try:
            EditorPreferencesService().save(".brres", "riistudio")
        except Exception as exc:  # the type is asserted below
            error = exc
        assert isinstance(error, settings.SettingsError), f"save gave {error!r}"
        assert settings_file().read_bytes() == before and not backups(), "service overwrote"


def test_a_file_damaged_after_it_was_shown_is_not_overwritten(qtbot: QtBot) -> None:
    with editors_window(qtbot) as (_window, page):
        before = write_settings("{damaged since shown")
        box = combo(page, ".brres")
        box.setCurrentIndex(2)
        box.activated.emit(2)
        assert settled(qtbot, lambda: not page.busy), "the save never finished"
        assert settings_file().read_bytes() == before and not backups(), "overwritten"
        assert "cannot be used" in page.banner.text(), page.banner.text()
        assert not any(b.isEnabled() for b in page.combos.values()), "editable on damage"
        assert box.currentIndex() == 0, "the refused choice is still shown"
        box.activated.emit(1)  # a forced pick while locked: the save reads the file and refuses
        assert settled(qtbot, lambda: not page.busy), "the forced save never finished"
        assert settings_file().read_bytes() == before and not backups(), "overwritten later"
        assert "cannot be used" in page.banner.text(), "the damage note went away"


def _no_backup(*_args: object, **_kwargs: object) -> None:
    raise ProjectError("Could not back up settings.json.", hint="Check free space.")


def _empty_error(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError


@pytest.mark.parametrize(
    ("save", "shown"),
    [(_no_backup, "Could not back up settings.json."), (_empty_error, "RuntimeError")],
    ids=["typed", "empty"],
)
def test_a_failed_save_is_explained_and_the_choice_goes_back(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, save: object, shown: str
) -> None:
    before = write_settings({"format": 1, "editor_preferences": {".brres": "riistudio"}})
    real_save = settings.save
    with editors_window(qtbot) as (_window, page):
        page.note.setText("an older note")
        monkeypatch.setattr(settings, "save", save)
        choose(qtbot, page, ".brres", "BrawlCrate")
        assert page.banner.isVisible() and shown in page.banner.text(), page.banner.text()
        assert page.note.text() == "", "an older note survived a failure"
        assert combo(page, ".brres").currentText() == "RiiStudio", "the choice did not go back"
        assert all(b.isEnabled() for b in page.combos.values()), "no retry after a failure"
        assert settings_file().read_bytes() == before
        # Not monkeypatch.undo(): that would also undo conftest's settings-path isolation.
        monkeypatch.setattr(settings, "save", real_save)
        choose(qtbot, page, ".brres", "BrawlCrate")
        assert not page.banner.isVisible(), "the old failure stayed after a good save"
        assert saved()["editor_preferences"] == {".brres": "brawlcrate"}


def _unreadable(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError


def test_a_failed_first_read_leaves_the_choices_off_until_a_good_read(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_load = settings.load
    monkeypatch.setattr(settings, "load", _unreadable)
    held = HeldPreferences()
    with editors_window(qtbot, held) as (window, page):
        shown = page.banner.text()
        assert page.banner.isVisible(), "the failed read was not shown"
        assert shown == "Could not read or save the editor choices: RuntimeError", shown
        assert not any(box.isEnabled() for box in page.combos.values()), "editable unread"
        combo(page, ".brres").activated.emit(2)  # past Qt's disabling: still no save
        assert settled(qtbot, lambda: not page.busy)
        assert held.saves == [], f"a save was tried before a good read: {held.saves}"
        assert not settings_file().exists(), "a pick was saved before anything was read"
        monkeypatch.setattr(settings, "load", real_load)
        window.editors_action.trigger()
        assert settled(qtbot, lambda: not page.busy), "the second read never finished"
        assert not page.banner.isVisible(), "the old failure stayed after a good read"
        assert all(box.isEnabled() for box in page.combos.values()), "still off"


def test_fixing_a_damaged_file_and_reopening_allows_choosing(qtbot: QtBot) -> None:
    write_settings("{damaged")
    with editors_window(qtbot) as (window, page):
        assert page.banner.isVisible()
        dialog = window.editors_window.dialog
        assert dialog is not None
        dialog.reject()
        write_settings({"format": 1, "kept": "yes"})
        window.editors_action.trigger()
        assert settled(qtbot, lambda: not page.busy), "the second read never finished"
        assert not page.banner.isVisible(), "the damage note stayed after the file was fixed"
        assert all(box.isEnabled() for box in page.combos.values()), "still locked"
        choose(qtbot, page, ".szs", "RiiStudio")
        assert saved() == {
            "format": 1,
            "kept": "yes",
            "editor_preferences": {".szs": "riistudio"},
            "tools": {},
        }
