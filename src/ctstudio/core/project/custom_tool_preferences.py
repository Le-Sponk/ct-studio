"""Pure validation of user-defined custom tools in machine settings (P5-T07c1).

``custom_tools`` maps an exact lowercase id to ``{"name", "exe", "args_template"}`` plus
any fields a later version adds. Template rules are ``CustomTool``'s own; nothing here
looks at the filesystem, so a relative or missing executable is kept as plain metadata.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from ctstudio.core.errors import ProjectError
from ctstudio.core.tools.spec import CustomTool

CUSTOM_TOOLS = "custom_tools"
_ID = re.compile(r"[a-z][a-z0-9_-]*")
_FIELDS = ("name", "exe", "args_template")


def check_id(tool_id: object) -> str:
    """Refuse anything but an exact lowercase slug; ids are never normalized."""
    if not isinstance(tool_id, str) or _ID.fullmatch(tool_id) is None:
        raise ValueError(f"invalid custom tool id: {tool_id!r}")
    return tool_id


def _text(value: object, label: str, *, blank: bool) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} is not text: {value!r}")
    if not blank and not value.strip():
        raise ValueError(f"{label} is blank")
    if "\0" in value:
        raise ValueError(f"{label} contains a NUL character")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} is not valid Unicode text: {value!r}") from exc
    return value


def _tool(tool_id: str, record: object) -> CustomTool:
    label = f"custom tool {tool_id!r}"
    if not isinstance(record, dict):
        raise ValueError(f"{label} is not a JSON object")
    fields = cast("dict[str, object]", record)
    missing = [name for name in _FIELDS if name not in fields]
    if missing:
        raise ValueError(f"{label} lacks {', '.join(missing)}")
    name = _text(fields["name"], f"{label} name", blank=False)
    exe = _text(fields["exe"], f"{label} exe", blank=False)
    args = fields["args_template"]
    if not isinstance(args, list):
        raise ValueError(f"{label} args_template is not a JSON list")
    tokens = [_text(token, f"{label} argument", blank=True) for token in cast("list[object]", args)]
    try:
        return CustomTool(name, Path(exe), tokens)
    except ProjectError as exc:
        raise ValueError(f"{label} is invalid: {exc}; {exc.details or ''}") from exc


def _table(other: Mapping[str, object]) -> dict[object, object]:
    if CUSTOM_TOOLS not in other:
        return {}
    value = other[CUSTOM_TOOLS]
    if not isinstance(value, dict):
        raise ValueError(f'"{CUSTOM_TOOLS}" is not a JSON object')
    return dict(cast("dict[object, object]", value))


def parse_custom_tools(other: Mapping[str, object]) -> dict[str, CustomTool]:
    """Validated copies of the recognized custom-tool records; no filesystem access."""
    return {check_id(key): _tool(cast("str", key), rec) for key, rec in _table(other).items()}


def updated_custom_tools(
    other: Mapping[str, object], tool_id: str, tool: CustomTool | None
) -> dict[str, object]:
    """A copy of ``other`` with one record set or removed; unknown fields are kept."""
    check_id(tool_id)
    parse_custom_tools(other)
    table = copy.deepcopy(_table(other))
    if tool is None:
        if tool_id not in table:
            return dict(other)
        del table[tool_id]
    else:
        record = dict(cast("dict[str, object]", table.get(tool_id, {})))
        record.update(name=tool.name, exe=str(tool.exe), args_template=list(tool.args_template))
        _tool(tool_id, record)
        table[tool_id] = record
    return {**other, CUSTOM_TOOLS: table}
