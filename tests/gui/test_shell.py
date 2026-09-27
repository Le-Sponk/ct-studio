"""P1-T06 GUI shell, headless screenshots and Qt-free CLI probes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QAction, QColor, QFontDatabase, QImage, QPalette
from PySide6.QtWidgets import QApplication, QDialog, QLabel
from pytestqt.qtbot import QtBot

from ctstudio import __version__
from ctstudio.__main__ import main
from ctstudio.core.errors import ProjectError
from ctstudio.gui.app import _save_smoke
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]
REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENS = REPO_ROOT / "tests" / "artifacts" / "screens"


def test_no_argument_entry_point_dispatches_to_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    from ctstudio.gui import app as gui_app

    called: list[Path | None] = []

    def fake_run_gui(path: Path | None) -> int:
        called.append(path)
        return 17

    monkeypatch.setattr(gui_app, "run_gui", fake_run_gui)
    assert main([]) == 17
    assert called == [None]


def test_gui_entry_point_configures_logging_before_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    from ctstudio.core import logging as log_module
    from ctstudio.gui import app as gui_app

    events: list[str] = []
    monkeypatch.setattr(log_module, "configure_logging", lambda: events.append("logging"))
    monkeypatch.setattr(gui_app, "run_gui", lambda _path: events.append("gui") or 0)
    assert main([]) == 0
    assert events == ["logging", "gui"]


def test_empty_dashboard_and_about_dialog(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert QFontDatabase.families(), "offscreen screenshots need a font, not tofu boxes"
    assert window.windowTitle() == "CT Studio"
    assert window.findChild(QLabel, "emptyTitle").text() == "No project open"
    assert "project" in window.findChild(QLabel, "emptyBody").text().lower()
    action = window.findChild(QAction, "aboutAction")
    assert action is not None
    action.trigger()
    dialog = window.findChild(QDialog, "aboutDialog")
    assert dialog is not None and dialog.isVisible()
    content = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert __version__ in content
    assert "GPL-3.0-or-later" in content
    assert "Third-party" in content and "before release" in content
    SCREENS.mkdir(parents=True, exist_ok=True)
    assert dialog.grab().save(str(SCREENS / "p1-t06-about.png"), "PNG")
    dialog.close()


def test_system_palette_light_and_dark_snapshots(qtbot: QtBot) -> None:
    app = QApplication.instance()
    assert app is not None
    original = app.palette()
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1280, 720)
    window.show()
    SCREENS.mkdir(parents=True, exist_ok=True)
    try:
        for theme, background, foreground in (
            ("light", "#f3f5f8", "#202530"),
            ("dark", "#202530", "#f3f5f8"),
        ):
            palette = QPalette(original)
            for role in (
                QPalette.ColorRole.WindowText,
                QPalette.ColorRole.Text,
                QPalette.ColorRole.ButtonText,
            ):
                palette.setColor(role, QColor(foreground))
            for role in (
                QPalette.ColorRole.Window,
                QPalette.ColorRole.Base,
                QPalette.ColorRole.Button,
            ):
                palette.setColor(role, QColor(background))
            app.setPalette(palette)
            app.processEvents()
            assert window.palette().color(QPalette.ColorRole.Window) == QColor(background)
            screenshot = SCREENS / f"p1-t06-dashboard-{theme}.png"
            assert window.grab().save(str(screenshot), "PNG")
            assert QImage(str(screenshot)).width() == 1280
            if theme == "dark":
                window.about_dialog.open()
                app.processEvents()
                assert window.about_dialog.grab().save(
                    str(SCREENS / "p1-t06-about-dark.png"), "PNG"
                )
                window.about_dialog.close()
    finally:
        app.setPalette(original)


def test_offscreen_smoke_writes_png_to_unicode_path(tmp_path: Path) -> None:
    png = tmp_path / "course é screenshots" / "dashboard.png"
    result = subprocess.run(  # noqa: S603 - argv uses our Python module, no shell
        [sys.executable, "-m", "ctstudio", "--offscreen-smoke", str(png)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=25,
        check=False,
        env={**os.environ, "QT_QPA_PLATFORM": "invalid"},
    )
    assert result.returncode == 0, result.stderr
    assert png.is_file()
    image = QImage(str(png))
    assert not image.isNull() and image.width() >= 800 and image.height() >= 500


def test_offscreen_smoke_at_150_percent_scale(tmp_path: Path) -> None:
    png = tmp_path / "scaled.png"
    result = subprocess.run(  # noqa: S603 - argv uses our Python module, no shell
        [sys.executable, "-m", "ctstudio", "--offscreen-smoke", str(png)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=25,
        check=False,
        env={**os.environ, "QT_SCALE_FACTOR": "1.5", "QT_QPA_PLATFORM": "offscreen"},
    )
    assert result.returncode == 0, result.stderr
    image = QImage(str(png))
    assert not image.isNull() and image.width() >= 960 and image.height() >= 600
    SCREENS.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(png, SCREENS / "p1-t06-dashboard-150pct.png")


def test_smoke_publish_failure_leaves_no_partial_png(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    destination = tmp_path / "shots é" / "smoke.png"

    def fail_publish(_source: Path, _destination: Path) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr(os, "link", fail_publish)
    with pytest.raises(ProjectError, match="Could not save screenshot"):
        _save_smoke(window, destination)
    assert not destination.exists()
    assert list(destination.parent.iterdir()) == []


def test_offscreen_smoke_never_overwrites_an_existing_png(tmp_path: Path) -> None:
    png = tmp_path / "saved.png"
    png.write_bytes(b"user work")
    result = subprocess.run(  # noqa: S603 - argv uses our Python module, no shell
        [sys.executable, "-m", "ctstudio", "--offscreen-smoke", str(png)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=25,
        check=False,
    )
    assert result.returncode == 1
    assert "Choose a new output name" in result.stderr
    assert png.read_bytes() == b"user work"


def test_importtime_version_stays_qt_free() -> None:
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "ctstudio", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"ctstudio {__version__}"
    assert "PySide6" not in result.stderr and "shiboken6" not in result.stderr
