"""P2-T02b: the persistent version cache is keyed by executable identity and invalidated."""

from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path

import pytest
from version_fakes import counting_spec, direct, fake_executable, runs

from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.versions import VersionCache, probe_versions

pytestmark = pytest.mark.timeout(10)


def bump_mtime(path: Path) -> None:
    stat = path.stat()
    later = stat.st_mtime_ns + 5_000_000_000
    os.utime(path, ns=(stat.st_atime_ns, later))


def test_a_second_run_reuses_the_persisted_version_without_spawning(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "tool é")
    counter = tmp_path / "count"
    spec = counting_spec(counter)
    store = tmp_path / "config é" / "tool-versions.json"
    [first] = probe_versions([(spec, direct(exe))], cache=VersionCache(store))
    assert (first.outcome, first.location.version, runs(counter)) == ("probed", "1.2", 1)
    # A new cache object reads the file written by the first: persistence across sessions.
    [second] = probe_versions([(spec, direct(exe))], cache=VersionCache(store))
    assert (second.outcome, second.location.version, runs(counter)) == ("cached", "1.2", 1)
    entries = json.loads(store.read_text(encoding="utf-8"))["entries"]
    assert len(entries) == 1
    assert next(iter(entries.values()))["version"] == "1.2"


def test_a_changed_mtime_or_size_or_force_triggers_a_new_probe(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "tool")
    counter = tmp_path / "count"
    spec = counting_spec(counter)
    cache = VersionCache(tmp_path / "versions.json")
    probe_versions([(spec, direct(exe))], cache=cache)
    bump_mtime(exe)
    [after_touch] = probe_versions([(spec, direct(exe))], cache=cache)
    assert after_touch.outcome == "probed" and runs(counter) == 2
    mtime = exe.stat().st_mtime_ns
    with exe.open("ab") as stream:
        stream.write(b"\0")  # same mtime, different size: an in-place update
    os.utime(exe, ns=(mtime, mtime))
    [after_resize] = probe_versions([(spec, direct(exe))], cache=cache)
    assert after_resize.outcome == "probed" and runs(counter) == 3
    [forced] = probe_versions([(spec, direct(exe))], cache=cache, force=True)
    assert forced.outcome == "probed" and runs(counter) == 4
    [reused] = probe_versions([(spec, direct(exe))], cache=cache)
    assert reused.outcome == "cached" and runs(counter) == 4


def test_failures_are_not_cached(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "tool")
    counter = tmp_path / "count"
    spec = counting_spec(counter, body="print('no version here')")
    cache = VersionCache(tmp_path / "versions.json")
    outcomes = [probe_versions([(spec, direct(exe))], cache=cache)[0].outcome for _ in range(2)]
    assert outcomes == ["unrecognised", "unrecognised"]
    assert runs(counter) == 2


def test_a_different_tool_or_path_does_not_share_an_entry(tmp_path: Path) -> None:
    first = fake_executable(tmp_path / "one")
    second = fake_executable(tmp_path / "two")
    counter = tmp_path / "count"
    spec = counting_spec(counter)
    cache = VersionCache(tmp_path / "versions.json")
    probe_versions([(spec, direct(first))], cache=cache)
    probe_versions([(spec, direct(second))], cache=cache)
    other = replace(spec, id="other")
    probe_versions([(other, direct(first))], cache=cache)
    assert runs(counter) == 3


def test_flatpak_entries_are_keyed_by_application_identity(tmp_path: Path) -> None:
    launcher = fake_executable(tmp_path / "flatpak")
    cache = VersionCache(tmp_path / "versions.json")
    blender = ToolLocation(launcher, None, "flatpak", "flatpak", "org.blender.Blender")
    other = ToolLocation(launcher, None, "flatpak", "flatpak", "org.example.Other")
    assert cache.key("blender", blender) != cache.key("blender", other)
    # The flatpak launcher's own mtime says nothing about the application: not in the key.
    key = cache.key("blender", blender)
    bump_mtime(launcher)
    assert cache.key("blender", blender) == key


def test_corrupt_or_foreign_cache_files_are_ignored_and_rewritten(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "tool")
    counter = tmp_path / "count"
    spec = counting_spec(counter)
    for content in ("{not json", '{"format": 99, "entries": {}}', "[1, 2]", '{"format": 1}'):
        store = tmp_path / f"versions-{runs(counter)}.json"
        store.write_text(content, encoding="utf-8")
        [result] = probe_versions([(spec, direct(exe))], cache=VersionCache(store))
        assert result.outcome == "probed", content
        assert json.loads(store.read_text(encoding="utf-8"))["format"] == 1


def test_an_unwritable_cache_never_hides_the_probed_version(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "tool")
    blocker = tmp_path / "not a folder"
    blocker.write_text("file", encoding="utf-8")
    cache = VersionCache(blocker / "versions.json")
    [result] = probe_versions([(counting_spec(tmp_path / "count"), direct(exe))], cache=cache)
    assert result.outcome == "probed"
    assert result.location.version == "1.2"
    assert cache.save_error is not None


def test_concurrent_probes_store_every_result(tmp_path: Path) -> None:
    folders = [fake_executable(tmp_path / f"tool {i}") for i in range(6)]
    counter = tmp_path / "count"
    spec = counting_spec(counter, body="import time; time.sleep(0.3); print('fake v2.0')")
    store = tmp_path / "versions.json"
    started = time.monotonic()
    probe_versions([(spec, direct(exe)) for exe in folders], cache=VersionCache(store))
    assert time.monotonic() - started < 6
    assert len(json.loads(store.read_text(encoding="utf-8"))["entries"]) == 6
    results = probe_versions([(spec, direct(exe)) for exe in folders], cache=VersionCache(store))
    assert {r.outcome for r in results} == {"cached"}
