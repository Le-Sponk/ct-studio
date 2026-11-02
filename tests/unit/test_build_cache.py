"""P4-T02: the build cache (``core.build.cache``) decides which steps can be skipped.

A step is skipped (a *hit*) when its key matches the one recorded after its last run and
every file it wrote still has the recorded content. The key covers the step's settings,
``impl_version``, the versions of the tools it starts, the files it writes and the content
of every file it reads. Size+mtime unchanged means unchanged, so a no-op build hashes
nothing; a touched file is hashed once and its new mtime recorded.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from ctstudio.core import fsutil
from ctstudio.core.build.cache import CACHE_FILE, BuildCache, Lookup
from ctstudio.core.build.node import BuildContext, Node, NodeResult
from ctstudio.core.errors import BuildError, ProjectError

pytestmark = pytest.mark.timeout(30)
VERSIONS: Mapping[str, str | None] = {"wszst": "2.42a", "blender": "4.2.3"}


def _done(_ctx: BuildContext) -> NodeResult:
    return NodeResult()


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _touch(path: Path) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = tmp_path / "Pistë 日本"
    _write(project / "files" / "course.kmp", b"RKMD kmp")
    _write(project / "files" / "posteffect" / "a.bblm", b"bblm")
    return project


def stage_node(root: Path, **changes: object) -> Node:
    fields: dict[str, object] = {
        "id": "stage:kmp",
        "inputs": (root / "files" / "course.kmp", root / "files" / "posteffect"),
        "outputs": (root / ".ctstudio" / "stage" / "course.kmp", root / ".ctstudio" / "fx"),
        "params": {"mode": "manual"},
        "tools": ("wszst",),
        "resources": frozenset(),
        "impl_version": 1,
        "run": _done,
    }
    fields.update(changes)
    return Node(**fields)  # type: ignore[arg-type] - test helper


def run_step(node: Node) -> None:
    """What the step would write."""
    _write(node.outputs[0], b"staged kmp")
    if len(node.outputs) > 1:
        _write(node.outputs[1] / "a.bblm", b"fx a")
        _write(node.outputs[1] / "sub" / "b.bblm", b"fx b")


def build(cache: BuildCache, node: Node, versions: Mapping[str, str | None] = VERSIONS) -> Lookup:
    """Check, run on a miss and store: one step of a build."""
    lookup = cache.check(node, versions)
    if not lookup.fresh:
        run_step(node)
        cache.store(node, lookup)
    return lookup


@pytest.fixture
def built(root: Path) -> BuildCache:
    cache = BuildCache.load(root)
    assert not build(cache, stage_node(root)).fresh
    return cache


def _no_hashing(path: Path) -> str:
    raise AssertionError(f"hashed {path}")


def _new_process(root: Path) -> BuildCache:
    fsutil._cached_digest.cache_clear()  # type: ignore[reportPrivateUsage] - a fresh process
    return BuildCache.load(root)


# --- hit and miss -----------------------------------------------------------------------------


def test_a_step_never_run_is_a_miss_and_hits_after_it_ran(root: Path, built: BuildCache) -> None:
    again = built.check(stage_node(root), VERSIONS)
    assert again.fresh
    assert again.key == built.check(stage_node(root), VERSIONS).key
    assert len(again.key) == 128 and int(again.key, 16) >= 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("params", {"mode": "manual", "level": 2}),
        ("impl_version", 2),
        ("tools", ("wszst", "blender")),
        ("outputs", (".ctstudio/stage/course.kmp",)),
    ],
)
def test_a_changed_step_is_a_miss(root: Path, built: BuildCache, field: str, value: object) -> None:
    if field == "outputs":  # the same file, without the fx folder
        value = (root / ".ctstudio" / "stage" / "course.kmp",)
    assert not built.check(stage_node(root, **{field: value}), VERSIONS).fresh


def test_a_new_tool_version_is_a_miss_but_other_tools_do_not_matter(
    root: Path, built: BuildCache
) -> None:
    assert built.check(stage_node(root), {**VERSIONS, "blender": "4.5.0"}).fresh
    assert not built.check(stage_node(root), {**VERSIONS, "wszst": "2.43a"}).fresh


def test_a_tool_with_no_version_given_is_refused(root: Path) -> None:
    with pytest.raises(ValueError, match=r"stage:kmp: no version given for wszst"):
        BuildCache.load(root).check(stage_node(root), {"blender": "4.2.3"})


def test_a_tool_whose_version_is_unknown_still_caches(root: Path) -> None:
    cache = BuildCache.load(root)
    unknown: dict[str, str | None] = {"wszst": None}
    build(cache, stage_node(root), unknown)
    assert cache.check(stage_node(root), unknown).fresh
    assert not cache.check(stage_node(root), {"wszst": "2.42a"}).fresh


# --- inputs -----------------------------------------------------------------------------------


def test_an_edited_input_is_a_miss(root: Path, built: BuildCache) -> None:
    (root / "files" / "course.kmp").write_bytes(b"RKMD kmp 2")
    assert not built.check(stage_node(root), VERSIONS).fresh


def test_same_size_new_content_in_an_input_is_a_miss(root: Path, built: BuildCache) -> None:
    kmp = root / "files" / "course.kmp"
    kmp.write_bytes(b"RKMD KMP")
    _touch(kmp)
    assert not built.check(stage_node(root), VERSIONS).fresh


@pytest.mark.parametrize("action", ["add", "remove", "edit", "rename"])
def test_a_change_inside_an_input_folder_is_a_miss(
    root: Path, built: BuildCache, action: str
) -> None:
    folder = root / "files" / "posteffect"
    if action == "add":
        _write(folder / "deeper" / "b.bblm", b"new")
    elif action == "remove":
        (folder / "a.bblm").unlink()
    elif action == "rename":
        (folder / "a.bblm").rename(folder / "b.bblm")
    else:
        (folder / "a.bblm").write_bytes(b"bblm 2")
    assert not built.check(stage_node(root), VERSIONS).fresh


def test_a_missing_input_caches_until_it_appears(root: Path) -> None:
    node = stage_node(root, inputs=(root / "files" / "course.kmp", root / "files" / "later.brres"))
    cache = BuildCache.load(root)
    build(cache, node)
    assert cache.check(node, VERSIONS).fresh
    _write(root / "files" / "later.brres", b"")
    assert not cache.check(node, VERSIONS).fresh


def test_an_input_outside_the_project_is_tracked(root: Path, tmp_path: Path) -> None:
    blend = _write(tmp_path / "elsewhere" / "track.blend", b"BLENDER")
    node = stage_node(root, inputs=(blend,))
    cache = BuildCache.load(root)
    build(cache, node)
    blend.write_bytes(b"BLENDER 2")
    assert not cache.check(node, VERSIONS).fresh


# --- touched but unchanged: the fast path -----------------------------------------------------


def test_an_untouched_project_is_checked_without_hashing(
    root: Path, built: BuildCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    built.save()
    cache = _new_process(root)
    monkeypatch.setattr(fsutil, "hash_file", _no_hashing)
    assert cache.check(stage_node(root), VERSIONS).fresh


def test_a_touched_input_is_a_hit_and_hashed_only_once(
    root: Path, built: BuildCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    built.save()
    _touch(root / "files" / "course.kmp")
    _touch(root / ".ctstudio" / "fx" / "sub" / "b.bblm")
    hashed: list[str] = []
    real = fsutil.hash_file

    def counting(path: Path) -> str:
        hashed.append(path.name)
        return real(path)

    cache = _new_process(root)
    monkeypatch.setattr(fsutil, "hash_file", counting)
    assert cache.check(stage_node(root), VERSIONS).fresh
    assert sorted(hashed) == ["b.bblm", "course.kmp"]
    cache.save()
    monkeypatch.setattr(fsutil, "hash_file", _no_hashing)
    assert _new_process(root).check(stage_node(root), VERSIONS).fresh


# --- outputs ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target", [".ctstudio/stage/course.kmp", ".ctstudio/fx/sub/b.bblm", ".ctstudio/fx"]
)
def test_a_deleted_output_is_a_miss(root: Path, built: BuildCache, target: str) -> None:
    path = root / target
    shutil.rmtree(path) if path.is_dir() else path.unlink()
    assert not built.check(stage_node(root), VERSIONS).fresh


def test_an_edited_output_is_a_miss(root: Path, built: BuildCache) -> None:
    (root / ".ctstudio" / "stage" / "course.kmp").write_bytes(b"hand edit!")
    assert not built.check(stage_node(root), VERSIONS).fresh


def test_an_output_replaced_by_a_folder_is_a_miss(root: Path, built: BuildCache) -> None:
    out = root / ".ctstudio" / "stage" / "course.kmp"
    out.unlink()
    out.mkdir()
    assert not built.check(stage_node(root), VERSIONS).fresh


def test_an_empty_output_folder_deleted_is_a_miss(root: Path) -> None:
    node = stage_node(root)
    cache = BuildCache.load(root)
    lookup = cache.check(node, VERSIONS)
    _write(node.outputs[0], b"staged kmp")
    node.outputs[1].mkdir()
    cache.store(node, lookup)
    assert cache.check(node, VERSIONS).fresh
    node.outputs[1].rmdir()
    assert not cache.check(node, VERSIONS).fresh


def test_storing_a_step_that_did_not_write_its_files_is_an_error(root: Path) -> None:
    cache = BuildCache.load(root)
    node = stage_node(root)
    lookup = cache.check(node, VERSIONS)
    _write(node.outputs[0], b"staged kmp")
    with pytest.raises(BuildError) as info:
        cache.store(node, lookup)
    assert info.value.node_id == "stage:kmp"
    assert "did not write" in info.value.user_message
    assert "fx" in info.value.user_message
    assert not cache.check(node, VERSIONS).fresh


def test_a_lookup_from_another_step_is_refused(root: Path) -> None:
    cache = BuildCache.load(root)
    lookup = cache.check(stage_node(root), VERSIONS)
    other = stage_node(root, id="stage:kcl")
    run_step(other)
    with pytest.raises(ValueError, match=r"stage:kcl: this lookup is for stage:kmp"):
        cache.store(other, lookup)


# --- forgetting -------------------------------------------------------------------------------


def test_invalidate_is_saved(root: Path, built: BuildCache) -> None:
    built.save()
    built.invalidate("stage:kmp")
    built.save()
    assert not _new_process(root).check(stage_node(root), VERSIONS).fresh


def test_a_failed_run_forgets_the_last_good_one(root: Path, built: BuildCache) -> None:
    node = stage_node(root)
    fx = node.outputs[1]
    kept = root.parent / "fx kept"
    shutil.move(fx, kept)
    lookup = built.check(node, VERSIONS)
    with pytest.raises(BuildError):
        built.store(node, lookup)
    shutil.move(kept, fx)
    assert not built.check(node, VERSIONS).fresh, "the step must run again after failing"


def test_invalidate_forgets_one_step(root: Path, built: BuildCache) -> None:
    other = stage_node(root, id="other", outputs=(root / ".ctstudio" / "other.bin",))
    build(built, other)
    built.invalidate("stage:kmp")
    built.invalidate("never-built")
    assert not built.check(stage_node(root), VERSIONS).fresh
    assert built.check(other, VERSIONS).fresh


def test_clear_forgets_every_step(root: Path, built: BuildCache) -> None:
    built.save()
    built.clear()
    assert not built.check(stage_node(root), VERSIONS).fresh
    built.save()
    assert not _new_process(root).check(stage_node(root), VERSIONS).fresh


# --- on disk ----------------------------------------------------------------------------------


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
