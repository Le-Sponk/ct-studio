"""P5-T10d: a compact dashboard header, so the part cards start near the top."""

from __future__ import annotations

from pathlib import Path

import pytest
from build_window_helpers import build_window
from editor_request_helpers import settled
from outside_visual_helpers import visual_style
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QApplication,
    QLayout,
    QProxyStyle,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)
from pytestqt.qtbot import QtBot
from wizard_fakes import shot

from ctstudio.gui.views.dashboard import Dashboard
from ctstudio.gui.views.header_buttons import HeaderButtons

pytestmark = [pytest.mark.gui]

LABELS = ["Refresh statuses", "Copy project folder", "Project details…", "Open in Blender"]


def _app() -> QApplication:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    return app


def _header(page: Dashboard) -> list[QPushButton]:
    return [page.refresh_button, page.copy_project, page.edit_button, page.open_blender]


def _rows(buttons: list[QPushButton], ancestor: QWidget) -> int:
    return len({button.mapTo(ancestor, QPoint()).y() for button in buttons})


def _gap(buttons: list[QPushButton], ancestor: QWidget) -> int:
    """The space Qt puts between the first two buttons (side by side in either layout)."""
    left, right = buttons[0], buttons[1]
    return right.mapTo(ancestor, QPoint()).x() - left.mapTo(ancestor, QPoint()).x() - left.width()


def _whole_and_inside(buttons: list[QPushButton], page: QWidget) -> bool:
    return all(
        button.width() >= button.sizeHint().width()  # the whole label, never squeezed
        and button.mapTo(page, QPoint()).x() + button.width() <= page.width()
        for button in buttons
    )


@pytest.mark.parametrize("enlarged", [False, True], ids=["normal", "enlarged"])
def test_the_first_card_starts_in_the_top_part_of_the_window(
    qtbot: QtBot, tmp_path: Path, enlarged: bool
) -> None:
    with visual_style(_app(), False, enlarged), build_window(qtbot, tmp_path) as (view, _p, _f):
        view.resize(1280, 720)
        page = view.dashboard
        first = page.cards[next(iter(page.cards))]

        def top() -> float:
            return first.mapTo(view, QPoint()).y() / view.height()

        assert settled(qtbot, lambda: top() <= 0.40), f"the first card starts at {top():.0%}"
        assert page.access_label.isHidden(), "a writable project needs no access line"
        assert page.notice.text() and not page.notice.isHidden()  # something to say: shown
        assert _rows(_header(page), page) == 1, "the header buttons are not on one row"
        assert _whole_and_inside(_header(page), page)
        shot(view, f"p5-t10d-header-1280x720-{'enlarged' if enlarged else 'normal'}.png")


