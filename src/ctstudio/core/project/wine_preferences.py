"""Pure validation of per-editor Wine-prefix choices in machine settings (P5-T07c2).

``wine_prefixes`` maps an exact lowercase editor id (built-in, custom or later) to
``{"prefix": text}`` plus any fields a later version adds. The prefix is metadata only:
nothing here looks at the filesystem, so a relative or missing folder is kept as written
and Wine checks it when an adapter dispatches.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from ctstudio.core.project.custom_tool_preferences import check_id

WINE_PREFIXES = "wine_prefixes"
PREFIX = "prefix"


def _check_prefix(editor_id: str, value: object) -> str:
    label = f"Wine prefix for {editor_id!r}"
    if not isinstance(value, str):
        raise ValueError(f"{label} is not text: {value!r}")
    if not value.strip():
        raise ValueError(f"{label} is blank")
    if "\0" in value:
        raise ValueError(f"{label} contains a NUL character")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} is not valid Unicode text: {value!r}") from exc
    return value


def _check_editor(editor_id: object) -> str:
    try:
        return check_id(editor_id)
    except ValueError:
        raise ValueError(f"invalid Wine-prefix editor id: {editor_id!r}") from None


def _record(editor_id: object, record: object) -> tuple[str, str]:
    key = _check_editor(editor_id)
    if not isinstance(record, dict):
        raise ValueError(f"Wine-prefix record for {key!r} is not a JSON object")
    fields = cast("dict[str, object]", record)
    if PREFIX not in fields:
        raise ValueError(f"Wine-prefix record for {key!r} lacks {PREFIX}")
    return key, _check_prefix(key, fields[PREFIX])


def _table(other: Mapping[str, object]) -> dict[object, object]:
    if WINE_PREFIXES not in other:
        return {}
    value = other[WINE_PREFIXES]
    if not isinstance(value, dict):
        raise ValueError(f'"{WINE_PREFIXES}" is not a JSON object')
    return dict(cast("dict[object, object]", value))


def parse_wine_prefixes(other: Mapping[str, object]) -> dict[str, Path]:
    """Validated copies of every recognized prefix choice; no filesystem access."""
    return {key: Path(text) for key, text in (_record(*item) for item in _table(other).items())}


def updated_wine_prefixes(
    other: Mapping[str, object], editor_id: str, prefix: Path | None
) -> dict[str, object]:
    """A copy of ``other`` with one choice set or removed; unknown fields are kept."""
    _check_editor(editor_id)
    parse_wine_prefixes(other)
    table = copy.deepcopy(_table(other))
    if prefix is None:
        if editor_id not in table:
            return dict(other)
        del table[editor_id]
    else:
        record = dict(cast("dict[str, object]", table.get(editor_id, {})))
        record[PREFIX] = _check_prefix(editor_id, str(prefix))
        table[editor_id] = record
    return {**other, WINE_PREFIXES: table}
