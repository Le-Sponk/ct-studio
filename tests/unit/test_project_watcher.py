"""P5-T06a: the project watcher on real watchfiles threads, plus injected-failure cases.

Real-watcher tests wait until the watcher says it is watching before changing anything,
then wait on an event (never a fixed sleep) for the change to arrive.
"""

from __future__ import annotations

import os
import queue
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from ctstudio.core.errors import ProjectError
from ctstudio.core.project.watch import WATCH_THREAD, ProjectWatcher, WatchPlan

pytestmark = pytest.mark.timeout(30)
NOTICE_S = 2.0  # the phase's limit for an outside edit to reach the dashboard


class Seen:
    """Collects what a watcher reports, from its own threads."""

    def __init__(self) -> None:
        self.changes: queue.Queue[frozenset[Path]] = queue.Queue()
        self.errors: list[ProjectError] = []
        self.error_threads: list[str] = []
        self.failed = threading.Event()

    def change(self, paths: frozenset[Path]) -> None:
        self.changes.put(paths)

    def error(self, error: ProjectError) -> None:
        self.error_threads.append(threading.current_thread().name)
        self.errors.append(error)
        self.failed.set()

    def until(self, wanted: Path, limit: float = NOTICE_S) -> set[Path]:
        """Everything reported until ``wanted`` shows up (or the limit passes)."""
        got: set[Path] = set()
        end = time.monotonic() + limit
        while wanted not in got:
            left = end - time.monotonic()
            if left <= 0:
                break
            try:
                got |= self.changes.get(timeout=left)
            except queue.Empty:
                break
        return got


def watch_threads() -> list[threading.Thread]:
    names = {WATCH_THREAD, f"{WATCH_THREAD}-outside"}  # not ctstudio-watchdog
    return [t for t in threading.enumerate() if t.name in names]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "Pistë é" / "proj ect"
    (folder / ".ctstudio" / "stage").mkdir(parents=True)
    (folder / "art").mkdir()
    (folder / "build").mkdir()
    return folder


@pytest.fixture
def seen() -> Seen:
    return Seen()


@contextmanager
def started(plan: WatchPlan, seen: Seen) -> Generator[ProjectWatcher, None, None]:
    watcher = ProjectWatcher(plan, seen.change, seen.error)
    watcher.start()
    try:
        assert watcher.wait_ready(10), "the watcher never started watching"
        yield watcher
    finally:
        watcher.stop()
        assert watcher.join(5), "a watcher thread did not stop"


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_an_edited_made_file_is_reported(root: Path, seen: Seen) -> None:
    stage = root / ".ctstudio" / "stage" / "course_model.brres"
    write(stage, b"made")
    with started(WatchPlan(root, {}), seen):
        write(stage, b"edited outside")
        assert stage in seen.until(stage)
    assert seen.errors == []


def test_an_atomic_save_is_reported_under_the_files_own_name(root: Path, seen: Seen) -> None:
    stage = root / ".ctstudio" / "stage" / "course.kcl"
    write(stage, b"made")
    with started(WatchPlan(root, {}), seen):
        temp = stage.with_name("course.kcl.tmp")
        write(temp, b"saved by an editor")
        os.replace(temp, stage)
        assert stage in seen.until(stage)


def test_ignored_changes_are_never_reported(root: Path, seen: Seen) -> None:
    sentinel = root / "files" / "course.kmp"
    ignored = [
        root / ".ctstudio" / "state.json",
        root / ".ctstudio" / "logs" / "build.log",
        root / "build" / "track.szs",
        root / "art" / "track.blend1",
        root / "art" / "track.blend@",
    ]
    with started(WatchPlan(root, {}), seen):
        for path in ignored:
            write(path, b"noise")
        write(sentinel, b"wanted")
        got = seen.until(sentinel)
    assert sentinel in got
    assert got.isdisjoint(ignored)


def test_an_outside_blend_is_watched_but_not_its_neighbours(
    root: Path, tmp_path: Path, seen: Seen
) -> None:
    art = tmp_path / "Art é"
    blend = art / "track.blend"
    write(blend, b"BLENDER")
    neighbour = art / "other.blend"
    with started(WatchPlan(root, {art: frozenset({"track.blend"})}), seen):
        assert len(watch_threads()) == 2  # the project folder, and the outside folder
        write(neighbour, b"BLENDER")
        write(art / "track.blend1", b"backup")
        write(blend, b"BLENDER saved")
        got = seen.until(blend)
    assert got == {blend}


