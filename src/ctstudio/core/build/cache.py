"""``.ctstudio/cache.json``: which build steps can be skipped (ARCHITECTURE §7, ADR-006).

``check`` gives a step's key, a BLAKE2b hash over its settings, ``impl_version``, the versions
of the tools it starts and the content of every file it reads (a folder counts as every file
in it, by name; a missing input counts as missing). The step is *fresh* when the key equals
the one stored after its last run and exactly the files it wrote then are there, unchanged.
Size+mtime unchanged means unchanged, so checking an untouched project hashes nothing; a
touched file is hashed once and its new mtime recorded.

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
from pathlib import Path

from ctstudio.core import fsutil
from ctstudio.core.build.node import Node
from ctstudio.core.components.state import FileRecord, input_key, parse_file, parse_object
from ctstudio.core.errors import BuildError, ProjectError

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


@dataclass(frozen=True)
class _Entry:
    key: str
    inputs: Records
    outputs: Records


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
            return cls(root, _parse(json.loads(raw.decode("utf-8"))))
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
        fresh = entry is not None and self._fresh(node, entry, _Entry(key, inputs, {}))
        return Lookup(node.id, key, fresh, inputs)

    def store(self, node: Node, lookup: Lookup) -> None:
        """Record a step that just ran, so the next ``check`` with the same key is fresh."""
        if lookup.node_id != node.id:
            raise ValueError(f"{node.id}: this lookup is for {lookup.node_id}")
        absent = [path for path in node.outputs if not path.exists()]
        if absent:
            self.invalidate(node.id)
            names = ", ".join(input_key(self.root, path) for path in absent)
            raise BuildError(node.id, f"it did not write {names}")
        made = self._records(_expand(node.outputs), {})
        with self._lock:
            self._entries[node.id] = _Entry(lookup.key, lookup.inputs, made)
            self._changed = True

    def invalidate(self, node_id: str) -> None:
        with self._lock:
            if self._entries.pop(node_id, None) is not None:
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
            text = json.dumps(_dump(self._entries), indent=2, sort_keys=True) + "\n"
            fsutil.atomic_write_text(self.root / CACHE_FILE, text)
            self._changed = False

    def _input(self, path: Path, known: Records, seen: dict[str, FileRecord]) -> object:
        """What the key holds for one declared input: a digest, a folder's digests, or None."""
        if path.is_dir():
            files = _files(path)
            records = self._records(files, known)
            seen.update(records)
            return {f.relative_to(path).as_posix(): records[self._key(f)].digest for f in files}
        if not path.is_file():  # not path.exists() would hash a pipe or device and hang
            return None
        record = self._records([path], known)
        seen.update(record)
        return next(iter(record.values())).digest

    def _fresh(self, node: Node, entry: _Entry, now: _Entry) -> bool:
        """Same key and outputs; then records the new mtimes of touched but unchanged files."""
        if entry.key != now.key or not all(path.exists() for path in node.outputs):
            return False
        files = _expand(node.outputs)
        if {self._key(path) for path in files} != set(entry.outputs):
            return False
        outputs = self._records(files, entry.outputs)
        if any(outputs[k].digest != entry.outputs[k].digest for k in outputs):
            return False
        with self._lock:
            new = _Entry(now.key, now.inputs, outputs)
            if new != entry and self._entries.get(node.id) is entry:
                self._entries[node.id] = new
                self._changed = True
        return True

    def _key(self, path: Path) -> str:
        return input_key(self.root, path)

    def _records(self, files: Iterable[Path], known: Records) -> dict[str, FileRecord]:
        return {self._key(path): _record(path, known.get(self._key(path))) for path in files}


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
    now = fsutil.Fingerprint.from_path(path)
    if old is not None and (now.size, now.mtime_ns) == (old.size, old.mtime_ns):
        return old
    return FileRecord(now.size, now.mtime_ns, now.digest)


def _dump(entries: Mapping[str, _Entry]) -> dict[str, object]:
    nodes = {
        node_id: {
            "key": entry.key,
            "inputs": {k: vars(v) for k, v in entry.inputs.items()},
            "outputs": {k: vars(v) for k, v in entry.outputs.items()},
        }
        for node_id, entry in entries.items()
    }
    return {"format": FORMAT, "nodes": nodes}


def _parse(data: object) -> dict[str, _Entry]:
    top = parse_object(data)
    if top["format"] != FORMAT:
        raise ValueError(f"format {top['format']!r}, expected {FORMAT}")
    return {node_id: _entry(value) for node_id, value in parse_object(top["nodes"]).items()}


def _entry(data: object) -> _Entry:
    entry = parse_object(data)
    key = entry["key"]
    if not isinstance(key, str):
        raise TypeError("key is not text")
    files = {
        part: {name: parse_file(v) for name, v in parse_object(entry[part]).items()}
        for part in ("inputs", "outputs")
    }
    return _Entry(key, files["inputs"], files["outputs"])
