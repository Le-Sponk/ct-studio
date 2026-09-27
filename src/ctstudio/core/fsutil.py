"""Atomic app-managed writes, backed-up user writes and cached content fingerprints."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from ctstudio.core.errors import ProjectError

_CHUNK_SIZE = 1024 * 1024
_replace_lock = threading.RLock()  # Windows rename needs serialized in-process writers.


def ensure_inside(root: Path, path: Path) -> Path:
    """Resolve symlinks and reject paths outside root; callers must guard later TOCTOU."""
    try:
        root = root.resolve()
        path = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise ProjectError(
            "Could not resolve project path.",
            hint="Check the path for broken or looping symlinks, then try again.",
            details=str(exc),
        ) from exc
    if not path.is_relative_to(root):
        raise ProjectError(
            "Path is outside the project folder.",
            hint="Select a path inside the project or explicitly mark it external.",
            details=f"root={root}; path={path}",
        )
    return path


def _stage_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temp:
            staged = Path(temp.name)
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
    except OSError:
        if staged is not None:
            staged.unlink(missing_ok=True)
        raise
    return Path(temp.name)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically replace an app-managed file; use replace_with_backup for user files."""
    staged: Path | None = None
    try:
        staged = _stage_bytes(path, data)
        with _replace_lock:
            if path.exists():
                shutil.copymode(path, staged)
            os.replace(staged, path)
    except OSError as exc:
        raise ProjectError(
            f"Could not write {path.name}.",
            hint="Check folder permissions and available disk space, then try again.",
            details=f"path={path}; error={exc}",
        ) from exc
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    """Write UTF-8 text by replacing an app-managed file atomically."""
    atomic_write_bytes(path, text.encode("utf-8"))


def replace_with_backup(path: Path, data: bytes) -> Path | None:
    """Back up a user file before replacing it; return backup path, or None if new."""
    with _replace_lock:
        if path.is_symlink():
            raise ProjectError(
                f"Cannot replace symlink {path.name}.", hint="Select a regular file."
            )
        backup: Path | None = None
        if path.exists():
            if not path.is_file():
                raise ProjectError(f"Cannot replace {path.name}.", hint="Select a regular file.")
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            backup = path.with_name(f"{path.name}.{stamp}.{uuid4().hex}.bak")
            staged: Path | None = None
            try:
                staged = _stage_bytes(backup, b"")
                shutil.copy2(path, staged)
                os.replace(staged, backup)
            except OSError as exc:
                raise ProjectError(
                    f"Could not back up {path.name}.",
                    hint="Check folder permissions and free space before retrying.",
                    details=f"path={path}; error={exc}",
                ) from exc
            finally:
                if staged is not None:
                    staged.unlink(missing_ok=True)
        atomic_write_bytes(path, data)
        return backup


def hash_file(path: Path) -> str:
    """Stream a BLAKE2b digest without loading the whole file into memory."""
    digest = hashlib.blake2b()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ProjectError(
            f"Could not hash {path.name}.",
            hint="Check that the file exists and is readable, then try again.",
            details=f"path={path}; error={exc}",
        ) from exc
    return digest.hexdigest()


@lru_cache(maxsize=256)
def _cached_digest(path: Path, size: int, mtime_ns: int) -> str:
    digest = hash_file(path)
    try:
        stat = path.stat()
    except OSError as exc:
        raise ProjectError(
            f"Could not stat {path.name} after hashing.",
            hint="Check the file and try again.",
            details=f"path={path}; error={exc}",
        ) from exc
    if (stat.st_size, stat.st_mtime_ns) != (size, mtime_ns):
        raise ProjectError(
            f"{path.name} changed while hashing.",
            hint="Wait for the edit to finish and try again.",
        )
    return digest


@dataclass(frozen=True)
class Fingerprint:
    """A metadata snapshot; digest is hashed on first access, then cached for this metadata."""

    path: Path
    size: int
    mtime_ns: int

    @classmethod
    def from_path(cls, path: Path) -> Fingerprint:
        try:
            path = path.resolve()
            stat = path.stat()
        except (OSError, RuntimeError) as exc:
            raise ProjectError(
                f"Could not stat {path.name}.",
                hint="Check that the file exists and is readable, then try again.",
                details=f"path={path}; error={exc}",
            ) from exc
        return cls(path, stat.st_size, stat.st_mtime_ns)

    @property
    def digest(self) -> str:
        """Lazy hash; cache keys assume size/mtime reflect content changes."""
        return _cached_digest(self.path, self.size, self.mtime_ns)
