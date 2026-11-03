"""P4-T03b: what a build leaves behind: ``state.json`` for the dashboard, and a build log.

A step that makes a track part says which (``Node.component``). After it runs, the runner
records the part in ``.ctstudio/state.json``: its settings, the files it wrote and the user's
files it was made from (the step's inputs and those of every step it needs, without the
files other steps write). Status then reads Ready, Stale after the ``.blend`` changes, and
"edited outside CT Studio" after someone edits a made file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from build_runner_helpers import Recorder, fail, make_root

from ctstudio.core.build import part_state
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import BuildContext, Node, NodeResult
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.components.state import STATE_FILE, load_state
from ctstudio.core.components.status import State, evaluate, settings_key
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.tools.process import CancelToken

pytestmark = pytest.mark.timeout(30)
TOOLS = ("blender", "wkclt", "wszst", "abmatt", "wimgt")


@dataclass(frozen=True)
class FakeProject:
    root: Path
    manifest: Manifest


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = make_root(tmp_path)
    (project / "track.blend").write_bytes(b"BLENDER v1")
    return project


def manifest() -> Manifest:
    return Manifest(project=ProjectInfo(name="T", blend="track.blend"))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def track_steps(root: Path, *, kcl_work: object = None) -> list[Node]:
    """blender_export (no part of its own) → kcl (makes the Collision part)."""
    exports = root / ".ctstudio" / "exports"
    stage = root / ".ctstudio" / "stage"

    def export(_ctx: BuildContext) -> NodeResult:
        _write(exports / "course.obj", "obj from " + (root / "track.blend").read_text("utf-8"))
        return NodeResult()

    def kcl(ctx: BuildContext) -> NodeResult:
        if callable(kcl_work):
            kcl_work(ctx)
        _write(stage / "course.kcl", "kcl of " + (exports / "course.obj").read_text("utf-8"))
        return NodeResult()

    return [
        Node("blender_export", (root / "track.blend",), (exports,), {}, (), frozenset(), 1, export),
        Node(
            "kcl", (exports / "course.obj",), (stage / "course.kcl",), {}, (), frozenset(), 1, kcl,
            component="kcl",
        ),
    ]  # fmt: skip


def build(root: Path, nodes: list[Node], cancel: CancelToken | None = None) -> Recorder:
    recorder = Recorder()
    request = BuildRequest(manifest(), "test", {}, {})
    run_build(
        BuildGraph(root, nodes),
        BuildCache.load(root),
        request,
        recorder,
        cancel=cancel or CancelToken(),
        jobs=2,
    )
    return recorder


def kcl_state(root: Path) -> State:
    return evaluate(FakeProject(root, manifest()), TOOLS)["kcl"].state


def _bump(path: Path) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))


# --- Node.component ---------------------------------------------------------------------------


def test_component_must_be_a_part_ct_studio_makes(root: Path) -> None:
    out = (root / ".ctstudio" / "stage" / "x",)
    with pytest.raises(ValueError, match=r"kcl: 'kc' is not a track part"):
        Node("kcl", (), out, {}, (), frozenset(), 1, lambda _c: NodeResult(), component="kc")
    with pytest.raises(ValueError, match=r"info: 'track_info' is not a track part CT Studio makes"):
        Node(
            "info", (), out, {}, (), frozenset(), 1, lambda _c: NodeResult(), component="track_info"
        )
    assert Node("a", (), out, {}, (), frozenset(), 1, lambda _c: NodeResult()).component is None


def test_two_steps_making_one_part_are_refused(root: Path) -> None:
    stage = root / ".ctstudio" / "stage"
    a = Node(
        "a", (), (stage / "a",), {}, (), frozenset(), 1, lambda _c: NodeResult(), component="kcl"
    )
    b = Node(
        "b", (), (stage / "b",), {}, (), frozenset(), 1, lambda _c: NodeResult(), component="kcl"
    )
    with pytest.raises(ValueError, match=r"'a' and 'b' both make the kcl part"):
        BuildGraph(root, [a, b])


# --- state.json -------------------------------------------------------------------------------


def test_a_built_part_is_ready(root: Path) -> None:
    assert kcl_state(root) == State.MISSING
    build(root, track_steps(root))
    assert kcl_state(root) == State.READY
    record = load_state(root).components["kcl"]
    assert record.settings == settings_key(manifest(), "kcl")
    assert set(record.outputs) == {"course.kcl"}
    assert set(record.inputs) == {"track.blend"}, "made from the user's file, not the export"


def test_a_changed_blend_makes_the_part_out_of_date(root: Path) -> None:
    build(root, track_steps(root))
    blend = root / "track.blend"
    blend.write_bytes(b"BLENDER v2")
    _bump(blend)
    assert kcl_state(root) == State.STALE
    build(root, track_steps(root))
    assert kcl_state(root) == State.READY


def test_an_edited_output_is_edited_outside_ct_studio(root: Path) -> None:
    build(root, track_steps(root))
    kcl = root / ".ctstudio" / "stage" / "course.kcl"
    kcl.write_text("hand edit of the collision", encoding="utf-8")
    _bump(kcl)
    assert kcl_state(root) == State.EDITED_EXTERNALLY


def test_a_part_made_into_a_folder_records_every_file_and_skips_missing_inputs(
    root: Path,
) -> None:
    stage = root / ".ctstudio" / "stage" / "kcl"

    def kcl(_ctx: BuildContext) -> NodeResult:
        _write(stage / "course.kcl", "kcl")
        _write(stage / "deep" / "extra.kcl", "kcl 2")
        return NodeResult()

    optional = root / "not_there.obj"
    node = Node(
        "kcl",
        (root / "track.blend", optional),
        (stage,),
        {},
        (),
        frozenset(),
        1,
        kcl,
        component="kcl",
    )
    build(root, [node])
    record = load_state(root).components["kcl"]
    assert set(record.outputs) == {"kcl/course.kcl", "kcl/deep/extra.kcl"}
    assert set(record.inputs) == {"track.blend"}
    assert kcl_state(root) == State.READY


def test_an_unchanged_build_rereads_nothing(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build(root, track_steps(root))
    calls: list[str] = []
    monkeypatch.setattr(part_state.state, "record", lambda *a: calls.append("record"))
    recorder = build(root, track_steps(root))
    assert ("NodeSkipped", "kcl") in recorder.kinds()
    assert calls == []


def test_a_skipped_part_with_no_record_is_recorded(root: Path) -> None:
    build(root, track_steps(root))
    (root / STATE_FILE).unlink()
    recorder = build(root, track_steps(root))
    assert ("NodeSkipped", "kcl") in recorder.kinds()
    assert kcl_state(root) == State.READY


def test_other_parts_records_are_kept(root: Path) -> None:
    stage = root / ".ctstudio" / "stage"

    def kmp(_ctx: BuildContext) -> NodeResult:
        _write(stage / "course.kmp", "kmp")
        return NodeResult()

    stage_kmp = Node(
        "stage:kmp", (), (stage / "course.kmp",), {}, (), frozenset(), 1, kmp, component="kmp"
    )
    build(root, [stage_kmp])
    build(root, track_steps(root))
    assert set(load_state(root).components) == {"kmp", "kcl"}


def test_a_failed_part_is_not_recorded(root: Path) -> None:
    build(root, track_steps(root, kcl_work=fail))
    assert "kcl" not in load_state(root).components
    assert kcl_state(root) == State.MISSING


def test_a_failed_rebuild_keeps_the_part_out_of_date(root: Path) -> None:
    build(root, track_steps(root))
    blend = root / "track.blend"
    blend.write_bytes(b"BLENDER v2")
    _bump(blend)
    build(root, track_steps(root, kcl_work=fail))
    assert kcl_state(root) == State.STALE


def test_a_cancelled_part_is_not_recorded(root: Path) -> None:
    """The export runs, the user cancels, the collision step never starts."""
    token = CancelToken()
    export, kcl = track_steps(root)
    cancelling = Node(
        export.id, export.inputs, export.outputs, {}, (), frozenset(), 1,
        lambda ctx: (export.run(ctx), token.cancel())[0],
    )  # fmt: skip
    build(root, [cancelling, kcl], cancel=token)
    assert not (root / STATE_FILE).exists()
