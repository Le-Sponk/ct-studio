"""A JSON Schema checker for the few keywords CT Studio's documented schemas use.

``jsonschema`` is not a dependency (AGENTS.md rule 5), and the schemas in ``docs/dev`` keep
to: ``type`` (one or a list), ``enum``, ``const``, ``required``, ``properties``,
``additionalProperties: false``, ``items``, ``minimum``, ``oneOf`` and local ``$ref``. Any
other keyword is refused, so a schema edit cannot silently stop being checked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

KNOWN = {
    "$schema",
    "title",
    "$defs",
    "type",
    "enum",
    "const",
    "required",
    "properties",
    "additionalProperties",
    "items",
    "minimum",
    "oneOf",
    "$ref",
}
_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "null": (type(None),),
}


def schema_from_doc(doc: Path, marker: str) -> dict[str, Any]:
    """The ```json block right after ``<!-- marker -->`` in ``doc``."""
    text = doc.read_text(encoding="utf-8")
    found = re.search(rf"<!-- {re.escape(marker)} -->\s*```json\n(.*?)\n```", text, re.S)
    if found is None:
        raise ValueError(f"no schema after <!-- {marker} --> in {doc.name}")
    return cast("dict[str, Any]", json.loads(found.group(1)))


def errors(value: object, schema: dict[str, Any], root: dict[str, Any] | None = None) -> list[str]:
    """Every way ``value`` breaks ``schema`` (empty when it matches)."""
    top = root if root is not None else schema
    unknown = set(schema) - KNOWN
    if unknown:
        raise ValueError(f"schema keyword(s) this checker does not know: {sorted(unknown)}")
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/$defs/")
        return errors(value, top["$defs"][name], top)
    if "oneOf" in schema:
        matches = [s for s in schema["oneOf"] if not errors(value, s, top)]
        return [] if len(matches) == 1 else [f"matches {len(matches)} of oneOf, not 1"]
    return [*_scalar(value, schema), *_compound(value, schema, top)]


def _is(value: object, name: str) -> bool:
    if isinstance(value, bool) and name in ("number", "integer"):
        return False
    return isinstance(value, _TYPES[name])


def _scalar(value: object, schema: dict[str, Any]) -> list[str]:
    found: list[str] = []
    kinds = schema.get("type")
    if kinds is not None:
        names = kinds if isinstance(kinds, list) else [kinds]
        if not any(_is(value, name) for name in names):
            found.append(f"{value!r} is not {kinds}")
    if "const" in schema and value != schema["const"]:
        found.append(f"{value!r} is not {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{value!r} is not one of {schema['enum']}")
    if "minimum" in schema and _is(value, "number") and cast(float, value) < schema["minimum"]:
        found.append(f"{value!r} is below {schema['minimum']}")
    return found


def _compound(value: object, schema: dict[str, Any], top: dict[str, Any]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        data = cast("dict[str, object]", value)
        props: dict[str, Any] = schema.get("properties", {})
        found += [f"missing {key!r}" for key in schema.get("required", []) if key not in data]
        if schema.get("additionalProperties") is False:
            found += [f"unexpected {key!r}" for key in data if key not in props]
        for key, sub in props.items():
            if key in data:
                found += [f"{key}: {e}" for e in errors(data[key], sub, top)]
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(cast("list[object]", value)):
            found += [f"[{i}]: {e}" for e in errors(item, schema["items"], top)]
    return found
