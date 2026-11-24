"""P5-T08d: the colour scheme's service, how it is applied, and applying it at every start.

``AppearanceService`` reads ``settings.json`` fresh for every call and writes nothing when
the file already says so; a damaged file is refused and never written. ``apply_scheme`` asks
Qt for the scheme and reports whether the system now shows it. ``run_gui`` applies the saved
scheme before the main window is made; a damaged file keeps the system's scheme.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from appearance_helpers import install_hints
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ctstudio.core.project import settings
from ctstudio.core.project.settings import COLOUR_SCHEME, SettingsError
from ctstudio.gui import app, appearance
from ctstudio.gui.appearance import AppearanceService, apply_saved, apply_scheme

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]
DAMAGED = '{"format": 1, "colour_scheme": "blue"}\n'


def outcome(call: Callable[[], object]) -> object:
    try:
        return call()
    except Exception as exc:
        return exc


def backups(path: Path) -> list[Path]:
    return [item for item in path.parent.iterdir() if item.name != path.name]


def test_the_schemes_qt_is_asked_for() -> None:
    assert appearance.SCHEMES == {
        None: Qt.ColorScheme.Unknown,
        "light": Qt.ColorScheme.Light,
        "dark": Qt.ColorScheme.Dark,
    }


def test_the_service_saves_reads_back_and_skips_needless_writes(tmp_path: Path) -> None:
    path = tmp_path / "config é" / "settings.json"
    service = AppearanceService(settings_path=path)
    assert service.load() is None, "no file must mean follow the system"
    assert service.save("dark") == "dark"
    assert json.loads(path.read_text(encoding="utf-8"))[COLOUR_SCHEME] == "dark"
    assert service.load() == "dark"
    before, made = path.read_bytes(), backups(path)
    assert service.save("dark") == "dark"
    assert path.read_bytes() == before and backups(path) == made, "an unchanged pick wrote"
    path.write_text('{"colour_scheme": "light", "future": 1}', encoding="utf-8")
    assert service.load() == "light", "the service did not read the file again"
    assert service.save(None) is None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert COLOUR_SCHEME not in data and data["future"] == 1


def test_the_service_refuses_a_damaged_file_and_never_writes_it(tmp_path: Path) -> None:
    path = tmp_path / "config é" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(DAMAGED, encoding="utf-8")
    service = AppearanceService(settings_path=path)
    assert isinstance(outcome(service.load), SettingsError)
    assert isinstance(outcome(lambda: service.save("dark")), SettingsError)
    assert path.read_text(encoding="utf-8") == DAMAGED, "a damaged file was overwritten"
    assert backups(path) == [], "a refused save made a backup"


@pytest.mark.parametrize(
    ("scheme", "wanted"),
    [
        ("light", Qt.ColorScheme.Light),
        ("dark", Qt.ColorScheme.Dark),
        (None, Qt.ColorScheme.Unknown),
    ],
)
def test_a_scheme_is_asked_for_and_shown(
    monkeypatch: pytest.MonkeyPatch, scheme: str | None, wanted: Qt.ColorScheme
) -> None:
    hints = install_hints(monkeypatch)
    assert apply_scheme(scheme) is True
    assert hints.asked == [wanted]


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_system_that_ignores_the_request_is_reported(
    monkeypatch: pytest.MonkeyPatch, scheme: str
) -> None:
    hints = install_hints(monkeypatch, honours=False)
    assert apply_scheme(scheme) is False, "an ignored request was reported as shown"
    assert hints.asked == [appearance.SCHEMES[scheme]]


@pytest.mark.parametrize("honours", [True, False])
@pytest.mark.parametrize("system", [Qt.ColorScheme.Dark, Qt.ColorScheme.Light])
def test_following_the_system_always_counts_as_shown(
    monkeypatch: pytest.MonkeyPatch, honours: bool, system: Qt.ColorScheme
) -> None:
    hints = install_hints(monkeypatch, honours=honours, system=system)
    assert apply_scheme(None) is True, f"following a {system} system was reported as refused"
    assert hints.asked == [Qt.ColorScheme.Unknown]
    assert hints.colorScheme() == system


@pytest.mark.parametrize("scheme", ["light", "dark", None])
def test_the_saved_scheme_is_applied(monkeypatch: pytest.MonkeyPatch, scheme: str | None) -> None:
    hints = install_hints(monkeypatch)
    settings.save(settings.UserSettings().with_colour_scheme(scheme))
    apply_saved()
    assert hints.asked == [appearance.SCHEMES[scheme]]


def test_a_damaged_file_keeps_the_systems_scheme(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    hints = install_hints(monkeypatch)
    path = settings.default_path()
    path.parent.mkdir(parents=True)
    path.write_text(DAMAGED, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="ctstudio.gui.appearance"):
        raised = outcome(apply_saved)
    assert raised is None, f"a damaged file stopped the start: {raised!r}"
    assert hints.asked == [], "a scheme was applied from a damaged file"
    assert any("follows the system" in record.getMessage() for record in caplog.records)
    assert path.read_text(encoding="utf-8") == DAMAGED


def test_every_start_applies_the_saved_scheme_before_the_window(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert qtbot is not None  # the running QApplication the start reuses
    hints = install_hints(monkeypatch)
    settings.save(settings.UserSettings().with_colour_scheme("dark"))
    seen: list[list[Qt.ColorScheme]] = []
    real_window = app.MainWindow

    def recorded_window() -> object:
        seen.append(list(hints.asked))
        return real_window()

    def running_app(_argv: list[str]) -> object:
        return QApplication.instance()

    monkeypatch.setattr(app, "QApplication", running_app)
    monkeypatch.setattr(app, "MainWindow", recorded_window)
    assert app.run_gui(tmp_path / "écran.png") == 0
    assert seen == [[Qt.ColorScheme.Dark]], f"the window was made with {seen!r} asked"
