"""P3-T02: ``.ctstudio/lock`` — one CT Studio edits a project at a time.

The first opener writes the lock (pid, host, a random token). A second opener gets the
project read-only and is told who holds it. A lock left by a CT Studio that has gone
(same computer, process no longer running) is stale and taken over. A lock from another
computer cannot be checked, so it is respected.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from ctstudio.core.project import lock as lock_module
from ctstudio.core.project.lock import LockOwner, acquire, pid_alive, read_owner

pytestmark = pytest.mark.timeout(30)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "Track é 日本"
    (root / ".ctstudio").mkdir(parents=True)
    return root


def _lock_file(root: Path) -> Path:
    return root / ".ctstudio" / "lock"


def _dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def _write_lock(root: Path, pid: int, host: str, owner_id: str = "theirs") -> None:
    data = {"pid": pid, "host": host, "token": owner_id, "since": "2026-11-02T00:00:00Z"}
    _lock_file(root).write_text(json.dumps(data), encoding="utf-8")


def test_this_process_is_alive_and_a_finished_one_is_not() -> None:
    assert pid_alive(os.getpid())
    assert not pid_alive(_dead_pid())


def test_a_finished_process_whose_handle_is_still_open_is_not_alive() -> None:
    """Windows keeps an exited process's record while a handle is open; it must not count."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert not pid_alive(child.pid)  # ``child`` still holds its handle here
    del child


@pytest.mark.parametrize("pid", [0, -1])
def test_impossible_pids_are_not_alive(pid: int) -> None:
    assert not pid_alive(pid)


