"""The offscreen font loader, moved out of MainWindow (Deep Clean #1 step e)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ctstudio.gui import app, offscreen_font
from ctstudio.gui.offscreen_font import ensure_offscreen_font

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


class Fonts:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.families: list[str] = []
        self.added: list[str] = []
        self.font_id = 7
        self.file = tmp_path / "probe.ttf"
        self.file.write_bytes(b"not read: addApplicationFont is replaced")
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        monkeypatch.setattr(offscreen_font, "font_file", lambda: self.file)
        monkeypatch.setattr(QFontDatabase, "families", self._families)
        monkeypatch.setattr(QFontDatabase, "addApplicationFont", self._add)
        monkeypatch.setattr(QFontDatabase, "applicationFontFamilies", self._loaded)

    def _families(self, *_args: object) -> list[str]:
        return list(self.families)

    @staticmethod
    def _loaded(_font_id: int) -> list[str]:
        return ["Probe Sans"]

    def _add(self, path: str) -> int:
        self.added.append(path)
        return self.font_id


@pytest.fixture
def fonts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, qtbot: QtBot) -> Iterator[Fonts]:
    del qtbot  # the QApplication exists
    qt = QApplication.instance()
    assert isinstance(qt, QApplication)
    before = QFont(qt.font())
    yield Fonts(monkeypatch, tmp_path)
    qt.setFont(before)


def _family() -> str:
    qt = QApplication.instance()
    assert isinstance(qt, QApplication)
    return qt.font().family()


def test_an_offscreen_app_without_fonts_gets_the_bundled_one(fonts: Fonts) -> None:
    ensure_offscreen_font()
    assert fonts.added == [str(fonts.file)]
    assert _family() == "Probe Sans"


@pytest.mark.parametrize("platform", ["windows", "xcb", ""])
def test_a_real_display_is_left_alone(
    fonts: Fonts, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", platform)
    ensure_offscreen_font()
    assert fonts.added == [] and _family() != "Probe Sans"


def test_fonts_qt_found_itself_are_kept(fonts: Fonts) -> None:
    fonts.families = ["Some Sans"]
    ensure_offscreen_font()
    assert fonts.added == [] and _family() != "Probe Sans"


def test_a_missing_font_file_changes_nothing(fonts: Fonts) -> None:
    fonts.file.unlink()
    ensure_offscreen_font()
    assert fonts.added == [] and _family() != "Probe Sans"


def test_a_font_qt_refuses_changes_nothing(fonts: Fonts) -> None:
    fonts.font_id = -1
    ensure_offscreen_font()
    assert fonts.added == [str(fonts.file)] and _family() != "Probe Sans"


def test_each_system_has_its_font(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(offscreen_font.sys, "platform", "win32")
    monkeypatch.setenv("WINDIR", "D:/Win")
    assert offscreen_font.font_file() == Path("D:/Win/Fonts/segoeui.ttf")
    monkeypatch.setattr(offscreen_font.sys, "platform", "linux")
    assert offscreen_font.font_file() == Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def test_the_smoke_run_loads_it_before_the_window_is_made(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    order: list[str] = []
    real_window = app.MainWindow

    def window() -> object:
        order.append("window")
        return real_window()

    def running(_argv: list[str]) -> object:
        return QApplication.instance()

    monkeypatch.setattr(app, "QApplication", running)
    monkeypatch.setattr(app, "ensure_offscreen_font", lambda: order.append("font"))
    monkeypatch.setattr(app, "MainWindow", window)
    assert app.run_gui(tmp_path / "frame.png") == 0
    assert order == ["font", "window"]
