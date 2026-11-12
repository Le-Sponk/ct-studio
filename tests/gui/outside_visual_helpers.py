"""P5-T06c2b2c1 whole-window fixtures; installed fonts/palettes are visual proxies."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# _opened is the existing test-only entry to the real window's adoption/navigation path.
import os
from collections.abc import Generator
from contextlib import contextmanager
from itertools import pairwise
from pathlib import Path

from outside_flow_helpers import all_tools
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QScrollArea, QWidget
from pytestqt.qtbot import QtBot
from reconcile_helpers import EditWork, edited_project, settled

from ctstudio.core.project.project import Project
from ctstudio.gui.launch_controller import LaunchController
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.outside_edit_banner import OutsideEditBanner


def installed_font(registered: list[int]) -> str:
    if os.name == "nt":
        for name in ("segoeui.ttf", "msgothic.ttc"):
            path = Path(os.environ["WINDIR"]) / "Fonts" / name
            if path.is_file():
                registered.append(QFontDatabase.addApplicationFont(str(path)))
    families = QFontDatabase.families()
    family = next((name for name in ("Segoe UI", "DejaVu Sans", "Arial") if name in families), "")
    assert family, "no readable installed visual-test font"
    return family


def proxy_palette(base: QPalette, dark: bool) -> QPalette:
    palette = QPalette(base)
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
        palette.setColor(role, QColor("#252525" if dark else "#fafafa"))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(role, QColor("#eeeeee" if dark else "#151515"))
        palette.setColor(
            QPalette.ColorGroup.Disabled, role, QColor("#999999" if dark else "#666666")
        )
    return palette


@contextmanager
def visual_style(app: QApplication, dark: bool, enlarged: bool) -> Generator[str, None, None]:
    original_font, original_palette = QFont(app.font()), QPalette(app.palette())
    registered: list[int] = []
    try:
        family = installed_font(registered)
        font = QFont(family, 15 if enlarged else 10)
        font.setFamilies([family, "MS Gothic"])
        font.setStretch(120 if enlarged else 100)
        assert QFontMetrics(font).inFontUcs4(ord("A")), "Latin text would render as boxes"
        app.setFont(font)
        app.setPalette(proxy_palette(original_palette, dark))
        yield family
    finally:
        app.setFont(original_font)
        app.setPalette(original_palette)
        for identifier in registered:
            if identifier >= 0:
                QFontDatabase.removeApplicationFont(identifier)


@contextmanager
def outside_window(
    qtbot: QtBot, folder: Path, size: tuple[int, int]
) -> Generator[tuple[MainWindow, Project, EditWork, QScrollArea], None, None]:
    project, work = edited_project(folder), EditWork()
    services = AppServices(
        launch=LaunchController(lock=work.lock, discard=work.discard),
        status=StatusService(find_tools=all_tools),
    )
    window = MainWindow(services)
    qtbot.addWidget(window)
    try:
        window.resize(*size)
        window.show()
        window.activateWindow()
        assert settled(qtbot, lambda: not window.welcome.busy), "welcome never finished"
        window._opened(project)
        assert settled(qtbot, lambda: idle(window)), "initial statuses never finished"
        area = window.findChild(QScrollArea, "dashboardScroll")
        assert area is not None, "actual MainWindow dashboard scroll area missing"
        assert services.project is project, "window did not adopt the synthetic project"
        yield window, project, work, area
    finally:
        work.gate.set()
        services.editing = False
        finished = services.shutdown(10)
        assert finished, "real outside-edit/status/watch owners did not finish"
        window.close()
        project.close()


def idle(window: MainWindow) -> bool:
    return not (window.services.launch.busy or window.services.status.busy or window.dashboard.busy)


def mapped(widget: QWidget, ancestor: QWidget) -> QRect:
    return QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())


def settle_layout(qtbot: QtBot, window: MainWindow, area: QScrollArea) -> None:
    def ready() -> bool:
        page = window.dashboard
        layout = page.layout()
        assert layout is not None, "dashboard has no layout"
        wanted = max(layout.totalHeightForWidth(page.width()), area.viewport().height())
        labels = page.cards["kcl"].outside.findChildren(QLabel)
        labels = [label for label in labels if label.isVisible() and label.text()]
        return page.height() == wanted and all(
            label.height() == min(label.maximumHeight(), label.heightForWidth(label.width()))
            for label in labels
        )

    assert settled(qtbot, ready), "queued dashboard/banner geometry never settled"


def reveal(qtbot: QtBot, window: MainWindow, area: QScrollArea, target: QWidget) -> None:
    settle_layout(qtbot, window, area)
    area.ensureWidgetVisible(target, 0, 0)
    visible(qtbot, area, target)


def visible(qtbot: QtBot, area: QScrollArea, target: QWidget) -> None:
    assert settled(
        qtbot, lambda: area.viewport().rect().contains(mapped(target, area.viewport()))
    ), (
        f"{target.objectName()} not fully visible: {mapped(target, area.viewport())} "
        f"in {area.viewport().rect()}"
    )


def assert_label_height(child: QWidget) -> None:
    if isinstance(child, QLabel) and child.text():
        assert child.wordWrap(), f"{child.objectName()} does not wrap long outside-edit text"
        wanted = min(child.maximumHeight(), child.heightForWidth(child.width()))
        assert wanted > 0, f"{child.objectName()} has no wrapped height requirement"
        assert child.height() >= wanted, f"{child.objectName()} wrap clipped"


def assert_banner(banner: OutsideEditBanner) -> None:
    children = [
        child
        for child in banner.findChildren(QWidget)
        if child.isVisible() and child.parentWidget() is banner
    ]
    children.sort(key=lambda child: child.y())
    for child in children:
        assert banner.rect().contains(mapped(child, banner)), child.objectName()
        assert_label_height(child)
    for previous, following in pairwise(children):
        assert previous.geometry().bottom() < following.y(), "outside-edit content overlaps"
    assert banner.lock_button.text() == "Lock as manual"
    assert banner.discard_button.text() == "Discard…"


def assert_geometry(window: MainWindow, area: QScrollArea) -> None:
    page, viewport = window.dashboard, area.viewport()
    assert page.width() <= viewport.width(), (
        f"page width {page.width()} > viewport {viewport.width()}"
    )
    assert area.horizontalScrollBar().maximum() == 0, "dashboard scrolls horizontally"
    for card in page.cards.values():
        assert 0 <= card.x() and card.geometry().right() < page.width(), card.objectName()
        assert_banner(card.outside)
    for button in page.findChildren(QAbstractButton):
        if button.isVisible():
            assert mapped(button, page).left() >= 0, button.objectName()
            assert mapped(button, page).right() < page.width(), button.objectName()
            assert button.width() >= button.sizeHint().width(), (
                f"{button.objectName()} native label clipped"
            )


def enabled_buttons(page: QWidget) -> list[QAbstractButton]:
    return [
        b
        for b in page.findChildren(QAbstractButton)
        if b.isVisible() and b.isEnabled() and b.focusPolicy() != Qt.FocusPolicy.NoFocus
    ]


def tab_controls(qtbot: QtBot, window: MainWindow, area: QScrollArea) -> None:
    page = window.dashboard
    settle_layout(qtbot, window, area)
    expected = set(enabled_buttons(page))
    window.activateWindow()
    QApplication.processEvents()
    page.refresh_button.setFocus()
    assert page.refresh_button.hasFocus(), "native focus did not activate"
    visited: set[QWidget] = set()
    for _index in range(200):
        focus = QApplication.focusWidget()
        assert focus is not None, "Tab lost native focus"
        if focus in expected:
            visited.add(focus)
            visible(qtbot, area, focus)
        if visited == expected:
            break
        QTest.keyClick(focus, Qt.Key.Key_Tab)
    assert visited == expected, (
        f"unreachable buttons: {[b.objectName() for b in expected - visited]}"
    )


def capture(window: MainWindow, folder: Path, name: str, *, page: bool = False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    QApplication.processEvents()
    path = folder / f"{name}.png"
    target = window.dashboard if page else window
    assert target.grab().save(str(path)), f"could not save {path}"
    return path
