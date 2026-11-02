"""P4-T01: the build graph made from a project (``graph.from_manifest``).

Every part CT Studio puts into the track is made the way its mode in ``ctstudio.toml`` says.
The caller supplies ``make_part(spec, mode)``, which returns that part's steps or ``None`` when
CT Studio cannot make it that way yet; the finishing steps (assemble, check) come last.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.build.graph import BuildGraph, from_manifest
from ctstudio.core.build.node import BuildContext, Node, NodeResult
from ctstudio.core.components.registry import ComponentSpec
from ctstudio.core.errors import BuildGraphError
from ctstudio.core.project.manifest import Components, Kcl, Manifest, ProjectInfo

pytestmark = pytest.mark.timeout(30)


def _done(_ctx: BuildContext) -> NodeResult:
    return NodeResult()


def _node(root: Path, node_id: str, reads: tuple[str, ...], writes: tuple[str, ...]) -> Node:
    inputs, outputs = tuple(root / p for p in reads), tuple(root / p for p in writes)
    return Node(node_id, inputs, outputs, {}, (), frozenset(), 1, _done)


def _stage(root: Path, spec: ComponentSpec) -> Node:
    return _node(root, f"stage:{spec.id}", (f"files/{spec.id}",), (f".ctstudio/stage/{spec.id}",))


def test_each_made_part_is_asked_for_in_dashboard_order(tmp_path: Path) -> None:
    asked: list[tuple[str, str]] = []

    def make_part(spec: ComponentSpec, mode: str) -> tuple[Node, ...]:
        asked.append((spec.id, mode))
        return (_stage(tmp_path, spec),)

    assemble = _node(tmp_path, "assemble", (".ctstudio/stage",), ("build/beginner_course.szs",))
    graph = from_manifest(tmp_path, Manifest(project=ProjectInfo(name="T")), make_part, [assemble])
    assert asked == [
        ("course_model", "auto"),
        ("kcl", "auto"),
        ("minimap", "auto"),
        ("skybox", "auto"),
        ("kmp", "manual"),
        ("posteffect", "template"),
    ], "objects and track info put no file of their own into the track"
    assert isinstance(graph, BuildGraph)
    assert [n.id for n in graph.nodes][-1] == "assemble"
    assert len(graph.needs("assemble")) == 6


def test_the_mode_comes_from_the_manifest(tmp_path: Path) -> None:
    asked: dict[str, str] = {}

    def make_part(spec: ComponentSpec, mode: str) -> tuple[Node, ...]:
        asked[spec.id] = mode
        return (_stage(tmp_path, spec),)

    manifest = Manifest(
        project=ProjectInfo(name="T"), components=Components(kcl=Kcl(mode="manual"))
    )
    from_manifest(tmp_path, manifest, make_part)
    assert asked["kcl"] == "manual"
    assert asked["course_model"] == "auto"


def test_a_step_shared_by_parts_runs_once(tmp_path: Path) -> None:
    export = _node(tmp_path, "blender_export", ("track.blend",), (".ctstudio/exports",))

    def make_part(spec: ComponentSpec, mode: str) -> tuple[Node, ...]:
        if mode == "auto" and spec.id in ("course_model", "kcl", "skybox"):
            made = _node(tmp_path, spec.id, (".ctstudio/exports",), (f".ctstudio/stage/{spec.id}",))
            return (export, made)
        return (_stage(tmp_path, spec),)

    graph = from_manifest(tmp_path, Manifest(project=ProjectInfo(name="T")), make_part)
    order = [n.id for n in graph.nodes]
    assert order.count("blender_export") == 1
    assert order.index("blender_export") < order.index("course_model")


def test_a_part_that_needs_no_step_in_its_mode_is_left_out(tmp_path: Path) -> None:
    def make_part(spec: ComponentSpec, mode: str) -> tuple[Node, ...]:
        return () if spec.id == "posteffect" else (_stage(tmp_path, spec),)

    graph = from_manifest(tmp_path, Manifest(project=ProjectInfo(name="T")), make_part)
    assert "stage:posteffect" not in [n.id for n in graph.nodes]
    assert len(graph.nodes) == 5


def test_a_mode_ct_studio_cannot_make_yet_is_explained(tmp_path: Path) -> None:
    def make_part(spec: ComponentSpec, mode: str) -> tuple[Node, ...] | None:
        return None if mode == "auto" else (_stage(tmp_path, spec),)

    with pytest.raises(BuildGraphError) as info:
        from_manifest(tmp_path, Manifest(project=ProjectInfo(name="T")), make_part)
    assert info.value.user_message == "CT Studio cannot make the Course model in auto mode yet."
    assert info.value.hint == "Set its mode to manual in ctstudio.toml."


def test_a_part_with_no_other_mode_says_so(tmp_path: Path) -> None:
    def make_part(spec: ComponentSpec, mode: str) -> tuple[Node, ...] | None:
        return None if spec.id == "kmp" else (_stage(tmp_path, spec),)

    with pytest.raises(BuildGraphError) as info:
        from_manifest(tmp_path, Manifest(project=ProjectInfo(name="T")), make_part)
    assert info.value.user_message == "CT Studio cannot make the Course data in manual mode yet."
    assert info.value.hint == "A newer CT Studio may be able to; check for an update."


def test_a_skybox_with_two_other_modes_names_both(tmp_path: Path) -> None:
    def make_part(spec: ComponentSpec, mode: str) -> tuple[Node, ...] | None:
        return None if spec.id == "skybox" else (_stage(tmp_path, spec),)

    with pytest.raises(BuildGraphError) as info:
        from_manifest(tmp_path, Manifest(project=ProjectInfo(name="T")), make_part)
    assert info.value.user_message == "CT Studio cannot make the Skybox in auto mode yet."
    assert info.value.hint == "Set its mode to template or manual in ctstudio.toml."


def test_steps_from_a_cycle_through_the_users_files_are_refused(tmp_path: Path) -> None:
    """A manual KMP chosen from build/ would wait for the track it goes into."""

    def make_part(spec: ComponentSpec, mode: str) -> tuple[Node, ...]:
        if spec.id == "kmp":
            reads = ("build/beginner_course.szs",)
            return (_node(tmp_path, "stage:kmp", reads, (".ctstudio/stage/course.kmp",)),)
        return (_stage(tmp_path, spec),)

    assemble = _node(tmp_path, "assemble", (".ctstudio/stage",), ("build/beginner_course.szs",))
    manifest = Manifest(project=ProjectInfo(name="T"))
    with pytest.raises(BuildGraphError, match=r"stage:kmp → assemble → stage:kmp"):
        from_manifest(tmp_path, manifest, make_part, [assemble])
