"""P4-T07b exit check: ``ctstudio build`` as a real process, with the real Wiimm 2.42a tools.

A synthetic all-manual project (the committed synthetic KCL and KMP, stand-in BRRES and a
stand-in post-effect file) is built from a separate process exactly as a user would run it.
CT Studio finds the real tools in this checkout's ``.tools/``; settings, logs and caches live
in throwaway user folders. Every ``--json-events`` line is checked against the schema in
``docs/dev/CLI.md``.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from ctstudio.core.project import manifest_io

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "unit"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above
from json_schema_check import errors, schema_from_doc  # type: ignore[reportMissingImports]

KEPT = ROOT / "tests" / "fakes" / "recordings" / "wszst" / "2.42a" / "inputs"
SCHEMA = schema_from_doc(ROOT / "docs" / "dev" / "CLI.md", "build-events-schema")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        not tp.WSZST.is_file() or not tp.WKMPT.is_file(), reason="Requires Wiimm 2.42a"
    ),
]
BRRES = b"bres\xfe\xff\x00\x00" + struct.pack(">IHH", 0x80, 0x10, 1) + b"root" + bytes(0x6C)
FILES = {
    "course_model": "files/course_model.brres",
    "kcl": "files/course.kcl",
    "minimap": "files/map_model.brres",
    "skybox": "files/vrcorn_model.brres",
    "kmp": "files/course.kmp",
    "posteffect": "files/fx",
}


def _environment(tmp_path: Path) -> dict[str, str]:
    users = tmp_path / "user folders é"
    env = dict(os.environ)
    env.update(
        PYTHONIOENCODING="utf-8",
        WIN_PD_OVERRIDE_LOCAL_APPDATA=str(users / "local"),
        WIN_PD_OVERRIDE_APPDATA=str(users / "roaming"),
        XDG_CONFIG_HOME=str(users / "config"),
        XDG_DATA_HOME=str(users / "data"),
        XDG_CACHE_HOME=str(users / "cache"),
        XDG_STATE_HOME=str(users / "state"),
    )
    return env


def _ctstudio(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - our own interpreter
        [sys.executable, "-m", "ctstudio", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=240,
        check=False,
    )


def _project(env: dict[str, str], tmp_path: Path) -> Path:
    root = tmp_path / "Pistë 日本"
    made = _ctstudio(env, "new", str(root), "--name", "Pistë", "--slot", "castle_course")
    assert made.returncode == 0, made.stderr
    (root / "files" / "fx").mkdir(parents=True)
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(KEPT / name, root / "files" / name)
    for name in ("course_model.brres", "map_model.brres", "vrcorn_model.brres"):
        (root / "files" / name).write_bytes(BRRES)
    (root / "files" / "fx" / "posteffect.bblm").write_bytes(
        b"PBLM" + struct.pack(">I", 0x50) + bytes(0x48)
    )
    _set_files(root, FILES)
    return root


def _set_files(root: Path, files: dict[str, str]) -> None:
    """Every part in ``files`` manual with that file, the rest as they were; auto-add off."""
    path = root / manifest_io.FILE_NAME
    manifest = manifest_io.load(path)
    parts = {
        part: dataclasses.replace(getattr(manifest.components, part), mode="manual", file=file)
        for part, file in files.items()
    }
    manifest = dataclasses.replace(
        manifest,
        components=dataclasses.replace(manifest.components, **parts),
        build=dataclasses.replace(manifest.build, auto_add=False),
    )
    manifest_io.save(manifest, path)


def test_build_then_build_again_then_json_events(tmp_path: Path) -> None:
    env = _environment(tmp_path)
    root = _project(env, tmp_path)

    first = _ctstudio(env, "build", str(root))
    assert first.returncode == 0, first.stdout + first.stderr
    assert first.stdout.startswith(
        "Building Pistë, replacing Mario Circuit (Flower Cup, track 1): test build, 8 steps\n"
    )
    assert "  done       Pack the track (" in first.stdout
    assert "Track: build/castle_course.szs\n" in first.stdout
    assert (root / "build" / "castle_course.szs").is_file()

    again = _ctstudio(env, "build", str(root), "--json-events")
    assert again.returncode == 0, again.stderr
    events = [json.loads(line) for line in again.stdout.splitlines()]
    assert all(errors(event, SCHEMA) == [] for event in events), again.stdout
    assert events[0]["event"] == "build_started" and len(events[0]["steps"]) == 8
    [end] = [e for e in events if e["event"] == "build_finished"]
    assert end["outcome"] == "succeeded" and end["ran"] == [] and len(end["skipped"]) == 8
    assert events[-1] is end


def test_json_output_closed_by_its_reader_stops_without_a_traceback(tmp_path: Path) -> None:
    env = _environment(tmp_path)
    root = _project(env, tmp_path)
    process = subprocess.Popen(  # noqa: S603 - our own interpreter
        [sys.executable, "-m", "ctstudio", "build", str(root), "--json-events"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert process.stdout is not None and process.stderr is not None
    try:
        first = process.stdout.readline()
        assert json.loads(first)["event"] == "build_started"
        process.stdout.close()  # as when a pipe's reader stops after its first line
        error = process.stderr.read()
        assert process.wait(timeout=60) == 1
        assert "The output was closed, so the build was stopped." in error
        assert "Traceback" not in error
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_a_wrong_file_fails_the_build_with_exit_1(tmp_path: Path) -> None:
    env = _environment(tmp_path)
    root = _project(env, tmp_path)
    (root / "files" / "course.kcl").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(0x40))

    failed = _ctstudio(env, "build", str(root), "--json-events")
    assert failed.returncode == 1, failed.stderr
    events = [json.loads(line) for line in failed.stdout.splitlines()]
    assert all(errors(event, SCHEMA) == [] for event in events), failed.stdout
    [stop] = [e for e in events if e["event"] == "step_failed"]
    assert stop["step"] == "stage:kcl" and not stop["cancelled"]
    assert "wrong type" in stop["message"]
    assert events[-1]["outcome"] == "failed" and "assemble" in events[-1]["not_run"]


def test_only_one_part_then_a_release_build(tmp_path: Path) -> None:
    env = _environment(tmp_path)
    root = _project(env, tmp_path)
    only = _ctstudio(env, "build", str(root), "--only", "kcl")
    assert only.returncode == 0, only.stderr
    assert "Track:" not in only.stdout and "Build succeeded: 1 done in" in only.stdout
    bad = _ctstudio(env, "build", str(root), "--only", "objects")
    assert bad.returncode == 2 and "invalid choice: 'objects'" in bad.stderr

    # The stand-ins are complete, so the check finds warnings only: a release build passes.
    release = _ctstudio(env, "build", str(root), "--release")
    assert release.returncode == 0, release.stdout + release.stderr
    assert ": release build, 8 steps\n" in release.stdout
    assert "  unchanged  Copy Collision\n" in release.stdout
    assert "Found while building:\n" in release.stdout
    assert "  warning  Missing bones 'posLD' and 'posRU' in minimap MDL.\n" in release.stdout
    assert "Track: build/castle_course.szs\n" in release.stdout
