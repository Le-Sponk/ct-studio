"""P4-T08 timing: build steps on synthetic files, with the ARCHITECTURE §15 budgets asserted.

- A typical track whose parts are all the user's own files (stand-in sizes: course model
  3 MiB, skybox 1 MiB, minimap 256 KiB, the committed synthetic KCL and KMP, four
  post-effect files), built with the real Wiimm 2.42a tools: the first test build must take
  < 10 s ("test build excl. Blender export, typical track"), the no-change rebuild < 1 s,
  both in-process and as a whole ``ctstudio build`` process.
- One 100 MiB part staged, then unchanged (printed; the unchanged check < 1 s).
- The cache key of one step with 1,000 input files: cold (every file hashed) and warm (size
  and mtime match, nothing hashed). Warm must stay < 1 s, since a no-change rebuild of such a
  project checks exactly this.

Timings print for ``docs/dev/BENCHMARKS.md``. Files are freshly written, so they are likely
in the OS cache: these are not cold-disk numbers.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ctstudio.core import fsutil
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildSummary
from ctstudio.core.build.node import BuildContext, Node, NodeResult
from ctstudio.core.build.project_build import build_project, plan_build
from ctstudio.core.project import manifest_io
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.tools.process import CancelToken

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

KEPT = ROOT / "tests" / "fakes" / "recordings" / "wszst" / "2.42a" / "inputs"
KIB, MIB = 1024, 1024 * 1024
REAL_TOOLS = pytest.mark.skipif(
    not tp.WSZST.is_file() or not tp.WKMPT.is_file(), reason="Requires Wiimm 2.42a"
)
pytestmark = [pytest.mark.slow, pytest.mark.benchmark, pytest.mark.timeout(600)]


def brres(size: int) -> bytes:
    """A BRRES header with no models, zero-padded to ``size`` (as test_magic.brres).

    Not random padding: wszst 2.42a reads the body and crashes on random bytes (measured
    2026-11-03, any size from 128 KiB). Zeros compress far better than real models, so the
    first-build time here is a lower bound; BENCHMARKS.md gives a real-track figure too.
    """
    head = b"bres\xfe\xff\x00\x00" + struct.pack(">IHH", size, 0x10, 1) + b"root"
    return head + bytes(size - len(head))


def postfx(magic: bytes, size: int = 2 * KIB) -> bytes:
    return magic + struct.pack(">I", size) + bytes(size - 8)


def typical_track(root: Path) -> Manifest:
    """A project whose six parts are the user's own files, at typical sizes."""
    Project.create(root, "Bench é", slot="castle_course").close()
    files = root / "files"
    (files / "fx").mkdir(parents=True)
    shutil.copyfile(KEPT / "course.kcl", files / "course.kcl")
    shutil.copyfile(KEPT / "course.kmp", files / "course.kmp")
    sizes = {"course_model.brres": 3 * MIB, "vrcorn_model.brres": MIB, "map_model.brres": 256 * KIB}
    for name, size in sizes.items():
        (files / name).write_bytes(brres(size))
    for name, magic in (
        ("bblm", b"PBLM"),
        ("bdof", b"PDOF"),
        ("blight", b"LGHT"),
        ("blmap", b"LMAP"),
    ):
        (files / "fx" / f"posteffect.{name}").write_bytes(postfx(magic))
    chosen = {
        "course_model": "files/course_model.brres",
        "kcl": "files/course.kcl",
        "minimap": "files/map_model.brres",
        "skybox": "files/vrcorn_model.brres",
        "kmp": "files/course.kmp",
        "posteffect": "files/fx",
    }
    return save_manual(root, chosen)


def save_manual(root: Path, chosen: dict[str, str]) -> Manifest:
    path = root / manifest_io.FILE_NAME
    manifest = manifest_io.load(path)
    parts = {
        part: dataclasses.replace(getattr(manifest.components, part), mode="manual", file=file)
        for part, file in chosen.items()
    }
    manifest = dataclasses.replace(
        manifest,
        components=dataclasses.replace(manifest.components, **parts),
        build=dataclasses.replace(manifest.build, auto_add=False),
    )
    manifest_io.save(manifest, path)
    return manifest


