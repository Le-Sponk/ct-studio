"""P4-T01: the build graph (``core.build.graph``): order, cycles, "rebuild just this".

Steps are linked through files: a step waits for every step that writes a file it reads.
An input inside an output folder, or an input folder that holds an output, counts too. The
order puts every step after the steps it waits for and otherwise keeps the given order, so
the same project always builds in the same order.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import BuildContext, Node, NodeResult
from ctstudio.core.errors import BuildGraphError

pytestmark = pytest.mark.timeout(30)


def _done(_ctx: BuildContext) -> NodeResult:
    return NodeResult()


def step(
    root: Path, node_id: str, reads: tuple[str, ...] = (), writes: tuple[str, ...] = ()
) -> Node:
    return Node(
        id=node_id,
        inputs=tuple(root / p for p in reads),
        outputs=tuple(root / p for p in (writes or (f"out/{node_id.replace(':', '_')}",))),
        params={},
        tools=(),
        resources=frozenset(),
        impl_version=1,
        run=_done,
    )


def ids(graph: BuildGraph) -> list[str]:
    return [node.id for node in graph.nodes]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "Projet é"


# --- order ------------------------------------------------------------------------------------


def test_steps_come_after_the_steps_they_wait_for(root: Path) -> None:
    a = step(root, "a", writes=("stage/a",))
    b = step(root, "b", reads=("stage/a",), writes=("stage/b",))
    c = step(root, "c", reads=("stage/b",), writes=("build/c.szs",))
    graph = BuildGraph(root, [c, a, b])
    assert ids(graph) == ["a", "b", "c"]
    assert graph.needs("c") == ("b",)
    assert graph.needs("b") == ("a",)
    assert graph.needs("a") == ()


def test_otherwise_the_given_order_is_kept(root: Path) -> None:
    x = step(root, "x")
    a = step(root, "a", writes=("stage/a",))
    y = step(root, "y")
    b = step(root, "b", reads=("stage/a",))
    assert ids(BuildGraph(root, [x, b, a, y])) == ["x", "a", "b", "y"]  # b moves only past a
    assert ids(BuildGraph(root, [y, x])) == ["y", "x"]


def test_a_step_waits_for_every_writer_of_what_it_reads_in_build_order(root: Path) -> None:
    kmp = step(root, "stage:kmp", writes=("stage/course.kmp",))
    kcl = step(root, "stage:kcl", writes=("stage/course.kcl",))
    other = step(root, "other", writes=("elsewhere/x",))
    assemble = step(root, "assemble", reads=("stage",), writes=("build/t.szs",))
    graph = BuildGraph(root, [assemble, kmp, other, kcl])
    assert ids(graph) == ["stage:kmp", "other", "stage:kcl", "assemble"]
    assert graph.needs("assemble") == ("stage:kmp", "stage:kcl")


def test_what_a_step_waits_for_is_listed_in_build_order(root: Path) -> None:
    writers = [step(root, f"w{i}", writes=(f"stage/f{i}",)) for i in range(12)]
    reader = step(root, "assemble", reads=("stage",))
    graph = BuildGraph(root, [reader, *reversed(writers)])
    assert graph.needs("assemble") == tuple(f"w{i}" for i in reversed(range(12)))


def test_reading_a_file_inside_an_output_folder_waits_for_it(root: Path) -> None:
    fx = step(root, "stage:posteffect", writes=("stage/posteffect",))
    check = step(root, "check", reads=("stage/posteffect/posteffect.bblm",))
    assert BuildGraph(root, [check, fx]).needs("check") == ("stage:posteffect",)


def test_similar_names_are_not_the_same_file(root: Path) -> None:
    a = step(root, "a", writes=("stage/course",))
    b = step(root, "b", reads=("stage/course.kmp", "stage/courses"))
    assert BuildGraph(root, [b, a]).needs("b") == ()


def test_paths_are_compared_after_dot_dot_is_resolved(root: Path) -> None:
    a = step(root, "a", writes=("stage/course.kmp",))
    b = step(root, "b", reads=("files/../stage/course.kmp",))
    assert BuildGraph(root, [b, a]).needs("b") == ("a",)


def test_inputs_outside_the_project_are_allowed(root: Path, tmp_path: Path) -> None:
    blend = tmp_path / "elsewhere" / "track.blend"
    node = Node("export", (blend,), (root / "exports" / "a.dae",), {}, (), frozenset(), 1, _done)
    assert ids(BuildGraph(root, [node])) == ["export"]


def test_the_same_step_given_twice_is_kept_once(root: Path) -> None:
    export = step(root, "blender_export", reads=("track.blend",), writes=("exports",))
    model = step(root, "model", reads=("exports/course.dae",))
    graph = BuildGraph(
        root, [export, model, step(root, "blender_export", ("track.blend",), ("exports",))]
    )
    assert ids(graph) == ["blender_export", "model"]


# --- refused graphs ---------------------------------------------------------------------------


def test_two_different_steps_with_one_id_are_refused(root: Path) -> None:
    with pytest.raises(ValueError, match=r"two different build steps are called 'a'"):
        BuildGraph(root, [step(root, "a", writes=("x",)), step(root, "a", writes=("y",))])


@pytest.mark.parametrize(
    ("first", "second", "named"),
    [
        ("stage/course.kmp", "stage/course.kmp", "stage/course.kmp"),
        ("stage/posteffect", "stage/posteffect/a.bblm", "stage/posteffect/a.bblm"),
        ("stage/posteffect/a.bblm", "stage/posteffect", "stage/posteffect/a.bblm"),
    ],
)
def test_two_steps_writing_the_same_file_are_refused(
    root: Path, first: str, second: str, named: str
) -> None:
    a, b = step(root, "a", writes=(first,)), step(root, "b", writes=(second,))
    with pytest.raises(ValueError) as info:
        BuildGraph(root, [a, b])
    assert str(info.value) == f"'a' and 'b' both write {(root / named).resolve()}"


def test_writing_outside_the_project_is_refused(root: Path, tmp_path: Path) -> None:
    stray = Node("a", (), (tmp_path / "outside.szs",), {}, (), frozenset(), 1, _done)
    with pytest.raises(ValueError, match=r"'a' writes .*outside\.szs, outside the project"):
        BuildGraph(root, [stray])


# --- cycles -----------------------------------------------------------------------------------


def test_a_cycle_is_named_step_by_step(root: Path) -> None:
    kmp = step(root, "stage:kmp", reads=("build/t.szs",), writes=("stage/course.kmp",))
    assemble = step(root, "assemble", reads=("stage",), writes=("build/t.szs",))
    with pytest.raises(BuildGraphError) as info:
        BuildGraph(root, [step(root, "first"), kmp, assemble])
    assert info.value.user_message == (
        "These build steps wait for each other's files, so none can go first:"
        " stage:kmp → assemble → stage:kmp (each waits for the next)."
    )
    assert info.value.hint == (
        "Choose your own files from outside the build/ and .ctstudio/ folders, then build again."
    )


def test_a_step_that_reads_its_own_output_is_a_cycle(root: Path) -> None:
    whole = step(root, "stage:posteffect", reads=("",), writes=("stage/posteffect",))
    with pytest.raises(BuildGraphError, match=r"stage:posteffect → stage:posteffect \(each"):
        BuildGraph(root, [whole])


def test_of_two_cycles_through_one_step_the_earlier_given_is_named(root: Path) -> None:
    x = step(root, "x", reads=("out/y", "out/z"), writes=("out/x",))
    y = step(root, "y", reads=("out/x",), writes=("out/y",))
    z = step(root, "z", reads=("out/x",), writes=("out/z",))
    with pytest.raises(BuildGraphError, match=r"first: x → y → x \(each"):
        BuildGraph(root, [x, y, z])
    with pytest.raises(BuildGraphError, match=r"first: x → z → x \(each"):
        BuildGraph(root, [x, z, y])


def test_only_the_steps_in_the_cycle_are_named(root: Path) -> None:
    a = step(root, "a", reads=("out/c",), writes=("out/a",))
    b = step(root, "b", reads=("out/a",), writes=("out/b",))
    c = step(root, "c", reads=("out/b",), writes=("out/c",))
    tail = step(root, "tail", reads=("out/b",), writes=("out/tail",))
    with pytest.raises(BuildGraphError, match=r"none can go first: a → c → b → a \(each"):
        BuildGraph(root, [step(root, "first"), tail, a, b, c])


# --- subgraph ---------------------------------------------------------------------------------


@pytest.fixture
def track(root: Path) -> BuildGraph:
    export = step(root, "blender_export", reads=("track.blend",), writes=("exports",))
    model = step(
        root, "course_model", reads=("exports/course.dae",), writes=("stage/course_model.brres",)
    )
    kcl = step(root, "kcl", reads=("exports/course.obj",), writes=("stage/course.kcl",))
    minimap = step(root, "minimap", reads=("stage/course.kcl",), writes=("stage/map_model.brres",))
    kmp = step(root, "stage:kmp", reads=("files/course.kmp",), writes=("stage/course.kmp",))
    assemble = step(root, "assemble", reads=("stage",), writes=("build/beginner_course.szs",))
    return BuildGraph(root, [export, model, kcl, minimap, kmp, assemble])


def test_rebuild_just_this_takes_the_step_and_what_it_waits_for(track: BuildGraph) -> None:
    assert ids(track.subgraph(["minimap"])) == ["blender_export", "kcl", "minimap"]
    assert ids(track.subgraph(["stage:kmp"])) == ["stage:kmp"]
    assert ids(track.subgraph(["stage:kmp", "course_model"])) == [
        "blender_export", "course_model", "stage:kmp"
    ]  # fmt: skip
    assert ids(track.subgraph(["assemble"])) == ids(track)
    assert ids(track.subgraph([])) == []


def test_a_subgraph_is_a_graph_of_its_own(track: BuildGraph) -> None:
    part = track.subgraph(["minimap"])
    assert part.needs("minimap") == ("kcl",)
    assert ids(part.subgraph(["kcl"])) == ["blender_export", "kcl"]


def test_an_unknown_step_suggests_the_closest_ids(track: BuildGraph) -> None:
    with pytest.raises(BuildGraphError) as info:
        track.subgraph(["minmap"])
    assert info.value.user_message == "There is no build step 'minmap'. Did you mean minimap?"
    with pytest.raises(BuildGraphError) as info:
        track.subgraph(["stage:k"])
    assert info.value.user_message.endswith("Did you mean stage:kmp?")
    with pytest.raises(BuildGraphError) as info:
        track.subgraph(["kcll"])
    assert info.value.user_message == "There is no build step 'kcll'. Did you mean kcl?"
    with pytest.raises(BuildGraphError) as info:
        track.subgraph(["zzz"])
    assert info.value.user_message == "There is no build step 'zzz'."
    assert info.value.hint == (
        "The steps are: blender_export, course_model, kcl, minimap, stage:kmp, assemble."
    )


def test_up_to_three_close_ids_are_suggested(root: Path) -> None:
    names = ["stage:kmp", "stage:kml", "stage:kmz", "stage:kmy", "assemble"]
    graph = BuildGraph(root, [step(root, name) for name in names])
    with pytest.raises(BuildGraphError) as info:
        graph.subgraph(["stage:km"])
    assert info.value.user_message.endswith(
        "Did you mean stage:kmz or stage:kmy or stage:kmp?"  # closest first, ties Z to A
    ), info.value.user_message


def test_needs_of_an_unknown_step_is_a_key_error(track: BuildGraph) -> None:
    with pytest.raises(KeyError):
        track.needs("nope")
