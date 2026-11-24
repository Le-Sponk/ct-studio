"""Settings → Advanced's machine settings (P5-T08e1, P5-T08e2): read and saved in
``settings.json``.

``AdvancedService``: whether the dashboard's build log shows the tool command rows, and how
many build logs each project keeps. ``load`` reads both together, fresh; a damaged or newer
file raises ``SettingsError`` and is never written. Saving what the file already says writes
nothing (no backup). Builds read the settings themselves, fresh for every build
(``build_controller``, ``ctstudio build``).
"""

from __future__ import annotations

from pathlib import Path

from ctstudio.core.project import settings

TOOL_COMMANDS = "toolCommands"  # the choices' names on the page, and the keys of ``load``
BUILD_LOGS_KEPT = "buildLogsKept"


class AdvancedService:
    def __init__(self, *, settings_path: Path | None = None) -> None:
        self._settings_path = settings_path

    def load(self) -> dict[str, object]:
        """Tool commands shown (absent: shown) and build logs kept (absent: None, 20)."""
        current = settings.load(self._settings_path)
        return {
            TOOL_COMMANDS: current.show_tool_commands(),
            BUILD_LOGS_KEPT: current.build_logs_kept(),
        }

    def save_tool_commands(self, shown: bool) -> bool:
        """Save ``shown`` and return it."""
        current = settings.load(self._settings_path)
        if current.show_tool_commands() != shown:
            settings.save(current.with_show_tool_commands(shown), self._settings_path)
        return shown

    def save_build_logs_kept(self, kept: int | None) -> int | None:
        """Save ``kept`` (None: the default) and return it."""
        current = settings.load(self._settings_path)
        if current.build_logs_kept() != kept:
            settings.save(current.with_build_logs_kept(kept), self._settings_path)
        return kept
