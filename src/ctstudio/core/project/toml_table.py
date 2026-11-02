"""Read one TOML table with errors that name the full key path (P3-T01, for ``manifest_io``).

``Table`` wraps the raw ``tomllib`` data of a table and its path (``components.kmp``). Each
reader method takes a key and a default, checks the value, and raises ``ManifestError`` with
the key path and, in plain words, what is allowed and what was found. Keys that no method
asked for are this version's unknown keys: ``rest()`` returns them (to keep on save) and
records their paths in the shared ``unknown`` list (to warn about once).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

from ctstudio.core.errors import ManifestError

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_SHOW_AT_MOST = 40


def key_path(parent: str, key: str) -> str:
    """``parent.key`` in TOML spelling: keys that are not bare get double quotes."""
    part = key if _BARE_KEY.fullmatch(key) else f'"{key}"'
    return f"{parent}.{part}" if parent else part


def show(value: object) -> str:
    """A found value as it would look in the file, long text shortened."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        text = value if len(value) <= _SHOW_AT_MOST else value[:_SHOW_AT_MOST] + "…"
        return f'"{text}"'
    if isinstance(value, list):
        return "[" + ", ".join(show(item) for item in cast("list[object]", value)) + "]"
    if isinstance(value, dict):
        return "a table"
    return str(value)


def _is_text_list(value: object) -> bool:
    if not isinstance(value, list):
        return False
    return all(isinstance(item, str) for item in cast("list[object]", value))


def _choices(options: tuple[str, ...]) -> str:
    return ", ".join(f'"{option}"' for option in options)


class Table:
    def __init__(self, data: Mapping[str, object], path: str, unknown: list[str]) -> None:
        self.data = data
        self.path = path
        self.unknown = unknown
        self._used: set[str] = set()

    def _value(self, key: str) -> object:
        self._used.add(key)
        return self.data.get(key)

    def known(self, key: str) -> None:
        """Mark ``key`` as understood although no reader method checked it here."""
        self._used.add(key)

    def fail(self, key: str, reason: str) -> ManifestError:
        return ManifestError(key_path(self.path, key), reason)

    def _wrong(self, key: str, expected: str, found: object) -> ManifestError:
        return self.fail(key, f"expected {expected}; found {show(found)}")

    def text(self, key: str, default: str, *, empty_ok: bool = True) -> str:
        value = self._value(key)
        if value is None:
            return default
        if not isinstance(value, str):
            raise self._wrong(key, "text in quotes", value)
        if not value and not empty_ok:
            raise self._wrong(key, "some text", value)
        return value

    def optional_text(self, key: str) -> str | None:
        """Absent → ``None``; present → non-empty text (an empty path means nothing)."""
        if key not in self.data:
            return None
        return self.text(key, "", empty_ok=False)

    def choice[T: str](self, key: str, options: tuple[T, ...], default: T) -> T:
        found = self.optional_choice(key, options)
        return default if found is None else found

    def optional_choice[T: str](self, key: str, options: tuple[T, ...]) -> T | None:
        value = self._value(key)
        if value is None:
            return None
        for option in options:
            if value == option:
                return option
        raise self._wrong(key, f"one of {_choices(options)}", value)

    def member(self, key: str, allowed: tuple[str, ...], default: str, expected: str) -> str:
        value = self.text(key, default)
        if value not in allowed:
            raise self._wrong(key, expected, value)
        return value

    def flag(self, key: str, default: bool) -> bool:
        value = self._value(key)
        if value is None:
            return default
        if not isinstance(value, bool):
            raise self._wrong(key, "true or false", value)
        return value

    def texts(self, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        value = self._value(key)
        if value is None:
            return default
        if not _is_text_list(value):
            raise self._wrong(key, 'a list of text, such as ["--a", "--b"]', value)
        return tuple(cast("list[str]", value))

    def whole(self, key: str, low: int, high: int) -> int | None:
        value = self._value(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise self._wrong(key, f"a whole number from {low} to {high}", value)
        return value

    def table(self, key: str) -> Table:
        value = self._value(key)
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise self._wrong(key, "a table", value)
        child = cast("dict[str, object]", value)
        return Table(child, key_path(self.path, key), self.unknown)

    def named(self, key: str) -> dict[str, Table]:
        """A table of user-named entries (``textures."road.png"``), each itself a table."""
        value = self._value(key)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise self._wrong(key, "a table of named entries", value)
        entries = Table(cast("dict[str, object]", value), key_path(self.path, key), self.unknown)
        return {name: entries.table(name) for name in entries.data}

    def rest(self) -> dict[str, object]:
        """The keys nobody read: kept as they are, and noted as unknown."""
        extra = {key: value for key, value in self.data.items() if key not in self._used}
        self.unknown.extend(key_path(self.path, key) for key in extra)
        return extra
