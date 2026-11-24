"""The colour scheme chosen on this computer (P5-T08d): saved in ``settings.json``, applied
through Qt.

Qt 6.8 and later let an application ask for the light or dark scheme
(``QStyleHints.setColorScheme``); ``Unknown`` follows the system again. Measured on Qt 6.11.2:
the Windows platform repaints open windows at once and goes back to the system's scheme for
``Unknown``; the offscreen platform ignores the request (its scheme stays ``Unknown``). So
whether a request worked is read back from ``colorScheme()``. ``run_gui`` applies the saved
scheme before the main window exists; Settings → Appearance applies a new choice once it is
saved.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from ctstudio.core.project import settings

_LOG = logging.getLogger(__name__)
SCHEMES = {None: Qt.ColorScheme.Unknown, "light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}


class Hints(Protocol):
    """The part of ``QStyleHints`` used here."""

    def colorScheme(self, /) -> Qt.ColorScheme: ...

    def setColorScheme(self, scheme: Qt.ColorScheme, /) -> None: ...


def style_hints() -> Hints:
    return QGuiApplication.styleHints()


def apply_scheme(scheme: str | None) -> bool:
    """Ask Qt for ``scheme`` (None: follow the system). True when the system now shows it;
    following the system always counts as shown."""
    hints = style_hints()
    wanted = SCHEMES[scheme]
    hints.setColorScheme(wanted)
    return scheme is None or hints.colorScheme() == wanted


def apply_saved(path: Path | None = None) -> None:
    """At start, before any window: the saved scheme. A damaged or newer settings file is
    logged and the system's scheme kept; Settings → Appearance explains the file."""
    try:
        scheme = settings.load(path).colour_scheme()
    except settings.SettingsError:
        _LOG.warning("The colour scheme follows the system: settings cannot be used", exc_info=True)
        return
    apply_scheme(scheme)


class AppearanceService:
    """The colour scheme in ``settings.json``. Each call reads the file fresh; a damaged or
    newer file raises ``SettingsError`` and is never written. Saving what the file already
    says writes nothing (no backup)."""

    def __init__(self, *, settings_path: Path | None = None) -> None:
        self._settings_path = settings_path

    def load(self) -> str | None:
        """The saved scheme; None: follow the system."""
        return settings.load(self._settings_path).colour_scheme()

    def save(self, scheme: str | None) -> str | None:
        """Save ``scheme`` (None: follow the system) and return it."""
        current = settings.load(self._settings_path)
        if current.colour_scheme() != scheme:
            settings.save(current.with_colour_scheme(scheme), self._settings_path)
        return scheme
