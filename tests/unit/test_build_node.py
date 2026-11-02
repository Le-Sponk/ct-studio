"""P4-T01: a build step (``core.build.node.Node``) and what it is checked for on creation.

A node says which files it reads (``inputs``; a folder means every file in it), which it
writes (``outputs``), its settings (``params``, plain JSON so they can be part of a cache
key), the tools it starts, the shared resources it must hold alone and its ``impl_version``
(raised when its code changes what it makes). Mistakes in a node are programming errors and
raise ``ValueError`` naming the node.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from ctstudio.core.build.node import BuildContext, Node, NodeResult
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.validation.issues import Issue

pytestmark = pytest.mark.timeout(30)


def _done(_ctx: BuildContext) -> NodeResult:
    return NodeResult()


def make(root: Path, node_id: str = "stage:kmp", /, **changes: object) -> Node:
    fields: dict[str, object] = {
        "id": node_id,
        "inputs": (root / "files" / "course.kmp",),
        "outputs": (root / ".ctstudio" / "stage" / "course.kmp",),
        "params": {"mode": "manual"},
        "tools": (),
        "resources": frozenset({"stage:course.kmp"}),
        "impl_version": 1,
        "run": _done,
    }
    fields.update(changes)
    return Node(**fields)  # type: ignore[arg-type] - tests pass wrong types on purpose


def test_a_node_keeps_what_it_was_given(tmp_path: Path) -> None:
    node = make(tmp_path, tools=["wszst"], inputs=[tmp_path / "a"], resources={"blender"})
    assert node.id == "stage:kmp"
    assert node.inputs == (tmp_path / "a",)
    assert node.outputs == (tmp_path / ".ctstudio" / "stage" / "course.kmp",)
    assert node.tools == ("wszst",)
    assert type(node.tools) is tuple
    assert node.resources == frozenset({"blender"})
    assert type(node.resources) is frozenset
    assert node.impl_version == 1


def test_params_are_a_frozen_copy(tmp_path: Path) -> None:
    given: dict[str, object] = {"mode": "manual", "args": ["-q"], "level": {"n": 1}}
    node = make(tmp_path, params=given)
    given["mode"] = "auto"
    assert isinstance(given["args"], list)
    given["args"].append("--x")
    assert isinstance(given["level"], dict)
    given["level"]["n"] = 2
    assert dict(node.params) == {"mode": "manual", "args": ["-q"], "level": {"n": 1}}
    with pytest.raises(TypeError):
        node.params["mode"] = "auto"  # type: ignore[index] - read-only on purpose


def test_nodes_compare_by_value_not_by_their_run_function(tmp_path: Path) -> None:
    def other(_ctx: BuildContext) -> NodeResult:
        return NodeResult()

    assert make(tmp_path) == make(tmp_path, run=other)
    assert make(tmp_path) != make(tmp_path, params={"mode": "auto"})
    assert make(tmp_path) != make(tmp_path, impl_version=2)


def test_run_gets_the_context_and_returns_issues(tmp_path: Path) -> None:
    seen: list[BuildContext] = []
    issue = Issue("warning", "kmp", "kmp.checkpoint", "No checkpoints.", None, "ctstudio")

    def run(ctx: BuildContext) -> NodeResult:
        seen.append(ctx)
        ctx.log("staged course.kmp")
        return NodeResult(issues=(issue,))

    logged: list[str] = []
    ctx = BuildContext(
        root=tmp_path,
        manifest=Manifest(project=ProjectInfo(name="T")),
        profile="test",
        tools={},
        log=logged.append,
    )
    assert make(tmp_path, run=run).run(ctx) == NodeResult(issues=(issue,))
    assert seen == [ctx]
    assert logged == ["staged course.kmp"]


@pytest.mark.parametrize("node_id", ["", "Stage", "stage kmp", "1stage", "stage/kmp", "-x"])
def test_a_bad_id_is_refused(tmp_path: Path, node_id: str) -> None:
    with pytest.raises(ValueError, match=r"build step id"):
        make(tmp_path, node_id)


@pytest.mark.parametrize("node_id", ["assemble", "stage:kmp", "stage:posteffect", "blender_export"])
def test_good_ids(tmp_path: Path, node_id: str) -> None:
    assert make(tmp_path, node_id).id == node_id


BadChange = Callable[[Path], dict[str, object]]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda r: {"inputs": (Path("files/course.kmp"),)},
            r"stage:kmp: .*course\.kmp is not absolute",
        ),
        (lambda r: {"outputs": (Path("course.kmp"),)}, r"stage:kmp: course\.kmp is not absolute"),
        (lambda r: {"outputs": ()}, r"stage:kmp: a build step must write at least one file"),
        (lambda r: {"outputs": (r / "a", r / "a")}, r"stage:kmp: .*a is listed twice"),
        (lambda r: {"inputs": (r / "a", r / "a")}, r"stage:kmp: .*a is listed twice"),
        (lambda r: {"inputs": (r / "a",), "outputs": (r / "a",)}, r"reads and writes .*a"),
        (lambda r: {"tools": ("blendr",)}, r"stage:kmp: unknown tool 'blendr'"),
        (lambda r: {"impl_version": 0}, r"stage:kmp: impl_version must be a whole number >= 1"),
        (lambda r: {"impl_version": True}, r"impl_version must be a whole number >= 1"),
        (lambda r: {"impl_version": 1.5}, r"impl_version must be a whole number >= 1"),
        (lambda r: {"params": {"file": Path("x")}}, r"stage:kmp: params must be plain JSON"),
        (lambda r: {"params": {"scale": float("nan")}}, r"params must be plain JSON"),
        (lambda r: {"params": {1: "x"}}, r"params must be plain JSON"),
        (lambda r: {"resources": frozenset({""})}, r"stage:kmp: a resource name cannot be empty"),
    ],
)
def test_a_bad_node_is_refused_with_its_id(tmp_path: Path, change: BadChange, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        make(tmp_path, **change(tmp_path))
