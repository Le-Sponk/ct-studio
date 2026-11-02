"""The project lock ``.ctstudio/lock``: one CT Studio edits a project at a time (P3-T02).

The lock file holds JSON ``{pid, host, token, since}``. It is created with ``O_EXCL``, so
when two CT Studios open a project at the same moment exactly one wins; the other opens
read-only and is told who holds it.

A lock is **stale**, and taken over, when it was written on this computer by a process that
is no longer running, or when it is damaged and older than ``DAMAGED_GRACE_S`` (a fresh
damaged file may be one another CT Studio is writing this instant). A lock from another
computer cannot be checked from here, so it is always respected. A takeover happens under a
second ``O_EXCL`` file, ``lock.takeover``, and re-checks the lock first, so two openers that
both saw the same stale lock cannot both win. ``release`` removes the file only while it
still carries our token, so it never deletes someone else's lock.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

LOCK_NAME = "lock"
DAMAGED_GRACE_S = 30.0
_OPENING = "another CT Studio is opening this project"

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _open_process = _KERNEL32.OpenProcess
    _open_process.restype = wintypes.HANDLE
    _open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _exit_code = _KERNEL32.GetExitCodeProcess
    _exit_code.restype = wintypes.BOOL
    _exit_code.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    _close_handle = _KERNEL32.CloseHandle
    _close_handle.restype = wintypes.BOOL
    _close_handle.argtypes = (wintypes.HANDLE,)
    _QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259
    _ACCESS_DENIED = 5

    def _windows_alive(pid: int) -> bool:
        handle = _open_process(_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            # Access denied means the process exists but belongs to someone else.
            return ctypes.get_last_error() == _ACCESS_DENIED
        try:
            code = wintypes.DWORD()
            return bool(_exit_code(handle, ctypes.byref(code))) and code.value == _STILL_ACTIVE
        finally:
            _close_handle(handle)


def pid_alive(pid: int) -> bool:
    """Whether a process with this id is running on this computer."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user
    return True


@dataclass(frozen=True)
class LockOwner:
    pid: int
    host: str
    since: str

    def describe(self) -> str:
        if self.host == socket.gethostname():
            return f"CT Studio (process {self.pid}) on this computer has this project open"
        return f"CT Studio on the computer '{self.host}' has this project open"


@dataclass
class HeldLock:
    path: Path
    token: str
    since: str

    def release(self) -> None:
        """Remove the lock if it is still ours; safe to call more than once."""
        if _token_of(self.path) == self.token:
            self.path.unlink(missing_ok=True)


@dataclass(frozen=True)
class LockResult:
    """Either ``held`` (we own the project) or a ``reason`` it is read-only."""

    held: HeldLock | None
    owner: LockOwner | None = None
    reason: str | None = None
    took_over_from: LockOwner | None = None


def lock_path(root: Path) -> Path:
    return root / ".ctstudio" / LOCK_NAME


def acquire(root: Path) -> LockResult:
    """Take the lock of the project in ``root`` (its ``.ctstudio/`` must exist)."""
    path = lock_path(root)
    try:
        return LockResult(_create(path))
    except FileExistsError:
        pass
    except OSError as exc:
        reason = exc.strerror or str(exc)
        return LockResult(None, reason=f"the project folder cannot be written to ({reason})")
    text = _read(path)
    owner = _parse(text)
    if not _stale(path, text, owner):
        return _held_by(owner)
    return _take_over(path)


def _held_by(owner: LockOwner | None) -> LockResult:
    if owner is None:
        return LockResult(None, reason=_OPENING)
    return LockResult(None, owner, owner.describe())


def _take_over(path: Path) -> LockResult:
    """Replace a stale lock while holding the takeover guard, re-checking it first."""
    guard = path.with_name(LOCK_NAME + ".takeover")
    if not _takeover_guard(guard):
        return LockResult(None, reason=_OPENING)
    try:
        text = _read(path)
        owner = _parse(text)
        if not _stale(path, text, owner):  # another opener got there first
            return _held_by(owner)
        path.unlink(missing_ok=True)
        return LockResult(_create(path), took_over_from=owner)
    except OSError:  # a fresh opener created the lock between unlink and create
        return LockResult(None, reason=_OPENING)
    finally:
        _remove(guard)


def _takeover_guard(guard: Path) -> bool:
    """Create the guard; a guard older than ``DAMAGED_GRACE_S`` is from a crash and cleared.

    Two openers clearing the same crashed guard at the same instant could both pass; that
    needs a crash *and* a race, and the re-check under the guard still sees a live lock.
    """
    for _attempt in range(2):
        try:
            os.close(os.open(guard, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644))
        except FileExistsError:
            if not _older_than_grace(guard):
                return False
            _remove(guard)
        except OSError:
            return False
        else:
            return True
    return False


def _older_than_grace(path: Path) -> bool:
    try:
        return time.time() - path.stat().st_mtime > DAMAGED_GRACE_S
    except OSError:
        return True  # gone already: nothing to wait for


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass  # Windows: still open elsewhere for a moment; the grace period clears it


def _create(path: Path) -> HeldLock:
    token = uuid4().hex
    since = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    data = {"pid": os.getpid(), "host": socket.gethostname(), "token": token, "since": since}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data))
    return HeldLock(path, token, since)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _fields(text: str | None) -> dict[str, object] | None:
    try:
        data: object = json.loads(text or "")
    except ValueError:
        return None
    return cast("dict[str, object]", data) if isinstance(data, dict) else None


def _parse(text: str | None) -> LockOwner | None:
    fields = _fields(text)
    if fields is None:
        return None
    pid, host, since = fields.get("pid"), fields.get("host"), fields.get("since")
    if isinstance(pid, bool) or not isinstance(pid, int) or not isinstance(host, str):
        return None
    return LockOwner(pid, host, since if isinstance(since, str) else "")


def _token_of(path: Path) -> object:
    fields = _fields(_read(path))
    return None if fields is None else fields.get("token")


def _stale(path: Path, text: str | None, owner: LockOwner | None) -> bool:
    if owner is not None:
        return owner.host == socket.gethostname() and not pid_alive(owner.pid)
    return _older_than_grace(path)  # damaged: old debris, or one being written right now
