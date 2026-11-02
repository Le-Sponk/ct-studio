"""``.ctstudio/state.json``: what CT Studio last made for each part, and from what (P3-T04).

The build runner records, per generated part, a settings key and the size, mtime and BLAKE2b
digest of every output (under ``.ctstudio/stage/``) and every input it read. Status uses the
record to tell Ready from Stale or EditedExternally. Size+mtime unchanged means unchanged
(no hashing); otherwise a file is hashed once per size+mtime (``fsutil.Fingerprint`` cache).
The file is app-managed and safe to delete: missing or damaged reads as "nothing made yet".
"""

from __future__ import annotations

import json
import logging
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from ctstudio.core import fsutil
from ctstudio.core.errors import ProjectError

GENERATED_DIR = ".ctstudio/stage"
STATE_FILE = ".ctstudio/state.json"
FORMAT = 1
_LOG = logging.getLogger(__name__)

type Change = Literal["same", "changed", "missing"]


@dataclass(frozen=True)
class FileRecord:
    size: int
    mtime_ns: int
    digest: str

    @classmethod
    def of(cls, path: Path) -> FileRecord:
        st = path.stat()
        return cls(st.st_size, st.st_mtime_ns, _digest(path, st.st_size, st.st_mtime_ns))

    def compare(self, path: Path) -> Change:
        """``same`` without hashing when size and mtime match; a touched file is hashed."""
        try:
            st = path.stat()
        except (FileNotFoundError, NotADirectoryError):  # Linux: a parent became a file
            return "missing"
        if not stat.S_ISREG(st.st_mode) or st.st_size != self.size:
            return "changed"
        if st.st_mtime_ns == self.mtime_ns:
            return "same"
        try:
            same = _digest(path, st.st_size, st.st_mtime_ns) == self.digest
        except ProjectError:  # being written (e.g. Blender saving) or gone mid-hash
            return "changed"
        return "same" if same else "changed"


def _digest(path: Path, size: int, mtime_ns: int) -> str:
    return fsutil.Fingerprint(path.resolve(), size, mtime_ns).digest


@dataclass(frozen=True)
class ComponentRecord:
    settings: str  # status.settings_key() when the part was made
    outputs: Mapping[str, FileRecord]  # by path inside .ctstudio/stage/, with "/"
    inputs: Mapping[str, FileRecord]  # by project-relative path with "/", or absolute


@dataclass(frozen=True)
class ProjectState:
    components: Mapping[str, ComponentRecord]


def record(
    root: Path, settings: str, outputs: Iterable[Path], inputs: Iterable[Path]
) -> ComponentRecord:
    """The record of a part just made from ``inputs`` into ``outputs``."""
    stage = (root / GENERATED_DIR).resolve()
    made: dict[str, FileRecord] = {}
    for path in outputs:
        resolved = path.resolve()
        if not resolved.is_relative_to(stage):
            raise ValueError(f"{path} is outside {GENERATED_DIR}")
        made[resolved.relative_to(stage).as_posix()] = FileRecord.of(path)
    used = {input_key(root, path): FileRecord.of(path) for path in inputs}
    return ComponentRecord(settings, made, used)


def input_key(root: Path, path: Path) -> str:
    resolved, base = path.resolve(), root.resolve()
    return resolved.relative_to(base).as_posix() if resolved.is_relative_to(base) else str(resolved)


def input_path(root: Path, key: str) -> Path:
    return root / key  # an absolute key replaces root (pathlib)


def load_state(root: Path) -> ProjectState:
    path = root / STATE_FILE
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return ProjectState({})
    except OSError as exc:
        raise ProjectError(
            "Could not read state.json.",
            hint="Close other programs using the project, or delete .ctstudio/state.json.",
            details=f"path={path}; error={exc}",
        ) from exc
    try:
        return _parse(json.loads(raw.decode("utf-8")))
    except (ValueError, TypeError, KeyError) as exc:  # UnicodeDecodeError is a ValueError
        _LOG.warning("state.json is damaged (%s); starting fresh", exc)
        return ProjectState({})


def save_state(root: Path, state: ProjectState) -> None:
    data = {
        "format": FORMAT,
        "components": {
            name: {
                "settings": rec.settings,
                "outputs": {k: vars(v) for k, v in rec.outputs.items()},
                "inputs": {k: vars(v) for k, v in rec.inputs.items()},
            }
            for name, rec in state.components.items()
        },
    }
    fsutil.atomic_write_text(root / STATE_FILE, json.dumps(data, indent=2, sort_keys=True) + "\n")


def _parse(data: object) -> ProjectState:
    top = _object(data)
    if top["format"] != FORMAT:
        raise ValueError(f"format {top['format']!r}, expected {FORMAT}")
    parts = _object(top["components"])
    return ProjectState({name: _component(entry) for name, entry in parts.items()})


def _component(data: object) -> ComponentRecord:
    entry = _object(data)
    settings = entry["settings"]
    if not isinstance(settings, str):
        raise TypeError("settings is not text")
    files = {
        k: {name: _file(v) for name, v in _object(entry[k]).items()} for k in ("outputs", "inputs")
    }
    return ComponentRecord(settings, files["outputs"], files["inputs"])


def _file(data: object) -> FileRecord:
    entry = _object(data)
    size, mtime_ns, digest = entry["size"], entry["mtime_ns"], entry["digest"]
    numbers = all(type(n) is int for n in (size, mtime_ns))
    if not numbers or not isinstance(digest, str):
        raise TypeError(f"bad file record {entry!r}")
    return FileRecord(cast("int", size), cast("int", mtime_ns), digest)


def _object(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise TypeError(f"expected an object, found {type(data).__name__}")
    return cast("dict[str, object]", data)
