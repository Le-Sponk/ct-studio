"""P4-T05a: the assemble step packs ``.ctstudio/stage/`` into ``build/<slot>.szs``.

It runs ``wszst create`` with the profile's compression into a temporary folder, checks with
``wszst list`` that every staged file is inside, then replaces ``build/<slot>.szs`` and,
when enabled, the ``_d`` copy. Auto-add is never passed (P4-T05b). A failure leaves the
previous SZS as it was.
"""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest
from build_runner_helpers import Recorder, make_root

from ctstudio.core.build import assemble
from ctstudio.core.build.assemble import assemble_step
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildSummary, LogLine, NodeFailed
from ctstudio.core.build.graph import BuildGraph, from_manifest
from ctstudio.core.build.node import Profile
from ctstudio.core.build.objects import ObjectCheck
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.build.stage import manual_parts
from ctstudio.core.project.manifest import BuildSettings, Manifest, ProjectInfo
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.wiimm import WiimmError
from ctstudio.core.validation.issues import Issue

pytestmark = pytest.mark.timeout(60)
RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a"
YAZ0 = b"Yaz0"
VERSIONS = {"wszst": "2.42a", "wkmpt": "2.42a"}


@pytest.fixture(autouse=True)
def no_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests are about packing; the object check has its own (test_build_objects.py)."""
    monkeypatch.setattr(assemble, "check_objects", lambda *_a: ObjectCheck(None, ()))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = make_root(tmp_path)
    stage = project / ".ctstudio" / "stage"
    stage.mkdir(parents=True)
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(RECORDINGS / "inputs" / name, stage / name)
    return project


def manifest(**build: object) -> Manifest:
    settings = dataclasses.replace(BuildSettings(), **build)
    return Manifest(project=ProjectInfo(name="T", slot="castle_course"), build=settings)


def run(root: Path, m: Manifest, profile: Profile = "test") -> tuple[BuildSummary, Recorder]:
    recorder = Recorder()
    summary = run_build(
        BuildGraph(root, [assemble_step(root, m, profile)]),
        BuildCache.load(root),
        BuildRequest(m, profile, {}, VERSIONS),
        recorder,
        cancel=CancelToken(),
    )
    return summary, recorder


def creates(fake_tools_path) -> list[list[str]]:
    return [c["argv"] for c in fake_tools_path.calls() if c["argv"][0] == "create"]


def only_issue(summary: BuildSummary, recorder: Recorder) -> Issue:
    [failed] = [e for e in recorder.events if isinstance(e, NodeFailed)]
    [issue] = failed.issues
    assert summary.outcome == "failed" and summary.issues == (issue,)
    return issue


# --- the step ---------------------------------------------------------------------------------


def test_the_step_reads_the_whole_stage_and_writes_the_slot_files(root: Path) -> None:
    node = assemble_step(root, manifest(), "test")
    assert node.id == "assemble"
    assert node.inputs == (root / ".ctstudio" / "stage",)
    assert node.outputs == (
        root / "build" / "castle_course.szs",
        root / "build" / "castle_course_d.szs",
    )
    assert node.tools == ("wszst", "wkmpt")
    assert node.component is None
    assert dict(node.params) == {
        "slot": "castle_course",
        "compression": "fast",
        "d_variant": True,
        "library": None,
    }
    single = assemble_step(root, manifest(make_d_variant=False), "release")
    assert single.outputs == (root / "build" / "castle_course.szs",)
    assert dict(single.params) == {
        "slot": "castle_course",
        "compression": "best",
        "d_variant": False,
        "library": None,
    }


def test_it_runs_after_every_stage_step(root: Path) -> None:
    kmp = root / "files" / "course.kmp"
    kmp.parent.mkdir()
    shutil.copyfile(RECORDINGS / "inputs" / "course.kmp", kmp)
    m = manifest()
    table = dataclasses.replace(m.components.kmp, file="files/course.kmp")
    m = dataclasses.replace(m, components=dataclasses.replace(m.components, kmp=table))
    graph = from_manifest(
        root,
        m,
        lambda spec, mode: manual_parts(root, m)(spec, mode) if spec.id == "kmp" else [],
        [assemble_step(root, m, "test")],
    )
    assert [n.id for n in graph.nodes] == ["stage:kmp", "assemble"]
    assert graph.subgraph(["assemble"]).nodes == graph.nodes


# --- building ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("profile", "settings", "flags"),
    [
        ("test", {}, ["--fast"]),
        ("release", {}, []),  # best is wszst's default: no flag
        ("test", {"test_compression": "best"}, []),
        ("release", {"release_compression": "fast"}, ["--fast"]),
    ],
)
def test_the_profile_picks_the_compression(
    fake_tools_path, root: Path, profile: Profile, settings: dict[str, object], flags: list[str]
) -> None:
    summary, _ = run(root, manifest(**settings), profile)
    assert summary.outcome == "succeeded"
    [argv] = creates(fake_tools_path)
    assert argv[:3] == ["create", "stage", "--dest"]
    assert argv[4:] == flags, "never --auto-add (P4-T05b), never --overwrite"
    assert Path(argv[3]).parent.parent == root / "build", "written beside, then moved"


def test_the_slot_file_and_d_copy_are_written(fake_tools_path, root: Path) -> None:
    summary, recorder = run(root, manifest())
    szs = root / "build" / "castle_course.szs"
    assert summary.ran == ("assemble",)
    assert szs.read_bytes()[:4] == YAZ0
    assert (root / "build" / "castle_course_d.szs").read_bytes() == szs.read_bytes()
    assert sorted(p.name for p in (root / "build").iterdir()) == [
        "castle_course.szs",
        "castle_course_d.szs",
    ], "the temporary folder is gone"
    assert [c["argv"][0] for c in fake_tools_path.calls()] == ["create", "list"]
    lines = [e.text for e in recorder.events if isinstance(e, LogLine)]
    assert lines == ["castle_course.szs: 2 files (fast compression), and the _d copy"]


def test_no_d_copy_when_turned_off(fake_tools_path, root: Path) -> None:
    (root / "build").mkdir()
    old = root / "build" / "castle_course_d.szs"
    old.write_bytes(b"an old _d from before")
    run(root, manifest(make_d_variant=False))
    assert old.read_bytes() == b"an old _d from before", "not CT Studio's to delete now"


def test_an_unchanged_stage_is_not_assembled_again(fake_tools_path, root: Path) -> None:
    run(root, manifest())
    summary, _ = run(root, manifest())
    assert summary.skipped == ("assemble",)
    assert len(creates(fake_tools_path)) == 1
    (root / "build" / "castle_course_d.szs").unlink()
    assert run(root, manifest())[0].ran == ("assemble",), "a deleted output is made again"


def test_an_existing_szs_is_replaced(fake_tools_path, root: Path) -> None:
    (root / "build").mkdir()
    (root / "build" / "castle_course.szs").write_bytes(b"old")
    assert run(root, manifest())[0].outcome == "succeeded"
    assert (root / "build" / "castle_course.szs").read_bytes()[:4] == YAZ0


# --- failures ---------------------------------------------------------------------------------


def test_a_staged_file_missing_from_the_archive_fails_and_keeps_the_old_szs(
    fake_tools_path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "build").mkdir()
    old = root / "build" / "castle_course.szs"
    old.write_bytes(b"the last good build")
    monkeypatch.setattr(assemble, "list_files", lambda *_a, **_k: ("course.kmp",))
    issue = only_issue(*run(root, manifest()))
    assert issue == Issue(
        "error",
        "assemble",
        "ASSEMBLE_FILES_MISSING",
        "castle_course.szs was made without 1 staged file: course.kcl.",
        "Report this with the build log: Wiimm's tool left out a file it was given.",
        "wszst list",
        root / "build" / "castle_course.szs",
    )
    assert old.read_bytes() == b"the last good build"
    assert sorted(p.name for p in (root / "build").iterdir()) == ["castle_course.szs"]


def test_dot_files_are_not_expected_inside(
    fake_tools_path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """wszst leaves out names starting with a dot (measured), e.g. a copy in progress."""
    listed: list[Path] = []
    (root / ".ctstudio" / "stage" / ".course.kcl.tmp").write_bytes(b"half a copy")
    monkeypatch.setattr(
        assemble, "list_files", lambda p, **_k: listed.append(p) or ("course.kcl", "course.kmp")
    )
    assert run(root, manifest())[0].outcome == "succeeded"
    assert len(listed) == 1


@pytest.fixture
def created(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Replace ``wszst create`` with one that writes a Yaz0 file; returns its keyword args."""
    calls: list[dict[str, object]] = []

    def fake(_stage: Path, dest: Path, **kwargs: object) -> Path:
        calls.append(kwargs)
        dest.write_bytes(YAZ0 + b" fake")
        return dest

    monkeypatch.setattr(assemble, "create_szs", fake)
    return calls


