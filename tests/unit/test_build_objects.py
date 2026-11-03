"""P4-T05b: the assemble step's object check (``core/build/objects.py``) and auto-add use.

``wkmpt`` and ``wszst autoadd -vv`` are replaced by their parsed results (the parsers have
their own tests on real 2.42a output), so each case states exactly which objects the KMP
places, which files Wiimm lists for them and what the library check found.
"""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest
from build_runner_helpers import Recorder, make_root

from ctstudio.core.build import assemble, objects
from ctstudio.core.build.assemble import assemble_step
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildSummary, LogLine
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.project.manifest import BuildSettings, Manifest, ProjectInfo
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.wiimm import AutoAddLibrary
from ctstudio.core.tools.wiimm_objects import KmpObject
from ctstudio.core.validation.issues import Issue

pytestmark = pytest.mark.timeout(60)
RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a"
VERSIONS = {"wszst": "2.42a", "wkmpt": "2.42a"}
POCHA = ("effect/pocha/rk_pocha.breff", "effect/pocha/rk_pocha.breft", "pocha.brres")
DATABASE = {0x65: ("itembox.brres",), 0x7: POCHA, 0x12D: ()}


class World:
    """What the replaced Wiimm calls return, and what they were asked."""

    def __init__(self) -> None:
        self.placed: tuple[KmpObject, ...] = ()
        self.found: tuple[str, ...] = ()
        self.invalid: tuple[str, ...] = ()
        self.verified: list[Path] = []
        self.created: list[AutoAddLibrary | None] = []


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    w = World()

    def verify(library: Path, **_k: object) -> AutoAddLibrary:
        w.verified.append(library)
        return AutoAddLibrary(library, w.found, (), w.invalid)

    def create(_stage: Path, dest: Path, **kwargs: object) -> Path:
        library = kwargs["auto_add"]
        assert library is None or isinstance(library, AutoAddLibrary)
        w.created.append(library)
        dest.write_bytes(b"Yaz0 fake")
        return dest

    monkeypatch.setattr(objects, "kmp_objects", lambda *_a, **_k: w.placed)
    monkeypatch.setattr(
        objects, "object_files", lambda ids, **_k: {i: DATABASE[i] for i in ids if i in DATABASE}
    )
    monkeypatch.setattr(objects, "autoadd_verify", verify)
    monkeypatch.setattr(assemble, "create_szs", create)
    monkeypatch.setattr(assemble, "list_files", lambda *_a, **_k: ("course.kcl", "course.kmp"))
    return w


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = make_root(tmp_path)
    stage = project / ".ctstudio" / "stage"
    stage.mkdir(parents=True)
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(RECORDINGS / "inputs" / name, stage / name)
    return project


@pytest.fixture
def library(tmp_path: Path) -> Path:
    folder = tmp_path / "my auto-add é"
    folder.mkdir()
    (folder / "itembox.brres").write_bytes(b"from the user's own disc")
    return folder


def manifest(**build: object) -> Manifest:
    settings = dataclasses.replace(BuildSettings(), **build)
    return Manifest(project=ProjectInfo(name="T", slot="castle_course"), build=settings)


def run(
    root: Path, m: Manifest, library: Path | None, recorder: Recorder | None = None
) -> BuildSummary:
    return run_build(
        BuildGraph(root, [assemble_step(root, m, "test", library)]),
        BuildCache.load(root),
        BuildRequest(m, "test", {}, VERSIONS),
        recorder or Recorder(),
        cancel=CancelToken(),
    )


def logged(recorder: Recorder) -> list[str]:
    return [e.text for e in recorder.events if isinstance(e, LogLine)]


def warnings(summary: BuildSummary) -> list[tuple[str, str]]:
    assert summary.outcome == "succeeded", summary
    assert all(i.severity == "warning" and i.component == "objects" for i in summary.issues)
    return [(i.code, i.message) for i in summary.issues]


def only(summary: BuildSummary) -> Issue:
    """The one issue: a warning, so the track is still built."""
    [issue] = summary.issues
    assert summary.outcome == "succeeded" and issue.severity == "warning", summary
    assert issue.component == "objects"
    return issue


def test_auto_add_is_used_with_a_usable_library_and_nothing_is_missing(
    root: Path, library: Path, world: World
) -> None:
    world.placed = (KmpObject(0x65, "itembox", 3),)
    world.found = ("BRRES itembox.brres", "BREFF effect/pocha/rk_pocha.breff")
    recorder = Recorder()
    summary = run(root, manifest(), library, recorder)
    assert warnings(summary) == []
    assert logged(recorder) == [
        "castle_course.szs: 2 files (fast compression, with auto-add), and the _d copy"
    ]
    assert world.verified == [library]
    [used] = world.created
    assert used is not None and used.path == library


