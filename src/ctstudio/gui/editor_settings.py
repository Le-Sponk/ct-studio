"""Editor choices for Settings → Editors…: the built-in order per file kind (P5-T07f1),
the user's own editor programs (P5-T07f2) and each Windows editor's Wine prefix (P5-T07f3).

A plain service: it reads the user's settings file and saves one change at a time through
``UserSettings.with_editor``, ``with_custom_tool`` or ``with_wine_prefix``, so the file's
backup and every unknown field (also inside a custom-tool or prefix record) are kept. Every
call blocks; the page runs them on its worker. A damaged or newer file raises
``SettingsError`` and is never written.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from ctstudio.core.project import settings
from ctstudio.core.project.editor_preferences import DEFAULT_EDITORS, parse_preferences
from ctstudio.core.tools.editors import PREFIX_RECIPES
from ctstudio.core.tools.spec import CustomTool

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
    """The saved choice for each kind in ``KINDS`` (None means the default order), the
    user's own editor programs by id, and the saved Wine prefixes by editor id."""

    choices: Mapping[str, str | None]
    custom: Mapping[str, CustomTool] = field(default_factory=dict[str, CustomTool])
    prefixes: Mapping[str, Path] = field(default_factory=dict[str, Path])


def _choices(loaded: settings.UserSettings) -> EditorKinds:
    preferences = parse_preferences(loaded.other)
    picked = {kind: preferences.get(kind) for kind in KINDS}
    return EditorKinds(
        {kind: tool if isinstance(tool, str) else None for kind, tool in picked.items()},
        loaded.custom_tools(),
        loaded.wine_prefixes(),
    )


def fresh_id(name: str, taken: Collection[str]) -> str:
    """A new custom-tool id from ``name`` that is not in ``taken`` (``custom-`` keeps it
    apart from built-in ids; a number is added when needed)."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:40].strip("-") or "tool"
    base = tool_id = f"custom-{slug}"
    number = 2
    while tool_id in taken:
        tool_id = f"{base}-{number}"
        number += 1
    return tool_id


class EditorGone(Exception):
    """The edited editor was removed outside this window; nothing was saved."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"{name} was removed outside this window, so the change was not saved. "
            "Close and reopen Settings → Editors… to see the current list."
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

    def save_custom(self, tool_id: str | None, tool: CustomTool | None) -> EditorKinds:
        """Add (``tool_id`` None: a fresh id), replace, or remove (``tool`` None) one custom
        tool, read fresh from the file; nothing is written when the file already says so. A
        new id never reuses a custom or Wine-prefix id, so an old prefix setting never
        attaches itself to a new program (built-in ids never start with ``custom-``)."""
        current = settings.load(self._settings_path)
        tools = current.custom_tools()
        if tool_id is None:
            if tool is None:
                raise ValueError("there is no custom tool to add")
            tool_id = fresh_id(tool.name, {*tools, *current.wine_prefixes()})
        elif tools.get(tool_id) == tool:
            return _choices(current)
        elif tool_id not in tools:
            raise EditorGone(tool.name if tool else tool_id)
        updated = current.with_custom_tool(tool_id, tool)
        settings.save(updated, self._settings_path)
        return _choices(updated)

    def save_prefix(self, editor_id: str, prefix: Path | None, *, name: str) -> EditorKinds:
        """Set (or clear, ``prefix`` None) one editor's Wine prefix, read fresh from the
        file; nothing is written when the file already says so. ``name`` names a custom
        editor that was removed outside meanwhile (``EditorGone``: no orphan prefix)."""
        current = settings.load(self._settings_path)
        if current.wine_prefixes().get(editor_id) == prefix:
            return _choices(current)
        if prefix is not None and editor_id not in PREFIX_RECIPES:
            if editor_id not in current.custom_tools():
                raise EditorGone(name)
        updated = current.with_wine_prefix(editor_id, prefix)
        settings.save(updated, self._settings_path)
        return _choices(updated)
