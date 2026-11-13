"""Pure editor catalogue (no discovery or adapter capability claims)."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

EDITOR_PREFERENCES = "editor_preferences"

DEFAULT_EDITORS: MappingProxyType[str, tuple[str, ...]] = MappingProxyType(
    {
        ".brres": ("brawlcrate", "riistudio"),
        # Catalogue intent only: not a claim that existing adapters accept SZS.
        ".szs": ("brawlcrate", "riistudio"),
        ".kmp": ("kmp_editor_lorenzi", "kmp_cloud"),
        ".blend": ("blender",),
        "folder": ("system",),
    }
)


def validate_editor(kind: str, tool: str | None) -> None:
    """Refuse unsupported kinds and non-exact built-in identifiers."""
    if kind not in DEFAULT_EDITORS:
        raise ValueError(f"unknown editor kind: {kind}")
    if tool is not None and tool not in DEFAULT_EDITORS[kind]:
        raise ValueError(f"unsupported editor for {kind}: {tool!r}")


def parse_preferences(other: Mapping[str, object]) -> dict[str, object]:
    """Copy and validate known preferences; keep future extension fields untouched."""
    if EDITOR_PREFERENCES not in other:
        return {}
    value = other[EDITOR_PREFERENCES]
    if not isinstance(value, dict):
        raise ValueError(f'"{EDITOR_PREFERENCES}" is not a JSON object')
    preferences = cast("dict[str, object]", value)
    for kind, tool in preferences.items():
        if kind in DEFAULT_EDITORS:
            if not isinstance(tool, str):
                raise ValueError(f"invalid editor preference for {kind}: {tool!r}")
            validate_editor(kind, tool)
    return dict(preferences)
