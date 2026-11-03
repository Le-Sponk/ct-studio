"""``.ctstudio/cache.json``: which build steps can be skipped (ARCHITECTURE §7, ADR-006).

``check`` gives a step's key, a BLAKE2b hash over its settings, ``impl_version``, the versions
of the tools it starts and the name and content of every file it reads (a folder counts as
every file in it, by name; a missing input counts as missing). The name counts, so the same
bytes read from another file (a new slot) are a miss. The step is *fresh* when the key equals
the one stored after its last run and exactly the files it wrote then are there, unchanged.
Size+mtime unchanged means unchanged, so checking an untouched project hashes nothing; a
touched file is hashed once and its new mtime recorded. ``Lookup.edited`` names the files the
step wrote last time that were changed since (by hand), so they can be backed up first; a
forgotten step (``invalidate``, ``--force``) still knows what it wrote.

The file is app-managed and safe to delete: missing or damaged reads as "nothing cached".
One cache may be shared by steps running in parallel.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import cast

from ctstudio.core import fsutil
from ctstudio.core.build.node import Node
from ctstudio.core.components.state import (
    FileRecord,
    input_key,
    parse_file,
    parse_object,
    resolved_key,
)
from ctstudio.core.errors import BuildError, ProjectError
from ctstudio.core.validation.issues import Issue, issue_from_json, issue_to_json

CACHE_FILE = ".ctstudio/cache.json"
FORMAT = 1
_LOG = logging.getLogger(__name__)

type Records = Mapping[str, FileRecord]  # by project-relative path with "/", or absolute


@dataclass(frozen=True)
class Lookup:
    node_id: str
    key: str
    fresh: bool
    inputs: Records  # the input files as they were when the key was made
    issues: tuple[Issue, ...] = ()  # when fresh: what the step found when it last ran
    edited: tuple[Path, ...] = ()  # files it wrote last time, changed since (not missing ones)


@dataclass(frozen=True)
class _Entry:
    key: str
    inputs: Records
    outputs: Records
    issues: tuple[Issue, ...] = ()  # absent in files from before P4-T06: none


class BuildCache:
    def __init__(self, root: Path, entries: dict[str, _Entry]) -> None:
        self.root = root
        self._entries = entries
        self._changed = False
        self._lock = threading.Lock()

    @classmethod
    def load(cls, root: Path) -> BuildCache:
        path = root / CACHE_FILE
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return cls(root, {})
        except OSError as exc:
            raise ProjectError(
                "Could not read cache.json.",
                hint="Close other programs using the project, or delete .ctstudio/cache.json.",
                details=f"path={path}; error={exc}",
            ) from exc
        try:
            return cls(root, _parse(json.loads(raw.decode("utf-8")), root))
        except (ValueError, TypeError, KeyError) as exc:  # UnicodeDecodeError is a ValueError
            _LOG.warning("cache.json is damaged (%s); starting fresh", exc)
            return cls(root, {})

    def check(self, node: Node, tool_versions: Mapping[str, str | None]) -> Lookup:
        with self._lock:
            entry = self._entries.get(node.id)
        known: Records = entry.inputs if entry else {}
        inputs: dict[str, FileRecord] = {}
        material = {
            "params": dict(node.params),
            "impl_version": node.impl_version,
            "tools": _versions(node, tool_versions),
            "inputs": [self._input(path, known, inputs) for path in node.inputs],
        }
        text = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        key = hashlib.blake2b(text.encode("utf-8")).hexdigest()
        if entry is None:
            return Lookup(node.id, key, False, inputs)
        outputs, edited = self._outputs(node, entry)
        if entry.key == key and not edited and self._complete(node, entry, outputs):
            self._refresh(node.id, entry, _Entry(key, inputs, outputs, entry.issues))
            return Lookup(node.id, key, True, inputs, entry.issues)
        return Lookup(node.id, key, False, inputs, (), edited)

    def store(self, node: Node, lookup: Lookup, issues: tuple[Issue, ...] = ()) -> None:
        """Record a step that just ran and what it found, so the same key is fresh next time."""
        if lookup.node_id != node.id:
            raise ValueError(f"{node.id}: this lookup is for {lookup.node_id}")
        absent = [path for path in node.outputs if not path.exists()]
        if absent:
            with self._lock:  # what it wrote is unknown now: forget the step entirely
                self._changed = self._entries.pop(node.id, None) is not None or self._changed
            names = ", ".join(input_key(self.root, path) for path in absent)
            raise BuildError(node.id, f"it did not write {names}")
        made = self._records(self._keyed(_expand(node.outputs)), {})
        with self._lock:
            self._entries[node.id] = _Entry(lookup.key, lookup.inputs, made, issues)
            self._changed = True

    def invalidate(self, node_id: str) -> None:
        """The step runs next time; what it wrote stays known, so hand edits are still seen."""
        with self._lock:
            entry = self._entries.get(node_id)
            if entry is not None and entry.key:
                self._entries[node_id] = _Entry("", entry.inputs, entry.outputs)
                self._changed = True

    def clear(self) -> None:
        with self._lock:
            self._changed = self._changed or bool(self._entries)
            self._entries.clear()

    def save(self) -> None:
        """Write cache.json atomically when something changed since it was loaded or saved."""
        with self._lock:
            if not self._changed:
                return
            data = _dump(self._entries, self.root)
            text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            fsutil.atomic_write_text(self.root / CACHE_FILE, text)
            self._changed = False

    def _input(self, path: Path, known: Records, seen: dict[str, FileRecord]) -> object:
        """What the key holds for one declared input: its name, then its digest, every digest
        in it (a folder) or None (missing); the name is resolved once, with the files."""
        if path.is_dir():
            files = _files(path)
            keyed = self._keyed(files)
            records = self._records(keyed, known)
            seen.update(records)
            digests = {
                f.relative_to(path).as_posix(): records[key].digest
                for f, (key, _) in zip(files, keyed, strict=True)
            }
            # One resolve for each file, not another resolve for a folder of 1,000 files.
            return [resolved_key(path, self._base), digests]
        if not path.is_file():  # not path.exists() would hash a pipe or device and hang
            return [input_key(self.root, path), None]
        [(name, resolved)] = self._keyed([path])
        record = self._records([(name, resolved)], known)
        seen.update(record)
        return [name, record[name].digest]

    def _outputs(self, node: Node, entry: _Entry) -> tuple[dict[str, FileRecord], tuple[Path, ...]]:
        """The step's output files now, by key, and those that differ from what it wrote."""
        files = _expand(path for path in node.outputs if path.exists())
        keyed = self._keyed(files)
        records = self._records(keyed, entry.outputs)
        edited = tuple(
            file
            for file, (key, _) in zip(files, keyed, strict=True)
            if key in entry.outputs and records[key].digest != entry.outputs[key].digest
        )
        return records, edited

    @staticmethod
    def _complete(node: Node, entry: _Entry, outputs: Records) -> bool:
        """Exactly the files the step wrote last time are there."""
        return all(path.exists() for path in node.outputs) and set(outputs) == set(entry.outputs)

    def _refresh(self, node_id: str, entry: _Entry, new: _Entry) -> None:
        """Record the new mtimes of touched but unchanged files (no rehash next time)."""
        with self._lock:
            if new != entry and self._entries.get(node_id) is entry:
                self._entries[node_id] = new
                self._changed = True

    @cached_property
    def _base(self) -> Path:
        return self.root.resolve()

    def _keyed(self, files: Iterable[Path]) -> list[tuple[str, Path]]:
        """Each file's key and resolved path, resolving it once (slow on Windows: P4-T08)."""
        keyed: list[tuple[str, Path]] = []
        for path in files:
            resolved = path.resolve()
            keyed.append((resolved_key(resolved, self._base), resolved))
        return keyed

    def _records(self, keyed: Iterable[tuple[str, Path]], known: Records) -> dict[str, FileRecord]:
        return {key: _record(path, known.get(key)) for key, path in keyed}


