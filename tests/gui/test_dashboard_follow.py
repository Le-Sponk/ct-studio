"""P5-T03e34: the dashboard keeps the newest build output in view while the reader is at its end."""

from pathlib import Path

import pytest
from build_fakes import summary
from build_window_helpers import build_window, eventually, finished, started
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget
from pytestqt.qtbot import QtBot
from test_build_dashboard_visual import _layout_settled, _palette
from wizard_fakes import shot

from ctstudio.core.build.events import BuildFinished, LogLine, NodeFailed
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.views.dashboard_follow import DashboardFollower

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def _area(view: MainWindow) -> QScrollArea:
    area = view.findChild(QScrollArea, "dashboardScroll")
    assert area is not None
    return area


def _settle(qtbot: QtBot, view: MainWindow) -> QScrollArea:
    area = _area(view)
    eventually(qtbot, lambda: _layout_settled(view, area), "dashboard layout did not settle")
    QApplication.processEvents()  # a queued follow request runs after the final range change
    QApplication.processEvents()
    return area


def _bottom_in_view(area: QScrollArea, widget: QWidget) -> bool:
    return (
        area.viewport().rect().contains(widget.mapTo(area.viewport(), widget.rect().bottomLeft()))
    )


def _top_in_view(area: QScrollArea, widget: QWidget) -> bool:
    return area.viewport().rect().contains(widget.mapTo(area.viewport(), widget.rect().topLeft()))


def _fail(view: MainWindow) -> None:
    view.services.build.build_event.emit(
        NodeFailed("stage:kcl", "Cannot read the collision source.", "Check the file.", False)
    )


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_build_scrolls_to_newest_output_without_moving_focus(
    qtbot: QtBot, tmp_path: Path, dark: bool
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    old_palette = QPalette(app.palette())
    app.setPalette(_palette(old_palette, dark))
    try:
        with build_window(qtbot, tmp_path) as (view, _project, fake):
            view.resize(720, 480)
            log, controls = view.dashboard.builds.log, view.dashboard.builds.controls
            log.toggle.click()
            area = _settle(qtbot, view)
            area.verticalScrollBar().setValue(0)
            assert not _bottom_in_view(area, controls)
            controls.test_button.click()
            started(qtbot, view, fake)
            focus = QApplication.focusWidget()
            view.services.build.build_event.emit(
                LogLine("stage:kcl", "\n".join(map(str, range(80))))
            )
            # The panel shows its list in its own queued refresh; layout grows after that.
            eventually(qtbot, log.view.isVisible, "log output was never shown")
            area = _settle(qtbot, view)
            bar = area.verticalScrollBar()
            assert bar.maximum() > 0 and bar.value() == bar.maximum()
            assert _top_in_view(area, log.view) and _bottom_in_view(area, log.view)
            assert _bottom_in_view(area, controls.cancel_button)
            assert QApplication.focusWidget() is focus
            shot(view, f"p5-t03e34-follow-{'dark' if dark else 'light'}.png")
    finally:
        app.setPalette(old_palette)


def test_late_result_and_error_stay_visible_as_layout_grows(qtbot: QtBot, tmp_path: Path) -> None:
    with build_window(qtbot, tmp_path) as (view, _project, fake):
        view.resize(720, 480)
        controls = view.dashboard.builds.controls
        controls.test_button.click()
        started(qtbot, view, fake)
        _fail(view)
        fake.events[-1] = BuildFinished(summary("failed", ran=(), failed=("stage:kcl",)))
        finished(qtbot, view, fake)
        area = _settle(qtbot, view)
        assert "Check the file" in controls.notice.text()
        assert _top_in_view(area, controls.notice)
        assert _bottom_in_view(area, controls.last_result)
        controls.show_notice("Line one\nLine two\nLine three")  # growth after the result
        area = _settle(qtbot, view)
        assert _bottom_in_view(area, controls.last_result)


def test_reader_scrolling_up_is_respected_until_back_at_end(qtbot: QtBot, tmp_path: Path) -> None:
    with build_window(qtbot, tmp_path) as (view, _project, fake):
        view.resize(720, 480)
        controls = view.dashboard.builds.controls
        controls.test_button.click()
        started(qtbot, view, fake)
        bar = _settle(qtbot, view).verticalScrollBar()
        assert bar.value() == bar.maximum() > 0
        bar.setValue(0)  # the reader scrolls up to the component cards
        _fail(view)
        area = _settle(qtbot, view)
        assert bar.value() == 0
        assert not _bottom_in_view(area, controls.notice)
        bar.setValue(bar.maximum())  # back at the end: follow again
        controls.show_notice("Another\nmulti-line\nwarning")
        area = _settle(qtbot, view)
        assert bar.value() == bar.maximum()
        assert _bottom_in_view(area, controls.notice)


def test_no_scrolling_before_a_build_or_after_rebinding(qtbot: QtBot, tmp_path: Path) -> None:
    with build_window(qtbot, tmp_path) as (view, project, fake):
        view.resize(720, 480)
        controls = view.dashboard.builds.controls
        bar = _settle(qtbot, view).verticalScrollBar()
        assert bar.maximum() > 0 and bar.value() == 0
        view.services.build.notice.emit("Not for any run.")
        controls.show_notice("Growth\nbefore\nany build")
        _settle(qtbot, view)
        assert bar.value() == 0
        controls.test_button.click()
        started(qtbot, view, fake)
        finished(qtbot, view, fake)
        _settle(qtbot, view)
        assert bar.value() == bar.maximum()
        view.dashboard.set_project(project, changed=True)  # rebinding forgets the run
        _settle(qtbot, view)
        before = bar.value()
        controls.show_notice("Growth\nafter\nrebinding")
        _settle(qtbot, view)
        assert bar.value() == before < bar.maximum()


def test_follower_scrolls_only_between_start_and_stop(qtbot: QtBot) -> None:
    area = QScrollArea()
    qtbot.addWidget(area)
    content = QWidget()
    content.setFixedHeight(400)
    area.setWidgetResizable(True)
    area.setWidget(content)
    area.resize(200, 100)
    follower = DashboardFollower(area)
    follower.attach(area)
    area.show()
    bar = area.verticalScrollBar()
    content.setFixedHeight(600)  # growth before any run
    eventually(qtbot, lambda: bar.maximum() > 400, "range never grew")
    assert bar.value() == 0
    follower.start()
    assert bar.value() == bar.maximum()
    content.setFixedHeight(800)
    eventually(qtbot, lambda: bar.maximum() > 600, "range never grew")
    assert bar.value() == bar.maximum()
    follower.stop()
    content.setFixedHeight(1000)
    eventually(qtbot, lambda: bar.maximum() > 800, "range never grew")
    assert bar.value() < bar.maximum()
