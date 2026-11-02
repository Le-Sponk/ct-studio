"""P3-T04: ``.ctstudio/state.json`` — what CT Studio last made, and from what.

The file is app-managed and safe to delete, so a missing or damaged one reads as "nothing
made yet" (damage is logged, never raised). File checks use size+mtime first and hash only
when they differ but the size matches.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from ctstudio.core import fsutil
from ctstudio.core.components.state import (
    GENERATED_DIR,
    STATE_FILE,
    ComponentRecord,
    FileRecord,
    ProjectState,
    load_state,
    record,
    save_state,
)
from ctstudio.core.errors import ProjectError

pytestmark = pytest.mark.timeout(30)


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _bump_mtime(path: Path, seconds: int = 10) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + seconds * 1_000_000_000))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "Projet é"
    (folder / ".ctstudio").mkdir(parents=True)
    return folder


def test_a_record_names_outputs_by_stage_path_and_inputs_by_project_path(
    root: Path, tmp_path: Path
) -> None:
    out = _write(root / GENERATED_DIR / "course_model.brres", b"model")
    fx = _write(root / GENERATED_DIR / "posteffect" / "posteffect.blight", b"light")
    blend = _write(root / "art" / "track.blend", b"blend")
    outside = _write(tmp_path / "elsewhere.blend", b"other")
    rec = record(root, "key", outputs=[out, fx], inputs=[blend, outside])
    assert set(rec.outputs) == {"course_model.brres", "posteffect/posteffect.blight"}
    assert set(rec.inputs) == {"art/track.blend", str(outside)}
    assert rec.settings == "key"
    assert rec.outputs["course_model.brres"] == FileRecord(
        5, out.stat().st_mtime_ns, fsutil.hash_file(out)
    )


def test_an_output_outside_the_stage_folder_is_refused(root: Path) -> None:
    stray = _write(root / "files" / "course.kmp", b"x")
    with pytest.raises(ValueError, match=r"course\.kmp is outside \.ctstudio/stage$"):
        record(root, "key", outputs=[stray], inputs=[])


def test_save_then_load_gives_the_same_state(root: Path) -> None:
    out = _write(root / GENERATED_DIR / "course.kcl", b"kcl")
    state = ProjectState({"kcl": record(root, "k1", outputs=[out], inputs=[])})
    save_state(root, state)
    assert load_state(root) == state
    data = json.loads((root / STATE_FILE).read_text(encoding="utf-8"))
    assert data["format"] == 1
    assert data["components"]["kcl"]["outputs"]["course.kcl"]["size"] == 3


def test_a_missing_state_file_is_empty(root: Path) -> None:
    assert load_state(root) == ProjectState({})


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        '{"format": 2, "components": {}}',
        '{"format": 1}',
        '{"format": 1, "components": {"kcl": {"settings": 1, "outputs": {}, "inputs": {}}}}',
        '{"format": 1, "components": {"kcl": {"settings": "k", "outputs": {"a": {"size": "1",'
        ' "mtime_ns": 1, "digest": "d"}}, "inputs": {}}}}',
        '{"format": 1, "components": {"kcl": {"settings": "k", "outputs": {"a": {"size": true,'
        ' "mtime_ns": 1, "digest": "d"}}, "inputs": {}}}}',
        '{"format": 1, "components": {"kcl": {"settings": "k", "outputs": [], "inputs": {}}}}',
        '{"format": 1, "components": {"kcl": {"settings": "k", "outputs": {"a": {"size": 1,'
        ' "mtime_ns": 1, "digest": 5}}, "inputs": {}}}}',
    ],
)
def test_a_damaged_state_file_is_empty_and_logged(
    root: Path, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    (root / STATE_FILE).write_text(text, encoding="utf-8")
    logger = logging.getLogger("ctstudio.core.components.state")
    logger.addHandler(caplog.handler)
    try:
        assert load_state(root) == ProjectState({})
    finally:
        logger.removeHandler(caplog.handler)
    assert "state.json" in caplog.text
    assert "starting fresh" in caplog.text


def test_an_unreadable_state_path_is_a_project_error(root: Path) -> None:
    (root / STATE_FILE).mkdir()
    with pytest.raises(ProjectError, match=r"Could not read state\.json"):
        load_state(root)


def test_unchanged_size_and_mtime_is_the_same_without_hashing(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _write(root / GENERATED_DIR / "a.bin", b"abc")
    rec = FileRecord.of(out)
    fsutil._cached_digest.cache_clear()  # type: ignore[reportPrivateUsage] - a fresh process
    monkeypatch.setattr(fsutil, "hash_file", _no_hashing)
    assert rec.compare(out) == "same"


def _no_hashing(path: Path) -> str:
    raise AssertionError(f"hashed {path}")


def test_a_different_size_is_changed_without_hashing(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _write(root / GENERATED_DIR / "a.bin", b"abc")
    rec = FileRecord.of(out)
    out.write_bytes(b"abcd")
    monkeypatch.setattr(fsutil, "hash_file", _no_hashing)
    assert rec.compare(out) == "changed"


def test_a_touched_file_is_hashed_once_and_still_the_same(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _write(root / GENERATED_DIR / "a.bin", b"abc")
    rec = FileRecord.of(out)
    _bump_mtime(out)
    calls: list[Path] = []
    real = fsutil.hash_file

    def counting(path: Path) -> str:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(fsutil, "hash_file", counting)
    assert rec.compare(out) == "same"
    assert rec.compare(out) == "same"
    assert len(calls) == 1


def test_same_size_new_content_is_changed(root: Path) -> None:
    out = _write(root / GENERATED_DIR / "a.bin", b"abc")
    rec = FileRecord.of(out)
    out.write_bytes(b"xyz")
    _bump_mtime(out)
    assert rec.compare(out) == "changed"


def test_a_deleted_file_or_one_replaced_by_a_folder(root: Path) -> None:
    out = _write(root / GENERATED_DIR / "a.bin", b"abc")
    rec = FileRecord.of(out)
    out.unlink()
    assert rec.compare(out) == "missing"
    assert rec.compare(out / "inside") == "missing"
    out.mkdir()
    assert rec.compare(out) == "changed"


def test_a_file_where_a_folder_was_means_the_files_inside_are_missing(root: Path) -> None:
    """Linux raises NotADirectoryError for ``file/inside``; Windows FileNotFoundError."""
    out = _write(root / GENERATED_DIR / "posteffect" / "a.blight", b"abc")
    rec = FileRecord.of(out)
    out.unlink()
    out.parent.rmdir()
    out.parent.write_bytes(b"now a file")
    assert rec.compare(out) == "missing"


def test_an_empty_file_replaced_by_an_empty_folder_is_changed(root: Path) -> None:
    """On Windows a folder's size is 0 too, so the size check alone would hash a folder."""
    out = _write(root / GENERATED_DIR / "a.bin", b"")
    rec = FileRecord.of(out)
    out.unlink()
    out.mkdir()
    _bump = out.stat()
    os.utime(out, ns=(_bump.st_atime_ns, _bump.st_mtime_ns + 10_000_000_000))
    assert rec.compare(out) == "changed"


def test_records_are_frozen_and_compare_by_value() -> None:
    a = ComponentRecord("k", {"x": FileRecord(1, 2, "d")}, {})
    assert a == ComponentRecord("k", {"x": FileRecord(1, 2, "d")}, {})
    with pytest.raises(AttributeError):
        a.settings = "other"  # type: ignore[misc]
