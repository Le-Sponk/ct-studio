"""Which built-in editor Open in… lists first, per file kind (P5-T07f1).

A plain service for Settings → Editors…: it reads the user's settings file and saves one
kind's choice (or a reset to the default order) through ``UserSettings.with_editor``, so the
file's backup and every unknown field are kept. Both calls block; the page runs them on its
worker. A damaged or newer file raises ``SettingsError`` and is never written.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ctstudio.core.project import settings
from ctstudio.core.project.editor_preferences import DEFAULT_EDITORS, parse_preferences

# Only kinds with more than one built-in editor have something to choose.
KINDS: tuple[str, ...] = tuple(kind for kind, tools in DEFAULT_EDITORS.items() if len(tools) > 1)
KIND_LABELS: MappingProxyType[str, str] = MappingProxyType(
    {
        ".brres": "Models and textures (.brres)",
        ".szs": "Track archives (.szs)",
        ".kmp": "Course data (.kmp)",
    }
)


@dataclass(frozen=True)
class EditorKinds:
    """The saved choice for each kind in ``KINDS``; None means the default order."""

    choices: Mapping[str, str | None]


def _choices(loaded: settings.UserSettings) -> EditorKinds:
    preferences = parse_preferences(loaded.other)
    picked = {kind: preferences.get(kind) for kind in KINDS}
    return EditorKinds(
        {kind: tool if isinstance(tool, str) else None for kind, tool in picked.items()}
    )


class EditorPreferencesService:
    def __init__(self, *, settings_path: Path | None = None) -> None:
        self._settings_path = settings_path

    def load(self) -> EditorKinds:
        """The saved choices (blocking); raises ``SettingsError`` for an unusable file."""
        return _choices(settings.load(self._settings_path))

    def save(self, kind: str, tool: str | None) -> EditorKinds:
        """Save ``kind``'s choice, read fresh from the file; nothing is written when the file
        already says so. Raises ``SettingsError`` (file untouched) when it cannot be used."""
        current = settings.load(self._settings_path)
        if _choices(current).choices.get(kind) == tool:
            return _choices(current)
        updated = current.with_editor(kind, tool)
        settings.save(updated, self._settings_path)
        return _choices(updated)
