"""Integration tests pinning the wszst behaviour spike S1 discovered (P0-T04).

These are not testing our code: they pin the *tool's* behaviour, so that if a future
wszst version changes it, we find out here instead of in a broken adapter. They are the
executable half of docs/dev/SPIKES.md section S1.

Marked `integration` (real tools from .tools/) per docs/process/TESTING_STRATEGY.md.
Run: uv run python -m pytest tests/integration -m integration
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WSZST = REPO_ROOT / ".tools" / "wiimms-szs-tools" / "bin" / "wszst"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "generated"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(120),
    pytest.mark.skipif(not WSZST.exists(), reason="wszst not installed; run bootstrap_tools.py"),
    pytest.mark.skipif(
        not (FIXTURES / "course.kcl").exists(),
        reason="fixtures not generated; run scripts/fixtures/make_fixtures.py",
    ),
]


@pytest.fixture
def work_dir() -> Iterator[Path]:
    """Temp dir on the repo volume (the container mounts /tmp noexec)."""
    base = REPO_ROOT / ".ctstudio" / "pytest-tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def wszst(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [str(WSZST), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture
def track_szs(work_dir: Path) -> Path:
    """An SZS built from the fixture KCL + KMP (no BRRES: those need S2/S3)."""
    stage = work_dir / "stage"
    stage.mkdir()
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(FIXTURES / name, stage / name)
    dest = work_dir / "track.szs"
    proc = wszst("create", stage, "--dest", dest, "--overwrite")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert dest.exists()
    return dest


def test_create_succeeds_without_a_complete_track(track_szs: Path) -> None:
    """`create` does not validate: it builds from whatever is staged (S1)."""
    assert track_szs.stat().st_size > 0


def test_create_accepts_an_empty_directory(work_dir: Path) -> None:
    """Surprising but verified: an empty stage still produces an archive."""
    empty = work_dir / "empty"
    empty.mkdir()
    dest = work_dir / "empty.szs"
    assert wszst("create", empty, "--dest", dest, "--overwrite").returncode == 0
    assert dest.exists(), "create reports success, so it must have written something"


def test_check_exit_code_is_not_a_pass_fail_signal(track_szs: Path, work_dir: Path) -> None:
    """The headline S1 finding, and the one an adapter is most likely to get wrong.

    A track with warnings and a corrupt file must NOT be distinguished by exit code:
    check returns 2 for real tracks and 0 for a file it cannot even parse.
    """
    on_track = wszst("check", track_szs)
    assert on_track.returncode == 2, "expected DIFFER(2) for a real track"
    assert "ERROR #" not in on_track.stdout + on_track.stderr

    corrupt = work_dir / "corrupt.szs"
    corrupt.write_bytes(b"not an archive" * 8)
    on_corrupt = wszst("check", corrupt)
    assert on_corrupt.returncode == 0, "wszst exits 0 on an unparseable file"
    assert "ERROR #" in on_corrupt.stdout + on_corrupt.stderr, (
        "the only reliable failure signal is ERROR # in the output"
    )


def test_check_reports_missing_components_when_a_kmp_is_present(track_szs: Path) -> None:
    proc = wszst("check", track_szs)
    text = proc.stdout + proc.stderr
    for component in ("course_model.brres", "map_model.brres", "vrcorn_model.brres"):
        assert f"Missing file:    ./{component}" in text, component
    assert "=>" in text, "the summary line is what tests and the GUI count on"


def test_check_reports_nothing_missing_without_a_kmp(work_dir: Path) -> None:
    """Missing components are only detected via the KMP, so a KCL-only archive is silent."""
    stage = work_dir / "kcl_only"
    stage.mkdir()
    shutil.copyfile(FIXTURES / "course.kcl", stage / "course.kcl")
    dest = work_dir / "kcl_only.szs"
    assert wszst("create", stage, "--dest", dest, "--overwrite").returncode == 0

    proc = wszst("check", dest)
    assert "Missing file:" not in proc.stdout + proc.stderr


def test_check_severity_prefixes_are_stable(track_szs: Path) -> None:
    """P4 maps these prefixes onto Issue severities."""
    proc = wszst("check", track_szs)
    text = proc.stdout + proc.stderr
    assert "+ WARNING:" in text
    assert "* INFO:" in text


def test_check_rejects_sections_but_analyze_supports_json(track_szs: Path) -> None:
    """Machine-readable output comes from `analyze`, never from `check`."""
    rejected = wszst("check", "--sections", track_szs)
    assert rejected.returncode == 108
    assert "doesn't allow the option --sections" in rejected.stdout + rejected.stderr

    analyzed = wszst("analyze", "--json", track_szs)
    assert analyzed.returncode == 0
    json.loads(analyzed.stdout)  # raises if it is not a single JSON object


def test_analyze_json_carries_what_status_needs(track_szs: Path) -> None:
    """One analyze call should replace check+slots for computing component status."""
    data = json.loads(wszst("analyze", "--json", track_szs).stdout)

    assert data["lap_count"] == 3, "from the fixture STGI"
    assert data["n_ckpt0"] == 1, "exactly one lap-counter checkpoint in the fixture"
    assert data["slot_info"], "slot proposals, same data as `wszst slots`"

    # Empty per-component hashes are how missing components are detected.
    assert data["sha1_kcl"] and data["sha1_kmp"]
    for absent in ("sha1_course", "sha1_vrcorn", "sha1_minimap"):
        assert data[absent] == "", f"{absent} should be empty while the BRRES is missing"


def test_analyze_slot_info_matches_the_slots_command(track_szs: Path) -> None:
    """Justifies skipping `slots` in the adapter."""
    data = json.loads(wszst("analyze", "--json", track_szs).stdout)
    slots_out = wszst("slots", track_szs).stdout
    for slot in data["slot_info"].split(","):
        assert slot in slots_out, slot


def test_compression_levels_trade_size_for_time(work_dir: Path, track_szs: Path) -> None:
    """FAST must be bigger than BEST, and both smaller than uncompressed."""
    stage = work_dir / "stage"
    sizes = {}
    levels = (("fast", "--compr=FAST"), ("best", "--compr=BEST"), ("none", "--no-compress"))
    for label, flag in levels:
        dest = work_dir / f"c_{label}.szs"
        assert wszst("create", stage, "--dest", dest, "--overwrite", flag).returncode == 0
        sizes[label] = dest.stat().st_size

    assert sizes["best"] < sizes["fast"] < sizes["none"], sizes


def test_list_long_shows_the_staged_files_with_magics(track_szs: Path) -> None:
    proc = wszst("list", "--long", track_szs)
    assert proc.returncode == 0
    assert "course.kcl" in proc.stdout
    assert "course.kmp" in proc.stdout
    assert "RKMD" in proc.stdout, "KMP magic, a cheap archive sanity check"