def test_a_missing_outside_folder_is_left_out(root: Path, tmp_path: Path, seen: Seen) -> None:
    gone = tmp_path / "unplugged drive"
    stage = root / ".ctstudio" / "stage" / "map_model.brres"
    with started(WatchPlan(root, {gone: frozenset({"t.blend"})}), seen):
        write(stage, b"edited")
        assert stage in seen.until(stage)
    assert seen.errors == []


def test_a_project_folder_that_cannot_be_watched_is_reported_not_raised(
    tmp_path: Path, seen: Seen
) -> None:
    missing = tmp_path / "gone é"
    watcher = ProjectWatcher(WatchPlan(missing, {}), seen.change, seen.error)
    watcher.start()  # must not raise on the caller's thread
    assert seen.failed.wait(10)
    assert watcher.join(5)
    assert watcher.wait_ready(0)  # given up counts as settled: nobody waits forever
    assert not watcher.alive
    (error,) = seen.errors
    assert isinstance(error, ProjectError)
    assert str(missing) in error.user_message
    assert "Refresh statuses" in (error.hint or "")
    assert seen.error_threads == [WATCH_THREAD]


def test_stop_ends_every_watcher_thread_quickly(root: Path, tmp_path: Path, seen: Seen) -> None:
    art = tmp_path / "art"
    art.mkdir()
    watcher = ProjectWatcher(
        WatchPlan(root, {art: frozenset({"t.blend"})}), seen.change, seen.error
    )
    watcher.start()
    assert watcher.wait_ready(10)
    assert watcher.alive and watcher.intact
    assert sorted(t.name for t in watch_threads()) == [WATCH_THREAD, f"{WATCH_THREAD}-outside"]
    begun = time.monotonic()
    watcher.stop()
    assert watcher.join(5)
    assert time.monotonic() - begun < 1.0
    assert not watcher.alive
    assert not watcher.intact  # a stopped watcher is not one to keep
    assert watch_threads() == []
    assert seen.errors == []


# --- folders that go away and come back (review of P5-T06a) --------------------------------------


def test_an_outside_folder_that_comes_back_is_reported_and_watched_again(
    root: Path, tmp_path: Path, seen: Seen
) -> None:
    import shutil

    art = tmp_path / "unplugged é"
    blend = art / "track.blend"
    write(blend, b"BLENDER")
    with started(WatchPlan(root, {art: frozenset({"track.blend"})}), seen) as watcher:
        shutil.rmtree(art)
        assert art in seen.until(art), "a folder that went away is a change (the file is missing)"
        write(blend, b"BLENDER back")
        assert art in seen.until(art), "a folder that came back is a change too"
        write(blend, b"BLENDER edited after")
        assert blend in seen.until(blend), "edits are noticed again once it is back"
        assert watcher.intact
    assert seen.errors == []


def test_an_outside_folder_missing_at_start_is_picked_up_when_it_appears(
    root: Path, tmp_path: Path, seen: Seen
) -> None:
    art = tmp_path / "later é"
    blend = art / "track.blend"
    with started(WatchPlan(root, {art: frozenset({"track.blend"})}), seen) as watcher:
        write(blend, b"BLENDER")
        assert art in seen.until(art)
        write(blend, b"BLENDER edited")
        assert blend in seen.until(blend)
        assert watcher.intact
    assert seen.errors == []


def test_a_project_folder_removed_while_watched_is_reported(tmp_path: Path, seen: Seen) -> None:
    import shutil

    root = tmp_path / "removed é"
    root.mkdir()
    watcher = ProjectWatcher(WatchPlan(root, {}), seen.change, seen.error)
    watcher.start()
    try:
        assert watcher.wait_ready(10)
        shutil.rmtree(root)
        assert seen.failed.wait(10), "watching stopped without a word"
        assert watcher.join(5)
        (error,) = seen.errors
        assert error.user_message == (
            f"CT Studio cannot notice changes in {root} (the folder is gone)."
        )
        assert not watcher.intact
    finally:
        watcher.stop()
        assert watcher.join(5)
