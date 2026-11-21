"""P5-T07f1 local evidence: Settings → Editors… light/dark, normal/enlarged, idle and damaged.

Pictures stay in tests/artifacts/screens (git-ignored, never uploaded). Fonts and palettes
are installed-font proxies (see outside_visual_helpers); native Linux pixels are not shown.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest
from editor_settings_helpers import combo, editors_window, write_settings
from outside_visual_helpers import visual_style
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLabel, QWidget
from pytestqt.qtbot import QtBot
from wizard_fakes import SCREENS, shot

from ctstudio.core.project import settings
from ctstudio.core.project.settings import SettingsError
from ctstudio.gui.editor_settings import KINDS
from ctstudio.gui.views.editors_page import EditorsPage

LONG_EXE = "C:/Program Files/Some Vendor/Paint Studio/bin/x64/paint-studio.exe"

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
CASES = [
    (dark, enlarged, damaged)
    for dark in (False, True)
    for enlarged in (False, True)
    for damaged in (False, True)
]


def inside(child: QWidget, parent: QWidget) -> bool:
    top_left = child.mapTo(parent, child.rect().topLeft())
    return parent.rect().contains(QRect(top_left, child.size()))


def assert_label_fits(label: QLabel, dialog: QDialog) -> None:
    assert inside(label, dialog), f"{label.text()!r} is cut off"
    if label.wordWrap():
        needed = label.heightForWidth(label.width())
        assert needed > 0 and label.height() >= needed, f"{label.text()!r} cut short"
    else:
        assert label.width() >= label.sizeHint().width(), f"{label.text()!r} is clipped"


def assert_readable(dialog: QDialog) -> None:
    """Every shown label and choice fits the window at full width; wrapped text fits; the
    choices line up under their labels."""
    boxes = [box for box in dialog.findChildren(QComboBox) if box.isVisible()]
    if boxes:  # hidden while the settings file cannot be used
        assert_choices_fit(boxes, dialog)
    for label in dialog.findChildren(QLabel):
        if label.isVisible() and label.text():
            assert_label_fits(label, dialog)
    assert dialog.width() <= dialog.screen().availableGeometry().width()


def assert_choices_fit(boxes: list[QComboBox], dialog: QDialog) -> None:
    for box in boxes:
        assert inside(box, dialog), f"{box.currentText()!r} is cut off"
        assert box.width() >= box.minimumSizeHint().width(), f"{box.currentText()!r} clipped"
    lines = {(box.mapTo(dialog, box.rect().topLeft()).x(), box.width()) for box in boxes}
    assert len(boxes) == len(KINDS) and len(lines) == 1, f"the choices do not line up: {lines}"


def assert_usable(page: EditorsPage) -> None:
    """A healthy file: the saved choice shows, the long own-editor row is shortened in the
    middle with the full text on hover, and every control is on."""
    assert combo(page, ".kmp").currentText() == "KMP Cloud"
    page.own.setCurrentRow(0)
    row = page.own.item(0)
    assert row.toolTip() == row.text() and LONG_EXE.split("/")[-1] in row.text()
    assert not page.own.horizontalScrollBar().isVisible(), "rows scroll sideways"
    middle = Qt.TextElideMode.ElideMiddle
    assert page.own.textElideMode() == middle, "long rows are cut at the edge"
    assert all(combo(page, kind).isEnabled() for kind in KINDS)
    controls = (page.own, page.add_button, page.edit_button, page.remove_button)
    assert all(control.isEnabled() for control in controls), "a control is off"


def assert_locked(page: EditorsPage) -> None:
    """A damaged file: the choices and own editors are off and hidden (the banner keeps the
    room)."""
    assert not any(combo(page, kind).isEnabled() for kind in KINDS)
    assert not any(combo(page, kind).isVisible() for kind in KINDS), "choices show"
    assert not page.own.isEnabled() and not page.add_button.isEnabled()
    assert not page.own.isVisible(), "the own editors show on a damaged file"


@pytest.mark.parametrize(
    ("dark", "enlarged", "damaged"),
    CASES,
    ids=[
        f"{'dark' if d else 'light'}{'-big' if e else ''}{'-damaged' if x else ''}"
        for d, e, x in CASES
    ],
)
def test_editors_window_pictures(qtbot: QtBot, dark: bool, enlarged: bool, damaged: bool) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    if damaged:
        write_settings("{damaged")
    else:
        own = {"name": "My long-named paint program", "exe": LONG_EXE, "args_template": ["{file}"]}
        write_settings(
            {
                "format": 1,
                "editor_preferences": {".kmp": "kmp_cloud"},
                "custom_tools": {"custom-paint": own},
            }
        )
    name = (
        f"p5-t07f1-{'dark' if dark else 'light'}{'-big' if enlarged else ''}"
        f"{'-damaged' if damaged else ''}"
    )
    with visual_style(app, dark, enlarged), editors_window(qtbot) as (window, page):
        window.resize(window.minimumSize())
        dialog = window.editors_window.dialog
        assert dialog is not None
        QApplication.processEvents()  # the window sizes itself; no adjustSize() here
        assert page.banner.isVisible() == damaged
        if damaged:
            assert_locked(page)
        else:
            assert_usable(page)
        assert_readable(dialog)
        shot(dialog, f"{name}.png")
    assert (SCREENS / f"{name}.png").stat().st_size > 0


def test_a_long_settings_path_wraps_inside_the_screen(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The damaged-file banner names the file; a long path without spaces must still wrap."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    deep = (
        tmp_path
        / "a_long_folder_name_without_any_spaces_0123456789"
        / "and_another_one_like_it_abcdefghij"
    )
    monkeypatch.setattr(settings, "default_path", lambda: deep / "settings.json")
    write_settings("{damaged")
    assert len(str(deep)) > 120, "the path is not long enough to test wrapping"
    with visual_style(app, False, True), editors_window(qtbot) as (window, page):
        dialog = window.editors_window.dialog
        assert dialog is not None
        QApplication.processEvents()
        assert page.banner.isVisible()
        assert "settings.json" in page.banner.text()
        assert_readable(dialog)


class _LinuxPathError(SettingsError):
    """A damaged-file error that names a Linux path, whichever system runs the test."""

    def __init__(self, path: PurePosixPath) -> None:
        super().__init__(Path(), "it is not valid JSON")
        self.shown = f"CT Studio's settings file {path} cannot be used: it is not valid JSON."

    def __str__(self) -> str:
        return self.shown


def test_a_long_linux_style_path_wraps_inside_the_screen(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linux paths use "/": the banner must wrap at those too, on any test machine."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    deep = PurePosixPath("/home/a_long_user_name_without_spaces_0123456789/.config")
    deep = deep / "ct-studio_settings_folder_also_without_spaces_abcdefghij" / "settings.json"

    def damaged(*_args: object, **_kwargs: object) -> None:
        raise _LinuxPathError(deep)

    monkeypatch.setattr(settings, "load", damaged)
    with visual_style(app, False, True), editors_window(qtbot) as (window, page):
        dialog = window.editors_window.dialog
        assert dialog is not None
        QApplication.processEvents()
        assert page.banner.isVisible() and "settings.json" in page.banner.text()
        assert "\\" not in page.banner.text(), "the test path is not Linux-style"
        assert_readable(dialog)
