"""P5-T06a: outside folders that vanish or whose watch ends (scripted watch, no timing)."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from watch_fakes import OutsideScript, Seen

from ctstudio.core.project.watch import ProjectWatcher, WatchPlan

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "proj é"
    folder.mkdir()
    return folder


def test_an_outside_folder_vanishing_under_its_watch_is_a_change_not_an_error(
    root: Path, tmp_path: Path
) -> None:
    art = tmp_path / "art"
    art.mkdir()
    gone = threading.Event()

    def outside(kwargs: dict[str, Any]) -> Iterator[set[tuple[object, str]]]:
        if gone.is_set():  # (watched again later: nothing is there to watch)
            raise AssertionError("a missing folder was watched")
        yield set()
        art.rmdir()
        gone.set()
        raise FileNotFoundError(str(art))  # some systems report the loss this way

    script = OutsideScript(outside)
    seen = Seen()
    watcher = ProjectWatcher(WatchPlan(root, {art: None}), seen.change, seen.error, watch=script)
    watcher.start()
    try:
        assert gone.wait(5)
        end = time.monotonic() + 5
        while art not in {p for batch in seen.changes for p in batch} and time.monotonic() < end:
            time.sleep(0.01)
        assert frozenset({art}) in seen.changes
        assert seen.errors == []
        assert watcher.intact
    finally:
        watcher.stop()
        assert watcher.join(5)


def test_an_outside_watch_that_ends_by_itself_is_reported(root: Path, tmp_path: Path) -> None:
    art = tmp_path / "art"
    art.mkdir()

    def outside(_kwargs: dict[str, Any]) -> Iterator[set[tuple[object, str]]]:
        yield set()  # then it simply ends, the folder still there

    seen = Seen()
    watcher = ProjectWatcher(
        WatchPlan(root, {art: None}), seen.change, seen.error, watch=OutsideScript(outside)
    )
    watcher.start()
    assert watcher.join(5), "the project thread kept running after the outside one ended"
    (error,) = seen.errors
    assert error.user_message == (
        f"CT Studio cannot notice changes in {art} (watching ended unexpectedly)."
    )
    assert not watcher.intact
