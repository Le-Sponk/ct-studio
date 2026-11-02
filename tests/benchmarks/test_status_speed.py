"""P3-T04 timing: status for 20 parts' worth of files, cold ≤ 300 ms and warm ≤ 30 ms.

"Cold" = a fresh process's first look after every file was touched since it was made, so each
one is hashed once (the worst case short of a rebuild). "Warm" = the next look, when size and
mtime match what is cached and nothing is hashed. The files are 1 MiB each (an average
course model is 1-3 MiB); 4 parts x 5 projects' worth = 20 parts, 25 files including inputs.
The limits are the phase file's; timings print for docs/dev/BENCHMARKS.md.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from ctstudio.core import fsutil
from ctstudio.core.components.state import GENERATED_DIR, ProjectState, record, save_state
from ctstudio.core.components.status import State, evaluate, settings_key
from ctstudio.core.project import manifest as m
from ctstudio.core.tools.registry import TOOL_BY_ID

PARTS = {
    "course_model": "course_model.brres",
    "kcl": "course.kcl",
    "minimap": "map_model.brres",
    "skybox": "vrcorn_model.brres",
}
MIB = 1024 * 1024


@dataclass
class _Project:
    root: Path
    manifest: m.Manifest


def _make(root: Path) -> _Project:
    project = _Project(root, m.Manifest(m.ProjectInfo(name="Bench", blend="track.blend")))
    root.mkdir(parents=True)
    (root / "track.blend").write_bytes(os.urandom(MIB))
    made = {}
    for part, name in PARTS.items():
        out = root / GENERATED_DIR / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(os.urandom(MIB))
        key = settings_key(project.manifest, part)
        made[part] = record(root, key, [out], [root / "track.blend"])
    save_state(root, ProjectState(made))
    return project


def _touch_all(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file() and path.name != "state.json":
            st = path.stat()
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 7_000_000_000))


@pytest.mark.slow
@pytest.mark.benchmark
def test_status_of_20_parts_cold_and_warm(tmp_path: Path) -> None:
    projects = [_make(tmp_path / f"Projet {i} é") for i in range(5)]
    for project in projects:
        _touch_all(project.root)
    fsutil._cached_digest.cache_clear()  # type: ignore[reportPrivateUsage] - a fresh process
    tools = frozenset(TOOL_BY_ID)

    start = time.perf_counter()
    cold = [evaluate(p, tools) for p in projects]
    cold_s = time.perf_counter() - start
    start = time.perf_counter()
    warm = [evaluate(p, tools) for p in projects]
    warm_s = time.perf_counter() - start

    for result in (*cold, *warm):
        assert all(result[part].state is State.READY for part in PARTS), result
    cold_ms, warm_ms = cold_s * 1000, warm_s * 1000
    print(f"status, 20 parts (25 x 1 MiB files): cold {cold_ms:.1f} ms, warm {warm_ms:.1f} ms")
    assert cold_s <= 0.300
    assert warm_s <= 0.030