def test_each_object_missing_from_stage_and_library_is_named_once(
    root: Path, library: Path, world: World
) -> None:
    world.placed = (KmpObject(0x7, "pocha", 1), KmpObject(0x65, "itembox", 2))
    world.found = ("BREFF effect/pocha/rk_pocha.breff", "BRRES itembox.brres")
    issue = only(run(root, manifest(), library))
    assert issue.code == "OBJECTS_FILES_MISSING"
    assert issue.message == (
        "pocha (object 0x7) needs effect/pocha/rk_pocha.breft, pocha.brres, which are not in"
        " the track or the auto-add library."
    )
    assert issue.hint == "Add the files to the track: your auto-add library does not have them."
    assert world.created[0] is not None, "the library still supplies what it has"


def test_files_in_the_stage_count_including_sub_folders(
    root: Path, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = root / ".ctstudio" / "stage"
    (stage / "effect" / "pocha").mkdir(parents=True)
    for name in POCHA:
        (stage / name).write_bytes(b"supplied by the user")
    world.placed = (KmpObject(0x7, "pocha", 1), KmpObject(0x12D, "dummy", 1))
    packed = ("course.kcl", "course.kmp", *POCHA)
    monkeypatch.setattr(assemble, "list_files", lambda *_a, **_k: packed)
    assert warnings(run(root, manifest(), None)) == []
    assert world.created == [None]


def test_no_library_set_names_the_objects_and_never_passes_auto_add(
    root: Path, world: World
) -> None:
    world.placed = (KmpObject(0x65, "itembox", 2),)
    recorder = Recorder()
    issue = only(run(root, manifest(), None, recorder))
    assert logged(recorder) == ["castle_course.szs: 2 files (fast compression), and the _d copy"]
    assert issue.message == (
        "itembox (object 0x65, placed 2 times) needs itembox.brres, which is not in the track,"
        " and no auto-add library is set up."
    )
    assert "own game disc" in (issue.hint or "")
    assert world.created == [None] and world.verified == []


def test_auto_add_off_ignores_the_library(root: Path, library: Path, world: World) -> None:
    world.placed = (KmpObject(0x65, "itembox", 1),)
    world.found = ("BRRES itembox.brres",)
    issue = only(run(root, manifest(auto_add=False), library))
    assert issue.message.endswith("which is not in the track (auto-add is off).")
    assert issue.hint == (
        "Turn auto-add on in the project's build settings, or add the files to the track."
    )
    assert world.created == [None] and world.verified == [], "the library is not even checked"
    node = assemble_step(root, manifest(auto_add=False), "test", library)
    assert node.inputs == (root / ".ctstudio" / "stage",)
    assert node.params["library"] is None


@pytest.mark.parametrize(
    ("found", "invalid", "reason"),
    [
        ((), (), "none of the auto-add files are in"),
        (("BRRES itembox.brres",), ("BRRES itembox.brres",), "1 file(s) in"),
    ],
    ids=["empty", "not the originals"],
)
def test_an_unusable_library_is_a_warning_and_is_not_passed(
    root: Path,
    library: Path,
    world: World,
    found: tuple[str, ...],
    invalid: tuple[str, ...],
    reason: str,
) -> None:
    world.placed = (KmpObject(0x65, "itembox", 1),)
    world.found, world.invalid = found, invalid
    unusable, missing = run(root, manifest(), library).issues
    assert unusable.code == "OBJECTS_LIBRARY_UNUSABLE"
    assert unusable.message.startswith(
        "The auto-add library is not used, so no objects are added from it: "
    )
    assert reason in unusable.message and unusable.file == library
    assert missing.message.endswith(
        "which is not in the track, and the auto-add library cannot be used."
    )
    assert world.created == [None]


def test_an_object_wiimm_does_not_know_is_a_warning(root: Path, world: World) -> None:
    world.placed = (KmpObject(0x3FF, "", 1),)
    issue = only(run(root, manifest(), None))
    assert (issue.code, issue.message) == (
        "OBJECTS_UNKNOWN",
        "The course places object 0x3ff, which is not in Wiimm's object list.",
    )


def test_no_kmp_means_no_object_check(root: Path, world: World) -> None:
    (root / ".ctstudio" / "stage" / "course.kmp").unlink()
    world.placed = (KmpObject(0x65, "itembox", 1),)  # would warn if wkmpt were asked
    summary = run(root, manifest(), None)
    assert summary.outcome == "succeeded" and summary.issues == ()


def test_the_library_is_an_input_so_changing_it_builds_again(
    root: Path, library: Path, world: World
) -> None:
    world.found = ("BRRES itembox.brres",)
    node = assemble_step(root, manifest(), "test", library)
    assert node.inputs == (root / ".ctstudio" / "stage", library)
    assert node.params["library"] == str(library)
    assert run(root, manifest(), library).ran == ("assemble",)
    assert run(root, manifest(), library).ran == (), "unchanged library: skipped"
    (library / "itembox.brres").write_bytes(b"rebuilt from the disc, other bytes")
    assert run(root, manifest(), library).ran == ("assemble",)