def _versions(node: Node, given: Mapping[str, str | None]) -> dict[str, str | None]:
    missing = [tool for tool in node.tools if tool not in given]
    if missing:
        raise ValueError(f"{node.id}: no version given for {', '.join(missing)}")
    return {tool: given[tool] for tool in node.tools}


def _files(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*") if path.is_file())


def _expand(paths: Iterable[Path]) -> list[Path]:
    """Files as themselves and folders as every file in them."""
    files: list[Path] = []
    for path in paths:
        files.extend(_files(path) if path.is_dir() else [path])
    return files


def _record(path: Path, old: FileRecord | None) -> FileRecord:
    """``old`` when size and mtime match it (no hashing), else a freshly hashed record."""
    now = fsutil.Fingerprint.from_path(path, resolved=True)
    if old is not None and (now.size, now.mtime_ns) == (old.size, old.mtime_ns):
        return old
    return FileRecord(now.size, now.mtime_ns, now.digest)


def _dump(entries: Mapping[str, _Entry], root: Path) -> dict[str, object]:
    nodes = {
        node_id: {
            "key": entry.key,
            "inputs": {k: vars(v) for k, v in entry.inputs.items()},
            "outputs": {k: vars(v) for k, v in entry.outputs.items()},
            "issues": [issue_to_json(issue, root) for issue in entry.issues],
        }
        for node_id, entry in entries.items()
    }
    return {"format": FORMAT, "nodes": nodes}


def _parse(data: object, root: Path) -> dict[str, _Entry]:
    top = parse_object(data)
    if top["format"] != FORMAT:
        raise ValueError(f"format {top['format']!r}, expected {FORMAT}")
    return {node_id: _entry(value, root) for node_id, value in parse_object(top["nodes"]).items()}


def _entry(data: object, root: Path) -> _Entry:
    entry = parse_object(data)
    key = entry["key"]
    if not isinstance(key, str):
        raise TypeError("key is not text")
    files = {
        part: {name: parse_file(v) for name, v in parse_object(entry[part]).items()}
        for part in ("inputs", "outputs")
    }
    issues = entry.get("issues", [])
    if not isinstance(issues, list):
        raise TypeError("issues is not a list")
    found = tuple(issue_from_json(item, root) for item in cast("list[object]", issues))
    return _Entry(key, files["inputs"], files["outputs"], found)
