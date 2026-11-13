"""The user's machine settings: ``settings.json`` in the user config folder (P2-T07a).

Machine-specific choices (for now, tool paths set in CT Studio) live here and never in a
project (ARCHITECTURE §6). The file is the user's: a damaged or newer one is reported and
never overwritten by a load, keys CT Studio does not know survive a save, and each save
keeps a backup of the previous file (``fsutil.replace_with_backup``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from ctstudio.core import platform as ct_platform
from ctstudio.core.errors import ProjectError
from ctstudio.core.fsutil import replace_with_backup
from ctstudio.core.project.editor_preferences import (
    DEFAULT_EDITORS,
    EDITOR_PREFERENCES,
    parse_preferences,
    validate_editor,
)
from ctstudio.core.tools.registry import TOOL_BY_ID

FORMAT = 1
FILE_NAME = "settings.json"
AUTO_ADD_LIBRARY = "auto_add_library"  # folder built by `wszst autoadd` from the own disc


class SettingsError(ProjectError):
    """The settings file exists but cannot be used; it is left as it is."""

    def __init__(self, path: Path, reason: str, details: str | None = None) -> None:
        self.path = path
        super().__init__(
            f"CT Studio's settings file {path} cannot be used: {reason}.",
            hint="Fix or delete that file; CT Studio will not overwrite it.",
            details=details,
        )


@dataclass(frozen=True)
class UserSettings:
    """Tool id → path set by the user, plus every other key the file had (kept as-is)."""

    tools: Mapping[str, str] = field(default_factory=lambda: {})
    other: Mapping[str, object] = field(default_factory=lambda: {})

    def editor_order(self, kind: str) -> tuple[str, ...]:
        """Pure ordered built-ins, preferred first; not tool discovery or dispatch."""
        preferences = parse_preferences(self.other)
        defaults = DEFAULT_EDITORS.get(kind, ())
        preferred = preferences.get(kind)
        if kind in DEFAULT_EDITORS and isinstance(preferred, str):
            return (preferred, *(tool for tool in defaults if tool != preferred))
        return defaults

    def with_editor(self, kind: str, tool: str | None) -> UserSettings:
        """Copy with an exact built-in preference, or reset this known kind."""
        validate_editor(kind, tool)
        preferences = parse_preferences(self.other)
        preferences.pop(kind, None)
        if tool is not None:
            preferences[kind] = tool
        other = dict(self.other)
        if preferences or EDITOR_PREFERENCES in other:
            other[EDITOR_PREFERENCES] = preferences
        return UserSettings(self.tools, other)

    def configured(self) -> dict[str, Path]:
        """The set paths of tools this version knows, for discovery and doctor."""
        return {tool: Path(path) for tool, path in self.tools.items() if tool in TOOL_BY_ID}

    def auto_add_library(self) -> Path | None:
        """The auto-add library folder chosen on this computer (P4-T05b), if any."""
        value = self.other.get(AUTO_ADD_LIBRARY)
        return Path(value) if isinstance(value, str) and value else None

    def with_auto_add_library(self, path: Path | None) -> UserSettings:
        other = {key: value for key, value in self.other.items() if key != AUTO_ADD_LIBRARY}
        if path is not None:
            other[AUTO_ADD_LIBRARY] = str(path)
        return UserSettings(self.tools, other)

    def with_tool(self, tool_id: str, path: Path | None) -> UserSettings:
        """A copy with ``tool_id`` set to ``path``, or cleared when ``path`` is None."""
        if tool_id not in TOOL_BY_ID:
            raise ValueError(f"unknown tool id: {tool_id}")
        tools = {key: value for key, value in self.tools.items() if key != tool_id}
        if path is not None:
            tools[tool_id] = str(path)
        return UserSettings(tools, self.other)


def default_path() -> Path:
    return ct_platform.user_directories().config / FILE_NAME


def load(path: Path | None = None) -> UserSettings:
    """The saved settings; nothing set when there is no file. Never writes."""
    target = path if path is not None else default_path()
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return UserSettings()
    except (OSError, UnicodeDecodeError) as exc:
        raise SettingsError(target, "it cannot be read", details=str(exc)) from exc
    try:
        data: object = json.loads(text)
    except ValueError as exc:
        raise SettingsError(target, "it is not valid JSON", details=str(exc)) from exc
    return _parse(target, data)


def _parse(target: Path, data: object) -> UserSettings:
    if not isinstance(data, dict):
        raise SettingsError(target, "it is not a JSON object")
    fields = cast("dict[str, object]", data)
    _check_format(target, fields.get("format", FORMAT))
    other = {key: value for key, value in fields.items() if key not in ("format", "tools")}
    _check_preferences(target, other)
    library = other.get(AUTO_ADD_LIBRARY)
    if library is not None and (not isinstance(library, str) or not library):
        raise SettingsError(target, f'"{AUTO_ADD_LIBRARY}" is not a folder path')
    return UserSettings(_tool_paths(target, fields.get("tools", {})), other)


def _check_preferences(target: Path, other: Mapping[str, object]) -> None:
    try:
        parse_preferences(other)
    except ValueError as exc:
        raise SettingsError(target, "editor preferences are invalid", details=str(exc)) from exc


def _check_format(target: Path, version: object) -> None:
    if not isinstance(version, int) or isinstance(version, bool):
        raise SettingsError(target, '"format" is not a number')
    if version > FORMAT:
        raise SettingsError(target, "it was written by a newer version of CT Studio")


def _tool_paths(target: Path, tools: object) -> dict[str, str]:
    if not isinstance(tools, dict):
        raise SettingsError(target, '"tools" is not a JSON object')
    paths = cast("dict[str, object]", tools)
    for tool, value in paths.items():
        if not isinstance(value, str) or not value:
            raise SettingsError(target, f'the path for "{tool}" is not a file path')
    return cast("dict[str, str]", paths)


def save(settings: UserSettings, path: Path | None = None) -> None:
    """Write the settings, keeping a backup of the file they replace."""
    target = path if path is not None else default_path()
    _check_preferences(target, settings.other)
    data = {"format": FORMAT, **settings.other, "tools": dict(settings.tools)}
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    replace_with_backup(target, text.encode("utf-8"))
