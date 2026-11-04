"""Optimistic user-file replacement must check after durable replacement staging."""

from __future__ import annotations

import errno
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from ctstudio.core import fsutil
from ctstudio.core.errors import ProjectError


@pytest.mark.parametrize("expected", [b"loaded snapshot", b""])
def test_expected_rejects_external_edit_after_replacement_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, expected: bytes
) -> None:
    path = tmp_path / "manifest café.toml"
    path.write_bytes(expected)
    real_stage = fsutil._stage_bytes
    staged_files: list[Path] = []

    def stage(target: Path, data: bytes) -> Path:
        staged = real_stage(target, data)
        staged_files.append(staged)
        if target == path:
            path.write_bytes(b"EXTERNAL USER EDIT")
        return staged

    monkeypatch.setattr(fsutil, "_stage_bytes", stage)
    with pytest.raises(ProjectError, match="changed") as caught:
        fsutil.replace_with_backup(path, b"replacement", expected=expected)
    assert caught.value.hint and "reopen" in caught.value.hint.lower()
    assert path.read_bytes() == b"EXTERNAL USER EDIT"
    assert all(not staged.exists() for staged in staged_files)
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == expected
    assert set(tmp_path.iterdir()) == {path, *backups}


@pytest.mark.parametrize("phase", ["backup", "replacement", "mode"])
@pytest.mark.parametrize("change", ["edit", "delete"])
def test_expected_rejects_changes_during_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str, change: str
) -> None:
    path = tmp_path / "work.bin"
    path.write_bytes(b"snapshot")
    real_stage = fsutil._stage_bytes
    real_copy = fsutil.shutil.copy2
    real_mode = fsutil.shutil.copymode

    def change_target() -> None:
        if change == "delete":
            path.unlink()
        else:
            path.write_bytes(b"external")

    def stage(target: Path, data: bytes) -> Path:
        staged = real_stage(target, data)
        if phase == "replacement" and target == path:
            change_target()
        return staged

    def copy(source: Path, target: Path) -> Path | str:
        result = real_copy(source, target)
        if phase == "backup":
            change_target()
        return result

    def mode(source: Path, target: Path, *, follow_symlinks: bool = True) -> None:
        real_mode(source, target, follow_symlinks=follow_symlinks)
        if phase == "mode" and source == path:
            change_target()

    monkeypatch.setattr(fsutil, "_stage_bytes", stage)
    monkeypatch.setattr(fsutil.shutil, "copy2", copy)
    monkeypatch.setattr(fsutil.shutil, "copymode", mode)
    with pytest.raises(ProjectError) as caught:
        fsutil.replace_with_backup(path, b"replacement", expected=b"snapshot")
    assert caught.value.hint
    if change == "delete":
        assert not path.exists()
    else:
        assert path.read_bytes() == b"external"
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"snapshot"
    assert set(tmp_path.iterdir()) == {*backups, *([path] if path.exists() else [])}


@pytest.mark.parametrize("expected", [b"snapshot", b""])
def test_matching_expected_commits_with_exact_backup(tmp_path: Path, expected: bytes) -> None:
    path = tmp_path / "exact café.bin"
    path.write_bytes(expected)
    backup = fsutil.replace_with_backup(path, b"replacement", expected=expected)
    assert path.read_bytes() == b"replacement"
    assert backup is not None and backup.read_bytes() == expected
    assert set(tmp_path.iterdir()) == {path, backup}


def test_late_symlink_is_rejected_even_when_referent_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "manifest.bin"
    referent = tmp_path / "elsewhere.bin"
    referent.write_bytes(b"snapshot")
    # Probe only genuine lack of symlink support/Windows privilege, not arbitrary errors.
    try:
        path.symlink_to(referent)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314 or exc.errno in (errno.ENOSYS, errno.EOPNOTSUPP):
            pytest.skip(f"File symlink creation unavailable: {exc}")
        raise
    path.unlink()
    path.write_bytes(b"snapshot")
    real_stage = fsutil._stage_bytes

    def stage(target: Path, data: bytes) -> Path:
        staged = real_stage(target, data)
        if target == path:
            path.unlink()
            path.symlink_to(referent)
        return staged

    monkeypatch.setattr(fsutil, "_stage_bytes", stage)
    with pytest.raises(ProjectError, match="symlink") as caught:
        fsutil.replace_with_backup(path, b"replacement", expected=b"snapshot")
    assert caught.value.hint
    assert path.is_symlink() and path.readlink().samefile(referent)
    assert referent.read_bytes() == b"snapshot"
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"snapshot"
    assert set(tmp_path.iterdir()) == {path, referent, *backups}


