"""P2-T02b: version probes run documented commands concurrently and are cached by file."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from version_fakes import counting_spec, direct, fake_executable, runs, spec_running

from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.versions import VersionCache, parse_version, probe_versions, version_argv

pytestmark = pytest.mark.timeout(10)

RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings"


def test_registry_regexes_parse_recorded_real_output() -> None:
    for platform in ("windows", "linux"):
        recording = json.loads(
            (RECORDINGS / f"rszst/5.11.5/{platform}-cli.json").read_text(encoding="utf-8")
        )
        version_run = next(run for run in recording if run["argv"] == ["--version"])
        output = version_run["stdout"] + version_run["stderr"]
        assert parse_version(TOOL_BY_ID["rszst"], output) == "5.11.5", platform
    # Banners recorded in TOOLS.md (P2-T01, Windows 11, real run).
    wiimm = "wszst: Wiimms SZS Tool v2.42a r8989 cygwin64 - Dirk Clemens - 2025-04-13\n"
    assert parse_version(TOOL_BY_ID["wszst"], wiimm) == "2.42a"
    assert parse_version(TOOL_BY_ID["wkclt"], wiimm) is None, "another tool's banner"
    blender = "Blender 5.2.2 LTS\n\tbuild date: 2026-08-25\n"
    assert parse_version(TOOL_BY_ID["blender"], blender) == "5.2.2"
    assert parse_version(TOOL_BY_ID["abmatt"], "Version v1.3.2") is None, "no verified regex"


def test_only_documented_commands_are_probed(tmp_path: Path) -> None:
    exe = tmp_path / "tool"
    assert version_argv(TOOL_BY_ID["wszst"], direct(exe)) == [str(exe), "version"]
    flatpak_exe = Path("/usr/bin/flatpak")
    flatpak = ToolLocation(flatpak_exe, None, "flatpak", "flatpak", "org.blender.Blender")
    assert version_argv(TOOL_BY_ID["blender"], flatpak) == [
        str(flatpak_exe),
        "run",
        "org.blender.Blender",
        "--version",
    ]
    for tool_id in ("brawlcrate", "riistudio", "kmp_cloud", "dolphin", "wine", "abmatt"):
        assert version_argv(TOOL_BY_ID[tool_id], direct(exe)) is None, tool_id
    wine = ToolLocation(exe, None, "path", "wine")
    assert version_argv(TOOL_BY_ID["blender"], wine) is None, "never start Wine for a version"


def test_a_probe_reads_the_version_even_from_a_nonzero_exit(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "tool é 日本")
    # rszst prints its banner and exits -1 (TOOLS.md); the banner is still the version.
    code = "import sys; print('noise'); print('fake v3.4', file=sys.stderr); sys.exit(255)"
    cache = VersionCache(tmp_path / "versions.json")
    [result] = probe_versions([(spec_running(code), direct(exe))], cache=cache)
    assert result.outcome == "probed"
    assert result.location.version == "3.4"
    assert result.location.path == exe


def test_unverified_probes_never_spawn(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "gui")
    counter = tmp_path / "count"
    spec = counting_spec(counter)
    no_regex = replace(spec, version_regex=None)
    no_args = replace(spec, version_args=())
    cache = VersionCache(tmp_path / "versions.json")
    results = probe_versions([(no_regex, direct(exe)), (no_args, direct(exe))], cache=cache)
    assert [r.outcome for r in results] == ["unprobed", "unprobed"]
    assert [r.location.version for r in results] == [None, None]
    assert runs(counter) == 0


def test_probes_run_concurrently_and_a_slow_tool_times_out(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "tools")
    quick = spec_running("import time; time.sleep(1.2); print('fake v1.0')")
    slow = spec_running("import time; time.sleep(30)", tool_id="slow")
    cache = VersionCache(tmp_path / "versions.json")
    started = time.monotonic()
    results = probe_versions(
        [*[(replace(quick, id=f"q{i}"), direct(exe)) for i in range(4)], (slow, direct(exe))],
        cache=cache,
        timeout=3,
    )
    elapsed = time.monotonic() - started
    assert [r.outcome for r in results] == ["probed"] * 4 + ["timeout"]
    assert results[-1].location.version is None
    assert results[-1].detail is not None and "3 s" in results[-1].detail
    assert elapsed < 4.5, f"probes were serialised: {elapsed:.1f} s"


def test_unrecognised_output_and_vanished_files_are_reported(tmp_path: Path) -> None:
    exe = fake_executable(tmp_path / "tools")
    cache = VersionCache(tmp_path / "versions.json")
    garbled = spec_running("print('something else')")
    gone = direct(tmp_path / "missing" / ("fake.exe" if sys.platform == "win32" else "fake"))
    results = probe_versions([(garbled, direct(exe)), (garbled, gone)], cache=cache)
    assert [r.outcome for r in results] == ["unrecognised", "failed"]
    assert results[0].detail == "something else"
    assert results[1].detail is not None and "not found" in results[1].detail
