"""P1-T05 filesystem safety, lazy fingerprints and Unicode paths."""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ctstudio.core.errors import ProjectError
from ctstudio.core.fsutil import (
    Fingerprint,
    atomic_write_bytes,
    atomic_write_text,
    ensure_inside,
    hash_file,
    replace_with_backup,
)


def test_atomic_writes_in_unicode_directory(tmp_path: Path) -> None:
    path = tmp_path / "course é track" / "track notes.txt"
    atomic_write_text(path, "é 🏁")
    assert path.read_text(encoding="utf-8") == "é 🏁"
    atomic_write_bytes(path, b"new bytes")
    assert path.read_bytes() == b"new bytes"
    assert list(path.parent.iterdir()) == [path]


def test_atomic_replace_is_never_observed_partial(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.bin"
    chunks = [bytes([n]) * (128 * 1024) for n in range(8)]
    atomic_write_bytes(path, chunks[0])

    # Windows cannot replace a destination while another thread has it open.
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda data: atomic_write_bytes(path, data), chunks))
    assert path.read_bytes() in chunks
    assert list(tmp_path.iterdir()) == [path]


def test_failed_replace_cleans_temp_and_preserves_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ctstudio.core import fsutil

    path = tmp_path / "output.bin"
    path.write_bytes(b"original")

    def fail(_src: Path, _dst: Path) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(fsutil.os, "replace", fail)
    with pytest.raises(ProjectError, match=r"output\.bin"):
        atomic_write_bytes(path, b"new")
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


def test_backup_naming_and_original_revisions(tmp_path: Path) -> None:
    path = tmp_path / "work é.txt"
    path.write_text("one", encoding="utf-8")
    first = replace_with_backup(path, b"two")
    second = replace_with_backup(path, b"three")
    assert first is not None and second is not None and first != second
    assert first.name.startswith(path.name + ".") and first.suffix == ".bak"
    assert first.read_bytes() == b"one"
    assert second.read_bytes() == b"two"
    assert path.read_bytes() == b"three"
    assert replace_with_backup(tmp_path / "new.txt", b"new") is None


def test_concurrent_backups_preserve_every_revision(tmp_path: Path) -> None:
    path = tmp_path / "work.bin"
    path.write_bytes(b"initial")
    payloads = [f"revision-{n}".encode() for n in range(12)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        backups = list(pool.map(lambda data: replace_with_backup(path, data), payloads))
    assert len(set(backups)) == len(payloads)
    assert all(backup is not None and backup.is_file() for backup in backups)
    assert {backup.read_bytes() for backup in backups if backup} | {path.read_bytes()} == {
        b"initial",
        *payloads,
    }


def test_failed_backup_preserves_user_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ctstudio.core import fsutil

    path = tmp_path / "keep.txt"
    path.write_bytes(b"user edits")

    def fail(_src: Path, _dst: Path) -> None:
        raise PermissionError("read denied")

    monkeypatch.setattr(fsutil.shutil, "copy2", fail)
    with pytest.raises(ProjectError, match="back up"):
        replace_with_backup(path, b"replacement")
    assert path.read_bytes() == b"user edits"
    assert list(tmp_path.iterdir()) == [path]


def test_symlink_cannot_be_replaced_as_user_file(tmp_path: Path) -> None:
    target = tmp_path / "user.txt"
    target.write_bytes(b"user edits")
    link = tmp_path / "shortcut.txt"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("file symlink unavailable on this host")
    with pytest.raises(ProjectError, match="symlink"):
        replace_with_backup(link, b"replacement")
    assert target.read_bytes() == b"user edits"


def test_ensure_inside_rejects_siblings_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    assert (
        ensure_inside(root, root / "nested" / "new.txt") == (root / "nested" / "new.txt").resolve()
    )
    with pytest.raises(ProjectError, match="outside"):
        ensure_inside(root, tmp_path / "project-other" / "file")
    with pytest.raises(ProjectError, match="outside"):
        ensure_inside(root, root / ".." / "elsewhere")
    link = root / "outside-link"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("directory symlink unavailable on this host")
    with pytest.raises(ProjectError, match="outside"):
        ensure_inside(root, link / "file")


def test_hash_file_streams_and_fingerprint_hashes_lazily(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ctstudio.core import fsutil

    path = tmp_path / "large enough.txt"
    data = b"x" * (1024 * 1024 + 19)
    path.write_bytes(data)
    calls = 0
    original = fsutil.hash_file

    def counted(file: Path) -> str:
        nonlocal calls
        calls += 1
        return original(file)

    monkeypatch.setattr(fsutil, "hash_file", counted)
    fingerprint = Fingerprint.from_path(path)
    assert fingerprint.size == len(data)
    assert fingerprint.mtime_ns == path.stat().st_mtime_ns
    assert calls == 0
    expected = hashlib.blake2b(data).hexdigest()
    assert fingerprint.digest == expected
    assert Fingerprint.from_path(path).digest == expected
    assert calls == 1
    path.write_bytes(b"changed")
    os.utime(path, ns=(path.stat().st_atime_ns, fingerprint.mtime_ns + 2_000_000_000))
    assert Fingerprint.from_path(path).digest == hashlib.blake2b(b"changed").hexdigest()
    assert calls == 2


def test_fingerprint_rejects_file_changed_during_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ctstudio.core import fsutil

    path = tmp_path / "moving.bin"
    path.write_bytes(b"before")
    fingerprint = Fingerprint.from_path(path)
    original = fsutil.hash_file

    def change_during_read(file: Path) -> str:
        digest = original(file)
        file.write_bytes(b"after-length-change")
        return digest

    monkeypatch.setattr(fsutil, "hash_file", change_during_read)
    with pytest.raises(ProjectError, match="changed while hashing"):
        _ = fingerprint.digest


def test_hash_missing_file_is_actionable(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match="missing") as exc:
        hash_file(tmp_path / "missing")
    assert exc.value.hint
