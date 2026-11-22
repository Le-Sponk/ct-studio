"""P5-T07f3: Settings → Editors… → Wine (Linux): choose and clear a Wine-prefix folder for
each Windows editor, built-in or the user's own. Real main window and settings file;
synthetic folders only. The tab shows on every system and says it is used on Linux only."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from editor_request_helpers import settled
from editor_settings_helpers import (
    HeldPreferences,
    backups,
    editors_window,
    saved,
    settings_file,
    write_settings,
)
from PySide6.QtWidgets import QFileDialog, QLabel
from pytestqt.qtbot import QtBot
from wine_prefix_helpers import (
    built_in_rows,
    choose_folder,
    clear_prefix,
    folder_dialog,
    pick,
    row,
    select_wine,
    show_wine,
    wine_rows,
)

from ctstudio.core.project import settings
from ctstudio.core.tools.editors import PREFIX_RECIPES

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]

PAINT = {"name": "Paint é", "exe": "C:/Tools é/paint.EXE", "args_template": ["{file}"]}
NATIVE = {"name": "Native", "exe": "/usr/bin/native-paint", "args_template": ["{file}"]}


def _prefixes(data: dict[str, object]) -> dict[str, object]:
    table = data.get("wine_prefixes")
    assert isinstance(table, dict), f"no prefix table: {data!r}"
    return dict(table)  # pyright: ignore[reportUnknownArgumentType]


def test_the_tab_lists_windows_editors_and_explains_it_is_for_linux(
    qtbot: QtBot, tmp_path: Path
) -> None:
    prefix = tmp_path / "prefixes é" / "brawl"
    write_settings(
        {
            "format": 1,
            "custom_tools": {"custom-paint": PAINT, "custom-native": NATIVE},
            "wine_prefixes": {"brawlcrate": {"prefix": str(prefix)}},
        }
    )
    with editors_window(qtbot) as (_window, page):
        tab = page.tabs.indexOf(page.wine)
        assert tab >= 0 and page.tabs.tabText(tab) == "&Wine (Linux)"
        assert page.tabs.currentIndex() == 0, "the Wine tab is shown first"
        show_wine(page)
        expected = [*built_in_rows({"brawlcrate": prefix}), row("Paint é", None)]
        assert wine_rows(page) == expected, "only Windows editors get a prefix row"
        intro = page.wine.intro.text()
        assert "On Linux" in intro and "Windows does not use these folders" in intro, intro
        assert page.wine.rows.item(0).toolTip() == page.wine.rows.item(0).text()


def test_choose_clear_and_reopen_keep_backups_and_unknown_fields(
    qtbot: QtBot, tmp_path: Path
) -> None:
    brawl, riis = tmp_path / "wine é" / "brawl", tmp_path / "wine é" / "riis"
    write_settings(
        {
            "format": 1,
            "later_setting": {"kept": True},
            "custom_tools": {"custom-paint": PAINT},
            "wine_prefixes": {
                "riistudio": {"prefix": "/old/riis", "note": "kept"},
                "later-editor": {"prefix": "/somewhere", "extra": 1},
            },
        }
    )
    with editors_window(qtbot) as (window, page):
        show_wine(page)
        choose_folder(qtbot, page, "BrawlCrate", brawl)
        assert page.note.text() == f"Saved. On Linux, BrawlCrate now runs in the prefix {brawl}."
        assert len(backups()) == 1, "the first save made no backup"
        choose_folder(qtbot, page, "RiiStudio", riis)
        choose_folder(qtbot, page, "Paint é", riis)
        data = saved()
        table = _prefixes(data)
        assert table["brawlcrate"] == {"prefix": str(brawl)}
        assert table["riistudio"] == {"prefix": str(riis), "note": "kept"}, "record field lost"
        assert table["later-editor"] == {"prefix": "/somewhere", "extra": 1}
        assert table["custom-paint"] == {"prefix": str(riis)}
        assert data["later_setting"] == {"kept": True} and len(backups()) == 3
        clear_prefix(qtbot, page, "BrawlCrate")
        assert page.note.text() == "Cleared the Wine prefix of BrawlCrate."
        assert "brawlcrate" not in _prefixes(saved()) and len(backups()) == 4
        dialog = window.editors_window.dialog
        assert dialog is not None
        dialog.reject()
        write_settings(
            {**saved(), "wine_prefixes": {**_prefixes(saved()), "kmp_cloud": {"prefix": "/k"}}}
        )
        window.editors_action.trigger()
        assert settled(qtbot, lambda: not page.busy), "the reread never ended"
        expected = built_in_rows({"riistudio": riis, "kmp_cloud": Path("/k")})
        assert wine_rows(page) == [*expected, row("Paint é", riis)], "reopen shows old rows"


def test_an_unchanged_choice_writes_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    folder = tmp_path / "same"
    before = write_settings({"format": 1, "wine_prefixes": {"brawlcrate": {"prefix": str(folder)}}})
    with editors_window(qtbot) as (_window, page):
        show_wine(page)
        choose_folder(qtbot, page, "BrawlCrate", folder)
        assert settings_file().read_bytes() == before and backups() == [], "rewrote the file"
        assert page.note.text().startswith("Saved."), "no note for an unchanged choice"


def test_clear_is_off_without_a_prefix_and_the_how_to_follows_the_row(
    qtbot: QtBot, tmp_path: Path
) -> None:
    write_settings(
        {
            "format": 1,
            "custom_tools": {"custom-paint": PAINT},
            "wine_prefixes": {"riistudio": {"prefix": str(tmp_path)}},
        }
    )
    with editors_window(qtbot) as (_window, page):
        show_wine(page)
        assert page.wine.selected() is None and not page.wine.choose_button.isEnabled()
        assert not page.wine.clear_button.isEnabled() and page.wine.how.text() == ""
        select_wine(page, "BrawlCrate")
        assert page.wine.choose_button.isEnabled() and not page.wine.clear_button.isEnabled()
        assert page.wine.how.text() == f"To make one: {PREFIX_RECIPES['brawlcrate']}"
        select_wine(page, "RiiStudio")
        assert page.wine.clear_button.isEnabled(), "Clear is off for a chosen prefix"
        assert PREFIX_RECIPES["riistudio"] in page.wine.how.text()
        select_wine(page, "Paint é")
        assert page.wine.how.text() == "To make one: WINEPREFIX=<folder> wineboot -u"
        page.wine.rows.currentItem().setSelected(False)
        assert page.wine.selected() is None and not page.wine.choose_button.isEnabled()
        assert page.wine.how.text() == "", "the how-to of an unselected editor stays"


def test_the_folder_dialog_starts_at_the_chosen_prefix_and_cancel_saves_nothing(
    qtbot: QtBot, tmp_path: Path
) -> None:
    before = write_settings(
        {"format": 1, "wine_prefixes": {"riistudio": {"prefix": str(tmp_path)}}}
    )
    service = HeldPreferences()
    with editors_window(qtbot, service) as (_window, page):
        show_wine(page)
        select_wine(page, "RiiStudio")
        page.wine.choose_button.click()
        dialog = folder_dialog(qtbot, page)
        assert Path(dialog.directory().absolutePath()) == tmp_path, "starts elsewhere"
        assert dialog.fileMode() == QFileDialog.FileMode.Directory, "it picks files"
        assert dialog.windowTitle() == "Choose the Wine prefix folder for RiiStudio"
        dialog.reject()
        assert settled(qtbot, lambda: page.wine.folder_dialog is None), "dialog kept"
        assert service.prefixes == [] and settings_file().read_bytes() == before


def test_a_damaged_file_hides_the_tabs_and_saves_nothing(qtbot: QtBot) -> None:
    before = write_settings("{damaged")
    service = HeldPreferences()
    with editors_window(qtbot, service) as (_window, page):
        assert page.banner.isVisible() and not page.tabs.isVisible(), "tabs show"
        assert not page.wine.rows.isEnabled() and not page.wine.choose_button.isEnabled()
        page.wine.chosen.emit("brawlcrate", Path("/x"))  # past Qt's own hiding
        assert settled(qtbot, lambda: not page.busy)
        assert settings_file().read_bytes() == before, "a damaged file was written"
        assert page.banner.isVisible(), "the save hid the damaged-file banner"


def test_a_file_damaged_after_it_was_shown_is_not_overwritten(qtbot: QtBot, tmp_path: Path) -> None:
    write_settings({"format": 1})
    with editors_window(qtbot) as (_window, page):
        show_wine(page)
        before = write_settings("{damaged after the window read it")
        choose_folder(qtbot, page, "BrawlCrate", tmp_path)
        assert settings_file().read_bytes() == before and backups() == [], "it was written"
        assert page.banner.isVisible() and "settings.json" in page.banner.text()
        assert not page.tabs.isVisible(), "the tabs still show on a damaged file"


def test_a_failed_save_is_shown_and_the_rows_stay_saved(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_settings({"format": 1})

    def broken(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    with editors_window(qtbot) as (_window, page):
        show_wine(page)
        monkeypatch.setattr(settings, "save", broken)
        choose_folder(qtbot, page, "BrawlCrate", tmp_path)
        assert page.banner.text() == "Could not read or save the editor settings: disk full"
        assert wine_rows(page) == built_in_rows(), "the row shows an unsaved prefix"


def test_while_saving_everything_is_off_and_nothing_else_is_saved(
    qtbot: QtBot, tmp_path: Path
) -> None:
    write_settings({"format": 1})
    service = HeldPreferences()
    with editors_window(qtbot, service) as (_window, page):
        show_wine(page)
        service.gate = threading.Event()
        select_wine(page, "BrawlCrate")
        page.wine.choose_button.click()
        pick(folder_dialog(qtbot, page), tmp_path)
        assert settled(qtbot, lambda: len(service.prefixes) == 1), "no save started"
        assert page.busy and page.busy_bar.isVisible()
        wine = page.wine
        assert not any(c.isEnabled() for c in (wine.rows, wine.choose_button, wine.clear_button))
        wine.chosen.emit("kmp_cloud", tmp_path)  # past Qt's own disabling
        service.gate.set()
        assert settled(qtbot, lambda: not page.busy), "the save never ended"
        assert service.prefixes == [("brawlcrate", tmp_path)], "a busy pick was saved"
        assert all(t is not threading.main_thread() for t in service.threads), "UI thread"
        assert page.wine.selected() == "brawlcrate", "the row lost its selection"


def test_an_editor_removed_outside_gets_no_prefix(qtbot: QtBot, tmp_path: Path) -> None:
    write_settings({"format": 1, "custom_tools": {"custom-paint": PAINT}})
    with editors_window(qtbot) as (_window, page):
        show_wine(page)
        select_wine(page, "Paint é")
        write_settings({"format": 1})
        choose_folder(qtbot, page, "Paint é", tmp_path)
        assert "Paint é was removed outside this window" in page.banner.text()
        assert "wine_prefixes" not in saved(), "a prefix was saved for a removed editor"
        assert wine_rows(page) == [*built_in_rows(), row("Paint é", None)], "rows changed"


def test_a_removed_editor_s_prefix_can_still_be_cleared(qtbot: QtBot, tmp_path: Path) -> None:
    """Clearing never needs the editor: an editor removed outside loses its old prefix."""
    write_settings(
        {
            "format": 1,
            "custom_tools": {"custom-paint": PAINT},
            "wine_prefixes": {"custom-paint": {"prefix": str(tmp_path)}},
        }
    )
    with editors_window(qtbot) as (_window, page):
        show_wine(page)
        write_settings({"format": 1, "wine_prefixes": {"custom-paint": {"prefix": str(tmp_path)}}})
        clear_prefix(qtbot, page, "Paint é")
        assert not page.banner.isVisible(), page.banner.text()
        assert _prefixes(saved()) == {}, "the old prefix was kept"
        assert page.note.text() == "Cleared the Wine prefix of Paint é."


def test_the_tab_text_names_the_windows_editors_only(qtbot: QtBot) -> None:
    """Pins the words: the heading is the list's buddy and the buttons say what they do."""
    write_settings({"format": 1})
    with editors_window(qtbot) as (_window, page):
        show_wine(page)
        buddies = [
            label for label in page.wine.findChildren(QLabel) if label.buddy() is page.wine.rows
        ]
        assert buddies == [page.wine.intro] and "Windows e&ditors" in page.wine.intro.text()
        assert page.wine.choose_button.text() == "Choose &folder…"
        assert page.wine.clear_button.text() == "C&lear"
        assert (
            not page.wine.choose_button.autoDefault() and not page.wine.clear_button.autoDefault()
        )
        assert json.loads(settings_file().read_text(encoding="utf-8")) == {"format": 1}
