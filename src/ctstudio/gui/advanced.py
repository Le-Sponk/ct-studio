"""Settings → Advanced's machine settings (P5-T08e1): read and saved in ``settings.json``.

``ToolCommandsService``: whether the dashboard's build log shows the tool command rows.
Each call reads the file fresh; a damaged or newer file raises ``SettingsError`` and is
never written. Saving what the file already says writes nothing (no backup). GUI builds read
the setting themselves, fresh for every build (``build_controller``).
"""

from __future__ import annotations

from pathlib import Path

from ctstudio.core.project import settings


class ToolCommandsService:
    def __init__(self, *, settings_path: Path | None = None) -> None:
        self._settings_path = settings_path

    def load(self) -> bool:
        """Whether tool commands are shown (absent from the file: shown)."""
        return settings.load(self._settings_path).show_tool_commands()

    def save(self, shown: bool) -> bool:
        """Save ``shown`` and return it."""
        current = settings.load(self._settings_path)
        if current.show_tool_commands() != shown:
            settings.save(current.with_show_tool_commands(shown), self._settings_path)
        return shown
