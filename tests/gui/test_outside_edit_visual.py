"""Local-only banner evidence; full mounted card/dashboard acceptance remains c2b."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from pytestqt.qtbot import QtBot

from ctstudio.gui.views.outside_edit_banner import OutsideEditBanner

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.fixture
def visual_family() -> Iterator[str]:
    handle = -1
    families = QFontDatabase.families()
    if not families:
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf"
        assert font_path.is_file(), "offscreen visual proof needs an installed readable font"
        handle = QFontDatabase.addApplicationFont(str(font_path))
        assert handle >= 0
        families = QFontDatabase.applicationFontFamilies(handle)
    family = "DejaVu Sans" if "DejaVu Sans" in families else families[0]
    try:
        yield family
    finally:
        if handle >= 0:
            QFontDatabase.removeApplicationFont(handle)


def _font(family: str, scale: float) -> QFont:
    font = QFont(family, int(12 * scale))
    font.setStretch(120)
    metrics = QFontMetrics(font)
    assert metrics.inFontUcs4(ord("A"))
    assert metrics.horizontalAdvance("WWW") > metrics.horizontalAdvance("iii")
    return font


def _canvas(family: str, dark: bool, scale: float) -> tuple[QWidget, list[OutsideEditBanner], str]:
    host = QWidget()
    host.setFont(_font(family, scale))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#202126" if dark else "#fafafa"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee" if dark else "#202124"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#383a42" if dark else "#eeeeee"))
    palette.setColor(QPalette.ColorRole.ButtonText, palette.color(QPalette.ColorRole.WindowText))
    palette.setColor(QPalette.ColorRole.Base, palette.color(QPalette.ColorRole.Window))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.PlaceholderText):
        palette.setColor(role, palette.color(QPalette.ColorRole.WindowText))
    host.setPalette(palette)
    host.setAutoFillBackground(True)
    grid = QGridLayout(host)
    banners: list[OutsideEditBanner] = []
    path = "D:/Pistë 日本/" + "very-long-output-folder/" * 16
    states = ("Edited", "Unavailable", "Locking", "Backing up", "Kept result", "Failure")
    for index, state in enumerate(states):
        frame = QGroupBox(state, host)
        frame.setFixedWidth(310)
        layout = QVBoxLayout(frame)
        banner = OutsideEditBanner(frame)
        layout.addWidget(banner)
        grid.addWidget(frame, index // 2, index % 2)
        banner.set_state(edited=index != 4, eligible=index != 1)
        if index in (2, 3):
            banner.show_work("lock" if index == 2 else "discard")
        elif index == 4:
            banner.show_note("Kept <outside> edit for Pistë", path)
        elif index == 5:
            banner.show_note(
                "Could not keep <outside> edit: " + "the files folder could not be written. " * 8,
                path,
            )
        banners.append(banner)
    return host, banners, path


def _labels_fit(banner: OutsideEditBanner) -> None:
    for label in (banner.title, banner.activity, banner.note):
        if label.isVisible():
            wanted = min(label.maximumHeight(), label.heightForWidth(label.width()))
            assert label.height() <= wanted + 2, "short notices must not stretch into blank bands"
    assert banner.title.hasHeightForWidth(), "word wrapping must retain Qt height-for-width"
    if banner.title.isVisible():
        bounds = banner.title.fontMetrics().boundingRect(
            QRect(0, 0, banner.title.width(), 10000),
            Qt.TextFlag.TextWordWrap,
            banner.title.text(),
        )
        assert bounds.height() <= banner.title.height() + 2, "banner title must not clip"
    assert banner.note.height() <= banner.note.fontMetrics().lineSpacing() * 4, (
        "outcome must stay bounded"
    )


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("scale", [1.0, 1.5])
def test_banner_palette_font_and_bounded_notes(
    qtbot: QtBot,
    visual_family: str,
    dark: bool,
    scale: float,
) -> None:
    host, banners, path = _canvas(visual_family, dark, scale)
    qtbot.addWidget(host)
    host.adjustSize()
    layout = host.layout()
    assert layout is not None
    # A six-state contact sheet must not inherit adjustSize()'s 2/3-screen height cap.
    host.resize(host.width(), layout.totalHeightForWidth(host.width()))
    host.show()
    QApplication.processEvents()
    for banner in banners:
        visible = [
            banner.title,
            banner.lock_button,
            banner.discard_button,
            banner.activity,
            banner.progress,
            banner.note,
        ]
        visible = [widget for widget in visible if widget.isVisible()]
        for index, widget in enumerate(visible):
            assert banner.rect().contains(widget.geometry())
            assert all(
                not widget.geometry().intersects(other.geometry()) for other in visible[index + 1 :]
            )
        for button in (banner.lock_button, banner.discard_button):
            if button.isVisible():
                assert button.width() >= button.sizeHint().width()
        banner_layout = banner.layout()
        assert banner_layout is not None
        assert visible[0].y() == banner_layout.contentsMargins().top(), (
            "compact content must stay at the top"
        )
        _labels_fit(banner)
    for banner in banners[4:]:
        assert (
            path in banner.note.toolTip()
            and banner.note.toolTip() == banner.note.accessibleDescription()
        )
    assert banners[5].note.textFormat() == Qt.TextFormat.PlainText
    root = Path(__file__).resolve().parents[2] / "tests/artifacts/screenshots"
    root.mkdir(parents=True, exist_ok=True)
    name = f"outside-edit-banner-{'dark' if dark else 'light'}-{int(scale * 100)}.png"
    assert host.grab().save(str(root / name))


@pytest.mark.parametrize("before,after", [(1.0, 1.5), (1.5, 1.0)])
def test_live_font_change_updates_every_label_bound(
    qtbot: QtBot,
    visual_family: str,
    before: float,
    after: float,
) -> None:
    area, host = QScrollArea(), QWidget()
    qtbot.addWidget(area)
    host.setFont(_font(visual_family, before))
    layout = QVBoxLayout(host)
    banner = OutsideEditBanner(host)
    layout.addWidget(banner)
    area.setWidget(host)
    area.setWidgetResizable(True)
    banner.set_state(edited=True, eligible=True)
    banner.show_work("discard")
    banner.show_note("Could not keep outside edit. " * 150, "D:/Pistë 日本/source")
    host.setFont(_font(visual_family, after))
    area.resize(310, 300)
    area.show()
    QApplication.processEvents()
    for label in (banner.title, banner.activity, banner.note):
        assert label.maximumHeight() == label.fontMetrics().lineSpacing() * 4
    assert area.horizontalScrollBar().maximum() == 0
    assert banner.lock_button.width() >= banner.lock_button.sizeHint().width()
    _labels_fit(banner)


def test_unbroken_failure_cannot_widen_the_banner(qtbot: QtBot, visual_family: str) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    host.setFont(_font(visual_family, 1.5))
    layout = QVBoxLayout(host)
    banner = OutsideEditBanner(host)
    layout.addWidget(banner)
    banner.set_state(edited=True, eligible=True)
    banner.show_note("Could not keep outside edit: " + "X" * 600, "D:/Pistë 日本/source")
    host.setFixedWidth(310)
    host.resize(310, 800)
    host.show()
    QApplication.processEvents()
    assert banner.minimumSizeHint().width() <= 310 - 2 * layout.contentsMargins().left()
    assert host.rect().contains(banner.geometry())
    assert banner.rect().contains(banner.note.geometry())
    _labels_fit(banner)
