"""P4-T08 finding on the user's own game files (``realdata``; local only, never on CI).

The track check (P4-T06) could not read Wiimm's report for most real tracks: it only knew
the summary shapes seen on synthetic stages. Here every track of the user's own disc copy
(``local_fixtures/mkwii/files/Race/Course/``, git-ignored) is checked as the build checks
it, and every report must parse. Then one track's own parts are built through ``ctstudio``'s
build with the real tools, in a temporary folder, and the timings printed for BENCHMARKS.md.
Nothing read here is written into the repository.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from ctstudio.core.build.node import Profile
from ctstudio.core.build.project_build import build_project, plan_build
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.core.tools.process import CancelToken, run
from ctstudio.core.tools.wiimm import invoke
from ctstudio.core.validation.wszst_check import parse_check

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

COURSES = ROOT / "local_fixtures" / "mkwii" / "files" / "Race" / "Course"
pytestmark = [
    pytest.mark.realdata,
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.timeout(900),
    pytest.mark.skipif(
        os.name != "nt" or not tp.WSZST.is_file() or not COURSES.is_dir(),
        reason="Requires native Windows Wiimm 2.42a and local_fixtures/mkwii/",
    ),
]
PARTS = {
    "course_model": "course_model.brres",
    "kcl": "course.kcl",
    "minimap": "map_model.brres",
    "skybox": "vrcorn_model.brres",
    "kmp": "course.kmp",
    "posteffect": "posteffect",
}


def test_every_original_track_report_parses() -> None:
    tracks = sorted(COURSES.glob("*.szs"))
    assert len(tracks) >= 32
    for track in tracks:  # as the build's check step runs it (never --brief, which drops the
        # summary when there are no warnings)
        out = invoke(tp.WSZST, ["check", track.name], COURSES, 120, None)
        assert out.exit_code in (0, 2), (track.name, out.exit_code)
        parse_check(out.stdout, track, exit_code=out.exit_code)


def test_a_real_tracks_own_parts_build_and_rebuild(tmp_path: Path) -> None:
    extracted = tmp_path / "x"
    run(
        [str(tp.WSZST), "extract", "castle_course.szs", "--dest", str(extracted), "-q"],
        cwd=COURSES,
        timeout=120,
    )
    root = tmp_path / "Real é"
    Project.create(root, "Real", slot="castle_course").close()
    for name in PARTS.values():
        source = extracted / name
        if source.is_dir():
            shutil.copytree(source, root / "files" / name)
        else:
            shutil.copyfile(source, root / "files" / name)
    path = root / manifest_io.FILE_NAME
    manifest = manifest_io.load(path)
    chosen = {
        part: dataclasses.replace(
            getattr(manifest.components, part), mode="manual", file=f"files/{name}"
        )
        for part, name in PARTS.items()
    }
    manifest = dataclasses.replace(
        manifest,
        components=dataclasses.replace(manifest.components, **chosen),
        build=dataclasses.replace(manifest.build, auto_add=False),
    )
    manifest_io.save(manifest, path)

    times: dict[str, float] = {}
    ran: dict[str, tuple[str, ...]] = {}
    runs: tuple[tuple[str, Profile], ...] = (
        ("test", "test"),
        ("no change", "test"),
        ("release", "release"),
    )
    for label, profile in runs:
        start = time.perf_counter()
        summary = build_project(
            plan_build(root, manifest, profile), lambda _e: None, cancel=CancelToken()
        )
        times[label] = time.perf_counter() - start
        assert summary.outcome == "succeeded", (label, summary)
        ran[label] = summary.ran
    assert ran["no change"] == ()
    assert ran["release"] == ("assemble", "validate")  # only packing differs for a release
    print("castle_course parts: " + ", ".join(f"{k} {v:.2f} s" for k, v in times.items()))
    assert times["test"] < 10.0 and times["no change"] < 1.0