@pytest.mark.parametrize("pid", [0, -1])
def test_impossible_pids_never_reach_the_os(pid: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """On Linux ``kill(0, 0)`` would signal CT Studio's own process group and say "alive"."""
    asked: list[int] = []

    def fake_kill(target: int, _signal: int) -> None:
        asked.append(target)

    monkeypatch.setattr(lock_module.sys, "platform", "linux")
    monkeypatch.setattr(lock_module.os, "kill", fake_kill)
    assert not pid_alive(pid)
    assert asked == []


def test_the_first_opener_holds_the_lock_and_records_who_it_is(tmp_path: Path) -> None:
    root = _root(tmp_path)
    result = acquire(root)
    assert result.held is not None
    assert result.owner is None
    data = json.loads(_lock_file(root).read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()
    assert data["host"] == socket.gethostname()
    assert data["token"] == result.held.token
    assert len(data["token"]) == 32
    assert data["since"].endswith("Z")


def test_a_second_opener_is_told_who_holds_it(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first = acquire(root)
    second = acquire(root)
    assert first.held is not None
    assert second.held is None
    assert second.owner == LockOwner(os.getpid(), socket.gethostname(), first.held.since)
    assert second.reason == (
        f"CT Studio (process {os.getpid()}) on this computer has this project open"
    )


def test_release_frees_the_project_for_the_next_opener(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first = acquire(root)
    assert first.held is not None
    first.held.release()
    assert not _lock_file(root).exists()
    first.held.release()  # twice is harmless
    assert acquire(root).held is not None


def test_release_leaves_a_lock_that_is_no_longer_ours(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first = acquire(root)
    assert first.held is not None
    _write_lock(root, os.getpid(), socket.gethostname(), owner_id="someone-else")
    first.held.release()
    assert json.loads(_lock_file(root).read_text(encoding="utf-8"))["token"] == "someone-else"  # noqa: S105 - a lock id


def test_a_lock_left_by_a_closed_ct_studio_is_taken_over(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_lock(root, _dead_pid(), socket.gethostname())
    result = acquire(root)
    assert result.held is not None
    assert result.took_over_from is not None
    assert json.loads(_lock_file(root).read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_a_lock_from_another_computer_is_respected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_lock(root, _dead_pid(), "other-pc")
    result = acquire(root)
    assert result.held is None
    assert result.owner is not None
    assert result.owner.host == "other-pc"
    assert result.reason == "CT Studio on the computer 'other-pc' has this project open"


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{not json",
        '{"pid": "x"}',
        "[1]",
        '{"pid": true, "host": "h"}',
        '{"pid": 5, "host": 3}',
    ],
)
def test_a_damaged_lock_is_stale_only_once_it_is_old(tmp_path: Path, content: str) -> None:
    """A brand-new damaged lock may be one being written this instant; an old one is debris."""
    root = _root(tmp_path)
    _lock_file(root).write_text(content, encoding="utf-8")
    fresh = acquire(root)
    assert fresh.held is None
    assert fresh.owner is None
    assert fresh.reason == "another CT Studio is opening this project"
    old = time.time() - lock_module.DAMAGED_GRACE_S - 5
    os.utime(_lock_file(root), (old, old))
    assert acquire(root).held is not None


def test_read_owner_reports_the_holder_without_taking_the_lock(tmp_path: Path) -> None:
    root = _root(tmp_path)
    assert read_owner(root) is None
    held = acquire(root).held
    assert held is not None
    owner = read_owner(root)
    assert owner is not None
    assert owner.pid == os.getpid()
    assert _lock_file(root).exists()


def test_a_folder_that_cannot_take_a_lock_opens_read_only_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)

    def refuse(*_args: object, **_kwargs: object) -> int:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(lock_module.os, "open", refuse)
    result = acquire(root)
    assert result.held is None
    assert result.owner is None
    assert result.reason == "the project folder cannot be written to (Permission denied)"


def test_two_openers_at_the_same_moment_get_exactly_one_lock(tmp_path: Path) -> None:
    root = _root(tmp_path)
    start = threading.Barrier(8)
    results: list[bool] = []

    def open_it() -> None:
        start.wait()
        results.append(acquire(root).held is not None)

    threads = [threading.Thread(target=open_it) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [False] * 7 + [True]


def test_openers_racing_to_take_over_a_stale_lock_get_exactly_one_lock(tmp_path: Path) -> None:
    """Without a takeover guard, a late opener could delete the lock a quicker one just made."""
    root = _root(tmp_path)
    _write_lock(root, _dead_pid(), socket.gethostname())
    start = threading.Barrier(8)
    results: list[bool] = []

    def open_it() -> None:
        start.wait()
        results.append(acquire(root).held is not None)

    threads = [threading.Thread(target=open_it) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [False] * 7 + [True]
    assert not (root / ".ctstudio" / "lock.takeover").exists()


def test_a_takeover_never_deletes_a_lock_that_became_live_meanwhile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stale check is repeated under the takeover guard, just before deleting."""
    root = _root(tmp_path)
    _write_lock(root, _dead_pid(), socket.gethostname())
    real_guard = lock_module._takeover_guard  # pyright: ignore[reportPrivateUsage]

    def guard_after_a_rival_wins(path: Path) -> bool:
        _lock_file(root).unlink()
        _write_lock(root, os.getpid(), socket.gethostname(), owner_id="rival")
        return real_guard(path)

    monkeypatch.setattr(lock_module, "_takeover_guard", guard_after_a_rival_wins)
    result = acquire(root)
    assert result.held is None
    assert json.loads(_lock_file(root).read_text(encoding="utf-8"))["token"] == "rival"  # noqa: S105 - a lock id


def test_a_takeover_guard_left_by_a_crash_is_cleared_once_old(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_lock(root, _dead_pid(), socket.gethostname())
    guard = root / ".ctstudio" / "lock.takeover"
    guard.write_text("", encoding="utf-8")
    assert acquire(root).held is None  # someone may be taking over right now
    old = time.time() - lock_module.DAMAGED_GRACE_S - 5
    os.utime(guard, (old, old))
    assert acquire(root).held is not None
    assert not guard.exists()
