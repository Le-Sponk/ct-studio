"""P4-T02: ``.ctstudio/cache.json`` on disk: restart, moved project, format, damage.

The cache file is app-managed and safe to delete; missing or damaged reads as "nothing
cached", and it is written atomically only when something changed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from test_build_cache import VERSIONS, _new_process, _write, stage_node
from test_build_cache import built as built  # fixture
from test_build_cache import root as root  # fixture

from ctstudio.core.build.cache import CACHE_FILE, BuildCache
from ctstudio.core.errors import ProjectError

pytestmark = pytest.mark.timeout(30)


def test_the_cache_survives_a_restart_and_a_moved_project(
    root: Path, built: BuildCache, tmp_path: Path
) -> None:
    built.save()
    assert _new_process(root).check(stage_node(root), VERSIONS).fresh
    moved = tmp_path / "moved here"
    shutil.copytree(root, moved)
    assert _new_process(moved).check(stage_node(moved), VERSIONS).fresh


def test_cache_json_is_readable_and_project_relative(root: Path, built: BuildCache) -> None:
    built.save()
    data = json.loads((root / CACHE_FILE).read_text(encoding="utf-8"))
    assert data["format"] == 1
    entry = data["nodes"]["stage:kmp"]
    assert entry["key"] == built.check(stage_node(root), VERSIONS).key
    assert sorted(entry["inputs"]) == ["files/course.kmp", "files/posteffect/a.bblm"]
    assert sorted(entry["outputs"]) == [
        ".ctstudio/fx/a.bblm",
        ".ctstudio/fx/sub/b.bblm",
        ".ctstudio/stage/course.kmp",
    ]
    assert set(entry["inputs"]["files/course.kmp"]) == {"size", "mtime_ns", "digest"}


def test_an_untouched_hit_does_not_rewrite_the_cache(root: Path, built: BuildCache) -> None:
    built.save()
    cache = BuildCache.load(root)
    (root / CACHE_FILE).write_text("sentinel", encoding="utf-8")
    assert cache.check(stage_node(root), VERSIONS).fresh
    cache.save()
    assert (root / CACHE_FILE).read_text(encoding="utf-8") == "sentinel"


def test_save_writes_only_when_something_changed(root: Path, built: BuildCache) -> None:
    BuildCache.load(root).save()
    assert not (root / CACHE_FILE).exists(), "nothing recorded, nothing written"
    built.save()
    (root / CACHE_FILE).write_text("{}", encoding="utf-8")  # damaged: loads as empty
    cache = BuildCache.load(root)
    assert cache.check(stage_node(root), VERSIONS).fresh is False
    cache.save()
    assert (root / CACHE_FILE).read_text(encoding="utf-8") == "{}", "a lookup alone saves nothing"
    built.save()
    assert (root / CACHE_FILE).read_text(encoding="utf-8") == "{}", "already saved"


@pytest.mark.parametrize(
    "content",
    [
        b"\xff\xfe not json",
        b"[]",
        b'{"format": 2, "nodes": {}}',
        b'{"format": 1, "nodes": {"a": {"key": 5, "inputs": {}, "outputs": {}}}}',
        b'{"format": 1, "nodes": {"a": {"key": "k", "inputs": {"x": {"size": 1}}, "outputs": {}}}}',
        b'{"format": 1}',
    ],
)
def test_a_damaged_cache_reads_as_empty(
    root: Path, content: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    _write(root / CACHE_FILE, content)
    cache = BuildCache.load(root)
    assert not cache.check(stage_node(root), VERSIONS).fresh
    assert "cache.json is damaged" in caplog.text


def test_an_unreadable_cache_is_a_project_error(root: Path) -> None:
    (root / CACHE_FILE).mkdir(parents=True)
    with pytest.raises(ProjectError, match=r"Could not read cache\.json"):
        BuildCache.load(root)
