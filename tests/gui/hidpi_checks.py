"""P5-T10h checks, run by test_high_dpi.py in a child pytest with QT_SCALE_FACTOR set.

Not collected on its own (no ``test_`` file prefix): the scale has to be set before the
QApplication exists, so each scale needs its own process. The parent also gives the child a
realistic screen (offscreen ``configfile``): 1280x720 logical at each scale, the size the
project's pictures use, not Qt's default 800x800 pixel screen. Each check reads the scale back
from the application, and the text is drawn in a real installed font (Segoe UI on Windows,
DejaVu Sans on Ubuntu) that is checked to draw letters, not boxes.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from editor_request_helpers import settled
from editor_settings_helpers import write_settings
from outside_visual_helpers import visual_style
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QLabel,
    QScrollArea,
    QWidget,
)
from pytestqt.qtbot import QtBot
from settings_visual_helpers import assert_readable, wrapped_fit
from settings_window_helpers import action, main_window, settings_dialog, shown_page
from test_dashboard_visual import sample, window
from tools_fakes import FakeDoctor, doctor, settings_file
from wizard_fakes import shot

from ctstudio.gui.views.path_label import PathLabel

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
__all__ = ["doctor", "settings_file"]  # fixtures used by name
SCREEN = (1280, 720)  # logical size of the child's screen at every scale


def application() -> QApplication:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    return app


@pytest.fixture(autouse=True)
def real_font() -> Iterator[None]:
    with visual_style(application(), dark=False, enlarged=False):  # asserts letters draw
        yield


def scale() -> float:
    wanted = float(os.environ["QT_SCALE_FACTOR"])
    app = application()
    assert app.devicePixelRatio() == pytest.approx(wanted), "the scale did not take effect"
    screen = app.primaryScreen().availableGeometry()
    assert (screen.width(), screen.height()) == SCREEN, f"a {screen.size()} screen"
    return wanted


def percent() -> str:
    return f"{round(scale() * 100)}pct"


def whole(child: QWidget, parent: QWidget) -> bool:
    top_left = child.mapTo(parent, child.rect().topLeft())
    return parent.rect().contains(QRect(top_left, child.size()))


def frame(widget: QWidget, top: QWidget, contents: list[QWidget]) -> QWidget:
    """The scrolled contents ``widget`` is in (scrolled out of view is not cut), else top."""
    parent = widget.parentWidget()
    while parent is not None and parent is not top:
        if parent in contents:
            return parent
        parent = parent.parentWidget()
    return top


def scrolled_contents(top: QWidget) -> list[QWidget]:
    """Shown scrolled contents; each may run past the bottom but never past the side."""
    contents: list[QWidget] = []
    for area in top.findChildren(QScrollArea):
        inner = area.widget()
        if area.isVisible() and inner is not None:
            contents.append(inner)
            side = f"{inner.width()} > {area.viewport().width()}"
            assert inner.width() <= area.viewport().width(), f"scrolled sideways: {side}"
    return contents


def within(widget: QWidget, holder: QWidget) -> bool:
    """Whole inside each parent up to ``holder``: a parent crops what sticks out of it."""
    parent = widget.parentWidget()
    while parent is not None:
        if not whole(widget, parent):
            return False
        if parent is holder:
            return True
        parent = parent.parentWidget()
    return True


def assert_button_fits(button: QAbstractButton, holder: QWidget) -> None:
    assert within(button, holder), f"{button.text()!r} is cut off"
    needed = button.minimumSizeHint()
    size = f"{button.width()}x{button.height()} < {needed.width()}x{needed.height()}"
    assert button.width() >= needed.width(), f"{button.text()!r}: {size}"
    assert button.height() >= needed.height(), f"{button.text()!r}: {size}"


def assert_label_fits(label: QLabel, holder: QWidget) -> None:
    """Whole in its frame; wrapped text has its height; one line has its height and width,
    unless it is a path shortened on purpose (PathLabel, whole path on hover and Copy)."""
    assert within(label, holder), f"{label.text()[:40]!r} sticks out of its frame"
    if label.wordWrap():
        needed = label.heightForWidth(label.width())
        assert label.height() >= needed, f"{label.text()[:40]!r} is cut short"
        return
    line = label.fontMetrics().height()
    assert label.contentsRect().height() >= line, f"{label.text()!r} is cut short"
    if isinstance(label, PathLabel) or label.textFormat() != Qt.TextFormat.PlainText:
        return  # a rich-text width would be measured on its markup
    needed = label.fontMetrics().horizontalAdvance(label.text())
    assert label.contentsRect().width() >= needed, f"{label.text()!r} is clipped"


def assert_lists_fit(top: QWidget) -> None:
    """Tables and lists never scroll sideways; a choice shows its whole text."""
    for view in top.findChildren(QAbstractItemView):
        if view.isVisible():
            bar = view.horizontalScrollBar()
            assert bar.maximum() == 0, f"{view.objectName()} scrolls sideways by {bar.maximum()}"
    for box in top.findChildren(QComboBox):
        if box.isVisible():
            needed = box.fontMetrics().horizontalAdvance(box.currentText())
            assert box.width() >= needed, f"{box.currentText()!r} is clipped"


def laid_out(top: QWidget) -> bool:
    """Every shown button has reached its minimum size: the layout has caught up."""
    for button in top.findChildren(QAbstractButton):
        if button.isVisible() and button.text():
            needed = button.minimumSizeHint()
            if button.width() < needed.width() or button.height() < needed.height():
                return False
    return True


def assert_nothing_clipped(top: QWidget) -> None:
    """Every shown button, label, table and choice fits (scrolled out of view is not cut)."""
    contents = scrolled_contents(top)
    for button in top.findChildren(QAbstractButton):
        if button.isVisible() and button.text():
            assert_button_fits(button, frame(button, top, contents))
    for label in top.findChildren(QLabel):
        if label.isVisible() and label.text():
            assert_label_fits(label, frame(label, top, contents))
    assert_lists_fit(top)


def test_dashboard_at_scale(qtbot: QtBot, tmp_path: Path) -> None:
    factor = scale()
    view = window(qtbot, tmp_path)
    view.resize(*SCREEN)
    sample(view)
    settled(qtbot, lambda: laid_out(view))  # the cards take a few turns to settle
    for part, card in view.dashboard.cards.items():
        icon = card.findChild(QLabel, f"{part}Icon")
        assert icon is not None
        drawn = icon.pixmap()
        assert not drawn.isNull(), f"{part}: no status icon"
        assert drawn.devicePixelRatio() >= factor, f"{part}: icon drawn below the scale"
        assert drawn.width() >= 16 * factor, f"{part}: {drawn.width()} px icon"
    assert_nothing_clipped(view)
    shot(view, f"p5-t10h-dashboard-{percent()}.png")
    view.close()


@pytest.mark.parametrize("page", ["Tools", "Editors"])
def test_settings_at_scale(
    qtbot: QtBot, doctor: FakeDoctor, settings_file: Path, page: str
) -> None:
    scale()
    write_settings({"format": 1, "editor_preferences": {".kmp": "kmp_cloud"}})
    with main_window(qtbot, doctor, settings_file) as (view, _preferences):
        action(view, "toolsAction" if page == "Tools" else "editorsAction").trigger()
        dialog = settings_dialog(view)
        made = view.tools_window.page if page == "Tools" else view.editors_window.page
        assert made is not None
        assert settled(qtbot, lambda: not made.busy), "the page's first read never ended"
        assert settled(qtbot, lambda: wrapped_fit(dialog)), "the window never refitted"
        assert shown_page(dialog) == page
        assert_readable(dialog)
        assert_nothing_clipped(dialog)
        shot(dialog, f"p5-t10h-settings-{page.lower()}-{percent()}.png")