def timed_build(
    root: Path, manifest: Manifest, only: str | None = None
) -> tuple[float, BuildSummary]:
    start = time.perf_counter()
    plan = plan_build(root, manifest, "test", only=only)
    summary = build_project(plan, lambda _e: None, cancel=CancelToken())
    return time.perf_counter() - start, summary


def user_folders(tmp_path: Path) -> dict[str, str]:
    users = tmp_path / "users"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for name in (
        "WIN_PD_OVERRIDE_LOCAL_APPDATA",
        "WIN_PD_OVERRIDE_APPDATA",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
    ):
        env[name] = str(users / name)
    return env


@REAL_TOOLS
def test_a_typical_track_builds_in_under_10_s_and_rebuilds_unchanged_in_under_1_s(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Bench é"
    manifest = typical_track(root)
    fsutil._cached_digest.cache_clear()  # type: ignore[reportPrivateUsage] - a fresh process

    first_s, first = timed_build(root, manifest)
    again_s, again = timed_build(root, manifest)
    assert first.outcome == "succeeded", first
    assert again.ran == () and len(again.skipped) == 8, again

    env = user_folders(tmp_path)
    start = time.perf_counter()
    process = subprocess.run(  # noqa: S603 - our own interpreter
        [sys.executable, "-m", "ctstudio", "build", str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
        check=False,
    )
    process_s = time.perf_counter() - start
    assert process.returncode == 0, process.stdout + process.stderr
    assert "Build succeeded: 8 unchanged" in process.stdout, process.stdout

    print(
        f"typical track: first test build {first_s:.2f} s, no-change rebuild "
        f"{again_s * 1000:.0f} ms in-process, {process_s * 1000:.0f} ms as a process"
    )
    assert first_s < 10.0
    assert again_s < 1.0
    assert process_s < 1.0


def test_a_100_mib_part_is_staged_then_left_alone(tmp_path: Path) -> None:
    root = tmp_path / "Bench é"
    manifest = typical_track(root)
    (root / "files" / "course_model.brres").write_bytes(brres(100 * MIB))
    fsutil._cached_digest.cache_clear()  # type: ignore[reportPrivateUsage]

    first_s, first = timed_build(root, manifest, only="course_model")
    again_s, again = timed_build(root, manifest, only="course_model")
    assert first.ran == ("stage:course_model",), first
    assert again.skipped == ("stage:course_model",), again
    staged = root / ".ctstudio" / "stage" / "course_model.brres"
    assert staged.stat().st_size == 100 * MIB
    print(f"stage 100 MiB: copy {first_s:.2f} s, unchanged {again_s * 1000:.0f} ms")
    assert again_s < 1.0


def test_the_cache_key_of_1000_inputs_cold_and_warm(tmp_path: Path) -> None:
    root = tmp_path / "Bench é"
    folder = root / "inputs"
    folder.mkdir(parents=True)
    paths = []
    for i in range(1000):
        path = folder / f"input {i:04d}.bin"
        path.write_bytes(os.urandom(4 * KIB))
        paths.append(path)
    out = root / "out.bin"

    def run(_ctx: BuildContext) -> NodeResult:
        out.write_bytes(b"made")
        return NodeResult()

    node = Node("many", tuple(paths), (out,), {}, (), frozenset(), 1, run)
    fsutil._cached_digest.cache_clear()  # type: ignore[reportPrivateUsage]
    cache = BuildCache.load(root)

    start = time.perf_counter()
    lookup = cache.check(node, {})
    cold_s = time.perf_counter() - start
    run(None)  # type: ignore[arg-type]
    cache.store(node, lookup)
    cache.save()

    again = BuildCache.load(root)  # as the next build: read from disk
    start = time.perf_counter()
    warm = again.check(node, {})
    warm_s = time.perf_counter() - start
    assert warm.fresh and warm.key == lookup.key
    print(
        f"cache key, 1,000 x 4 KiB inputs: cold {cold_s * 1000:.0f} ms, warm {warm_s * 1000:.0f} ms"
    )
    assert warm_s < 1.0
