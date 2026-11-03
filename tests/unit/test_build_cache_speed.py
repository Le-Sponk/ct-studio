"""P4-T08: a no-change check of many inputs does little work per file (``core.build.cache``).

The benchmark (``tests/benchmarks/test_build_speed.py``) found a warm check of 1,000 inputs
took ~0.94 s on Windows, almost all of it in ``Path.resolve`` (five per file). These tests
pin the fix: each input path is resolved once, the project folder once per cache, and the
keys are still exactly what ``input_key`` gives.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from ctstudio.core import fsutil
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.node import BuildContext, Node, NodeResult
from ctstudio.core.components.state import input_key
from ctstudio.core.fsutil import Fingerprint, hash_file

pytestmark = pytest.mark.timeout(30)


def _done(_ctx: BuildContext) -> NodeResult:
    return NodeResult()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = tmp_path / "Pistë 日本"
    project.mkdir()
    return project


def _node(root: Path, count: int) -> Node:
    folder = root / "inputs"
    folder.mkdir()
    paths = []
    for i in range(count):
        path = folder / f"in {i}.bin"
        path.write_bytes(bytes([i]) * (i + 1))
        paths.append(path)
    (folder / "sub").mkdir()
    (folder / "sub" / "deep.bin").write_bytes(b"deep")
    out = root / "out.bin"
    out.write_bytes(b"made")
    return Node("n", (*paths, folder / "sub"), (out,), {}, (), frozenset(), 1, _done)


def _resolves(monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    counts: Counter[str] = Counter()
    real = Path.resolve

    def counting(self: Path, strict: bool = False) -> Path:
        counts[self.name] += 1
        return real(self, strict)

    monkeypatch.setattr(Path, "resolve", counting)
    return counts


def _warm(root: Path, node: Node) -> BuildCache:
    cache = BuildCache.load(root)
    cache.store(node, cache.check(node, {}))
    cache.save()
    return BuildCache.load(root)


def test_a_warm_check_resolves_each_input_once_and_the_project_once(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = _node(root, 20)
    again = _warm(root, node)
    fsutil._cached_digest.cache_clear()  # type: ignore[reportPrivateUsage] - prove no hashing
    counts = _resolves(monkeypatch)
    lookup = again.check(node, {})
    assert lookup.fresh
    files = [f"in {i}.bin" for i in range(20)] + ["deep.bin"]
    assert {name: counts[name] for name in files} == dict.fromkeys(files, 1)
    assert counts["out.bin"] == 1
    assert counts[root.name] <= 1  # once per cache, maybe before this check
    assert fsutil._cached_digest.cache_info().misses == 0  # type: ignore[reportPrivateUsage]


def test_the_keys_are_still_what_input_key_gives(root: Path) -> None:
    node = _node(root, 3)
    cache = BuildCache.load(root)
    lookup = cache.check(node, {})
    folder = root / "inputs"
    expected = {input_key(root, folder / f"in {i}.bin") for i in range(3)}
    expected.add(input_key(root, folder / "sub" / "deep.bin"))
    assert set(lookup.inputs) == expected
    assert expected == {f"inputs/in {i}.bin" for i in range(3)} | {"inputs/sub/deep.bin"}


def test_an_input_outside_the_project_keeps_its_full_path(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere é" / "shared.bin"
    outside.parent.mkdir()
    outside.write_bytes(b"shared")
    out = root / "out.bin"
    node = Node("n", (outside,), (out,), {}, (), frozenset(), 1, _done)
    lookup = BuildCache.load(root).check(node, {})
    assert set(lookup.inputs) == {str(outside.resolve())}


def test_a_project_folder_reached_through_dots_gives_the_same_keys(root: Path) -> None:
    node = _node(root, 2)
    plain = BuildCache.load(root).check(node, {})
    dotted = root / ".." / root.name
    assert BuildCache.load(dotted).check(node, {}).inputs == plain.inputs


def test_a_folder_inputs_key_names_each_file_with_its_own_content(root: Path) -> None:
    """The key's exact material (cache.json compatibility): a folder is ``{name: digest}``."""
    folder = root / "fx"
    folder.mkdir()
    for name, data in (("a.bin", b"one"), ("b.bin", b"two"), ("c.bin", b"three")):
        (folder / name).write_bytes(data)
    out = root / "out.bin"
    node = Node("n", (folder,), (out,), {"k": 1}, (), frozenset(), 3, _done)
    material = {
        "params": {"k": 1},
        "impl_version": 3,
        "tools": {},
        "inputs": [{name: hash_file(folder / name) for name in ("a.bin", "b.bin", "c.bin")}],
    }
    text = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = hashlib.blake2b(text.encode("utf-8")).hexdigest()
    assert BuildCache.load(root).check(node, {}).key == expected


def test_a_fingerprint_resolves_its_path_unless_told_it_already_is(root: Path) -> None:
    (root / "a.bin").write_bytes(b"a")
    dotted = root / "sub" / ".." / "a.bin"
    (root / "sub").mkdir()
    assert Fingerprint.from_path(dotted).path == (root / "a.bin").resolve()
    assert Fingerprint.from_path(dotted, resolved=True).path == dotted