@pytest.mark.usefixtures("created")
def test_files_in_sub_folders_must_be_inside_and_dot_folders_need_not(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = root / ".ctstudio" / "stage"
    (stage / "posteffect").mkdir()
    (stage / "posteffect" / "posteffect.bfg").write_bytes(b"fog")
    (stage / ".partial").mkdir()
    (stage / ".partial" / "x.bin").write_bytes(b"left by a crash")
    monkeypatch.setattr(assemble, "list_files", lambda *_a, **_k: ("course.kcl", "course.kmp"))
    issue = only_issue(*run(root, manifest()))
    assert issue.message == (
        "castle_course.szs was made without 1 staged file: posteffect/posteffect.bfg."
    )
    everything = ("course.kcl", "course.kmp", "posteffect/posteffect.bfg")
    monkeypatch.setattr(assemble, "list_files", lambda *_a, **_k: everything)
    assert run(root, manifest())[0].outcome == "succeeded"


def test_the_wszst_found_on_the_tools_page_is_used(
    root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, created: list[dict[str, object]]
) -> None:
    exe = tmp_path / "my tools" / "wszst.exe"
    seen: list[object] = []
    monkeypatch.setattr(
        assemble,
        "list_files",
        lambda _p, **k: seen.append(k["executable"]) or ("course.kcl", "course.kmp"),
    )
    m = manifest()
    tools = {"wszst": ToolLocation(exe, "2.42a", "setting", "direct")}
    run_build(
        BuildGraph(root, [assemble_step(root, m, "test")]),
        BuildCache.load(root),
        BuildRequest(m, "test", tools, VERSIONS),
        Recorder(),
        cancel=CancelToken(),
    )
    assert [c["executable"] for c in created] == [exe]
    assert seen == [exe]


def test_an_empty_stage_fails_clearly(fake_tools_path, root: Path) -> None:
    shutil.rmtree(root / ".ctstudio" / "stage")
    issue = only_issue(*run(root, manifest()))
    assert (issue.code, issue.message, issue.hint) == (
        "ASSEMBLE_NOTHING_STAGED",
        "There is nothing to put into castle_course.szs yet.",
        "Choose the track's files on the dashboard, then build again.",
    )
    assert creates(fake_tools_path) == []


def test_a_locked_szs_fails_clearly_and_leaves_no_temporary_files(
    fake_tools_path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(src: object, dst: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(assemble.os, "replace", locked)
    issue = only_issue(*run(root, manifest()))
    assert issue.code == "ASSEMBLE_REPLACE_FAILED"
    assert issue.message == "Could not replace build/castle_course.szs: Permission denied."
    assert issue.hint == "Close Dolphin or any program using the track file, then build again."
    assert list((root / "build").iterdir()) == []


def test_a_wszst_failure_leaves_no_temporary_files(
    fake_tools_path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(stage: Path, dest: Path, **_kwargs: object) -> Path:
        dest.write_bytes(b"half an archive")
        raise WiimmError(stage, 0, "ERROR #64 [CAN'T CREATE FILE]", error_code=64, details="")

    monkeypatch.setattr(assemble, "create_szs", broken)
    summary, recorder = run(root, manifest())
    [failed] = [e for e in recorder.events if isinstance(e, NodeFailed)]
    assert summary.outcome == "failed"
    assert "ERROR #64" in failed.message
    assert list((root / "build").iterdir()) == []


# --- P4-GATE review fixes -----------------------------------------------------------------------


def test_a_track_edited_by_hand_is_backed_up_before_it_is_replaced(
    fake_tools_path, root: Path
) -> None:
    assert run(root, manifest())[0].outcome == "succeeded"
    szs = root / "build" / "castle_course.szs"
    szs.write_bytes(szs.read_bytes() + b" + my hand edit")
    assert run(root, manifest())[0].ran == ("assemble",)
    [copy] = (root / ".ctstudio" / "backups").rglob("castle_course.szs")
    assert copy.read_bytes().endswith(b" + my hand edit")
    assert not szs.read_bytes().endswith(b" + my hand edit")


def test_a_wszst_crash_is_said_plainly_and_its_output_kept_for_the_log(
    fake_tools_path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dump = "0 [main] wszst 1105 cygwin_exception::open_stackdumpfile: Dumping stack trace"

    def crashed(stage: Path, dest: Path, **_kwargs: object) -> Path:
        raise WiimmError(stage, 35584, f"tool exited 35584: {dump}", error_code=None, details=dump)

    monkeypatch.setattr(assemble, "create_szs", crashed)
    summary, recorder = run(root, manifest())
    [failed] = [e for e in recorder.events if isinstance(e, NodeFailed)]
    assert summary.outcome == "failed"
    assert failed.message == (
        "Wiimm's tool stopped unexpectedly while packing the track: "
        "one of the track's files is probably damaged."
    )
    assert failed.hint == (
        "Export or choose the BRRES files again, then build again. "
        "The build log has the tool's own output."
    )
    [issue] = failed.issues
    assert issue.code == "ASSEMBLE_TOOL_CRASHED"
    assert failed.details == dump
    assert summary.log is not None and dump in summary.log.read_text(encoding="utf-8")