def test_the_header_buttons_take_two_rows_only_when_one_does_not_fit(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with visual_style(_app(), False, True), build_window(qtbot, tmp_path) as (view, _p, _f):
        page = view.dashboard
        buttons = _header(page)
        view.resize(800, 600)
        assert settled(qtbot, lambda: _whole_and_inside(buttons, page)), "a button was cut"
        strip = page.header_buttons
        needed = sum(button.sizeHint().width() for button in buttons) + 3 * _gap(buttons, page)
        assert _rows(buttons, page) == (2 if needed > strip.width() else 1)
        shot(view, "p5-t10d-header-800x600-enlarged.png")
        view.resize(1280, 720)
        assert settled(qtbot, lambda: _rows(buttons, page) == 1), "no way back to one row"


class _PairSpacing(QProxyStyle):
    """A style that leaves spacing to each pair of controls, as some Linux themes do."""

    def pixelMetric(
        self,
        metric: QStyle.PixelMetric,
        option: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        if metric == QStyle.PixelMetric.PM_LayoutHorizontalSpacing:
            return -1
        return super().pixelMetric(metric, option, widget)

    def layoutSpacing(
        self,
        control1: QSizePolicy.ControlType,
        control2: QSizePolicy.ControlType,
        orientation: Qt.Orientation,
        option: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        return 14


def _strip(qtbot: QtBot) -> tuple[QWidget, HeaderButtons, list[QPushButton]]:
    """The strip inside a plain window, as on the dashboard (never a window itself)."""
    window = QWidget()
    qtbot.addWidget(window)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)  # the strip is exactly as wide as the window
    layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)  # any size we ask for
    buttons = [QPushButton(label) for label in LABELS]
    strip = HeaderButtons(buttons, window)
    layout.addWidget(strip)
    layout.addStretch(1)
    return window, strip, buttons


def test_a_button_strip_follows_its_width(qtbot: QtBot) -> None:
    window, strip, buttons = _strip(qtbot)
    one_row = sum(button.sizeHint().width() for button in buttons) + 60
    window.resize(one_row, 200)
    window.show()
    qtbot.waitExposed(window)
    assert settled(qtbot, lambda: _rows(buttons, strip) == 1), "room for one row"
    assert all(b.y() == buttons[0].y() for b in buttons)
    two_rows = max(b.sizeHint().width() for b in buttons) * 2 + 40
    assert strip.minimumSizeHint().width() <= two_rows, "on one row it cannot shrink to two"
    window.resize(one_row // 2, 200)
    assert settled(qtbot, lambda: _rows(buttons, strip) == 2), "no room, still one row"
    order = [(b.mapTo(strip, QPoint()).y(), b.mapTo(strip, QPoint()).x()) for b in buttons]
    assert order == sorted(order), "the buttons changed order"


@pytest.mark.parametrize("pairs", [False, True], ids=["style-gap", "pair-gap"])
def test_one_row_needs_the_gaps_between_the_buttons_too(qtbot: QtBot, pairs: bool) -> None:
    window, strip, buttons = _strip(qtbot)
    style = _PairSpacing("Fusion")
    if pairs:
        window.setStyle(style)
        for widget in (strip, *buttons):
            widget.setStyle(style)
    window.resize(sum(button.sizeHint().width() for button in buttons) + 200, 200)
    window.show()
    qtbot.waitExposed(window)
    assert settled(qtbot, lambda: _rows(buttons, strip) == 1)
    gap = _gap(buttons, strip)
    assert gap > 0, "no space between the buttons"
    needed = sum(button.sizeHint().width() for button in buttons) + 3 * gap
    window.resize(needed - 1, 200)
    assert settled(qtbot, lambda: _rows(buttons, strip) == 2), "one row with squeezed labels"
    window.resize(needed, 200)
    assert settled(qtbot, lambda: _rows(buttons, strip) == 1), "room for one row"
    assert _whole_and_inside(buttons, strip)


def test_a_longer_label_moves_the_buttons_to_two_rows(qtbot: QtBot) -> None:
    window, strip, buttons = _strip(qtbot)
    window.resize(sum(button.sizeHint().width() for button in buttons) + 60, 200)
    window.show()
    qtbot.waitExposed(window)
    assert settled(qtbot, lambda: _rows(buttons, strip) == 1)
    buttons[0].setText(LABELS[0] + " and everything else as well")  # same size of window
    assert settled(qtbot, lambda: _rows(buttons, strip) == 2), "the longer label was cut"


def test_a_bigger_font_moves_the_buttons_to_two_rows(qtbot: QtBot) -> None:
    window, strip, buttons = _strip(qtbot)
    window.resize(sum(button.sizeHint().width() for button in buttons) + 60, 200)
    window.show()
    qtbot.waitExposed(window)
    assert settled(qtbot, lambda: _rows(buttons, strip) == 1)
    font = strip.font()
    font.setPointSizeF(font.pointSizeF() * 2)
    strip.setFont(font)  # the same width: only the labels grew
    assert settled(qtbot, lambda: _rows(buttons, strip) == 2), "the bigger labels were cut"