def test_expected_read_failure_preserves_target_and_cleans_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "read.bin"
    path.write_bytes(b"snapshot")
    real_read = Path.read_bytes
    error = PermissionError("external reader denied")
    faults = [error]

    def read(target: Path) -> bytes:
        if target == path and faults:
            raise faults.pop()
        return real_read(target)

    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(ProjectError, match="verify") as caught:
        fsutil.replace_with_backup(path, b"replacement", expected=b"snapshot")
    assert caught.value.__cause__ is error
    assert caught.value.hint and "reopen" in caught.value.hint
    assert not faults
    assert path.read_bytes() == b"snapshot"
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"snapshot"
    assert set(tmp_path.iterdir()) == {path, *backups}


@pytest.mark.parametrize("phase", ["backup", "replacement"])
def test_fsync_failure_cleans_partial_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    path = tmp_path / "durable.bin"
    path.write_bytes(b"snapshot")
    real_stage = fsutil._stage_bytes
    faults = [OSError("disk fsync failure")]
    real_fsync = os.fsync
    failing = False

    def fsync(fd: int) -> None:
        if failing and faults:
            raise faults.pop()
        real_fsync(fd)

    def stage(target: Path, data: bytes) -> Path:
        nonlocal failing
        failing = (target == path) == (phase == "replacement")
        return real_stage(target, data)

    monkeypatch.setattr(fsutil.os, "fsync", fsync)
    monkeypatch.setattr(fsutil, "_stage_bytes", stage)
    with pytest.raises(ProjectError) as caught:
        fsutil.replace_with_backup(path, b"replacement", expected=b"snapshot")
    assert caught.value.hint and not faults
    assert path.read_bytes() == b"snapshot"
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == (1 if phase == "replacement" else 0)
    assert all(backup.read_bytes() == b"snapshot" for backup in backups)
    assert set(tmp_path.iterdir()) == {path, *backups}


def test_backup_failure_never_stages_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "backup.bin"
    path.write_bytes(b"snapshot")
    faults = [PermissionError("backup denied")]

    def copy(_source: Path, _target: Path) -> None:
        raise faults.pop()

    monkeypatch.setattr(fsutil.shutil, "copy2", copy)
    with pytest.raises(ProjectError, match="back up") as caught:
        fsutil.replace_with_backup(path, b"replacement", expected=b"snapshot")
    assert caught.value.hint and not faults
    assert path.read_bytes() == b"snapshot"
    assert list(tmp_path.iterdir()) == [path]


def test_default_backup_preserves_two_argument_atomic_write_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "default.bin"
    path.write_bytes(b"snapshot")
    calls: list[tuple[Path, bytes]] = []

    def write(target: Path, data: bytes) -> None:
        calls.append((target, data))

    monkeypatch.setattr(fsutil, "atomic_write_bytes", write)
    backup = fsutil.replace_with_backup(path, b"replacement")
    assert calls == [(path, b"replacement")]
    assert backup is not None and backup.read_bytes() == b"snapshot"


@pytest.mark.parametrize("state", ["stale", "missing", "matching"])
def test_atomic_expected_contract_without_backup(tmp_path: Path, state: str) -> None:
    path = tmp_path / "atomic.bin"
    if state != "missing":
        path.write_bytes(b"snapshot" if state == "matching" else b"external")
    if state == "matching":
        fsutil.atomic_write_bytes(path, b"replacement", expected=b"snapshot")
        assert path.read_bytes() == b"replacement"
    else:
        with pytest.raises(ProjectError) as caught:
            fsutil.atomic_write_bytes(path, b"replacement", expected=b"snapshot")
        assert caught.value.hint
        if state == "missing":
            assert not path.exists()
        else:
            assert path.read_bytes() == b"external"
    assert set(tmp_path.iterdir()) == ({path} if path.exists() else set())


def test_backup_commit_lock_remains_held_during_replacement_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "concurrent.bin"
    path.write_bytes(b"snapshot")
    ready, release = Event(), Event()
    real_stage = fsutil._stage_bytes

    def stage(target: Path, data: bytes) -> Path:
        staged = real_stage(target, data)
        if target == path:
            ready.set()
            assert release.wait(5)
        return staged

    monkeypatch.setattr(fsutil, "_stage_bytes", stage)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fsutil.replace_with_backup, path, b"first", expected=b"snapshot")
        try:
            assert ready.wait(5)
            acquired = fsutil._replace_lock.acquire(blocking=False)
            if acquired:
                fsutil._replace_lock.release()
            assert not acquired
            assert path.read_bytes() == b"snapshot"
        finally:
            release.set()
        backup = future.result(timeout=5)
    assert path.read_bytes() == b"first"
    assert backup is not None and backup.read_bytes() == b"snapshot"
