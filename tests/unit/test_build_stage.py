"""P4-T04: staging a part the user supplies (manual mode) into ``.ctstudio/stage/``.

The step ``stage:<part>`` checks the chosen file with the same type check the dashboard uses,
then copies it under the name the game expects (``course.kcl``; post-effects as a whole
folder). A wrong type, no file chosen, a missing file or a file inside ``.ctstudio/`` fails
the step with one clear Issue. Unchanged files are not copied again.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
from pathlib import Path

import pytest
from build_runner_helpers import Recorder, make_root
from test_magic import brres, kcl, kmp, png, postfx

from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildSummary, NodeFailed
from ctstudio.core.build.graph import BuildGraph, from_manifest
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.build.stage import manual_parts, stage_part
from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS
from ctstudio.core.components.state import load_state
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.validation.issues import Issue

pytestmark = pytest.mark.timeout(30)
STAGE = Path(".ctstudio") / "stage"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_root(tmp_path)


def manual(component: str, file: str | None, base: Manifest | None = None) -> Manifest:
    base = base or Manifest(project=ProjectInfo(name="T"))
    table = dataclasses.replace(getattr(base.components, component), mode="manual", file=file)
    parts = dataclasses.replace(base.components, **{component: table})
    return dataclasses.replace(base, components=parts)


def write(root: Path, rel: str, data: bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def bump(path: Path) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))


def stage(root: Path, manifest: Manifest, *parts: str) -> tuple[BuildSummary, Recorder]:
    nodes = [stage_part(root, manifest, COMPONENT_BY_ID[p]) for p in parts]
    recorder = Recorder()
    request = BuildRequest(manifest, "test", {}, {})
    summary = run_build(
        BuildGraph(root, nodes), BuildCache.load(root), request, recorder, cancel=CancelToken()
    )
    return summary, recorder


def only_issue(summary: BuildSummary, recorder: Recorder) -> Issue:
    [failed] = [e for e in recorder.events if isinstance(e, NodeFailed)]
    [issue] = failed.issues
    assert summary.outcome == "failed"
    assert summary.issues == (issue,)
    assert failed.message == issue.message and failed.hint == issue.hint
    return issue


# --- copying ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("component", "rel", "data", "staged"),
    [
        ("course_model", "files/my model.brres", brres(), "course_model.brres"),
        ("kcl", "files/Course.KCL", kcl(), "course.kcl"),
        ("minimap", "files/map.brres", brres(0x90), "map_model.brres"),
        ("skybox", "files/sky.brres", brres(0xA0), "vrcorn_model.brres"),
        ("kmp", "files/course.kmp", kmp(), "course.kmp"),
    ],
)
def test_a_supplied_file_is_copied_under_its_game_name(
    root: Path, component: str, rel: str, data: bytes, staged: str
) -> None:
    source = write(root, rel, data)
    summary, _ = stage(root, manual(component, rel), component)
    assert summary.outcome == "succeeded"
    assert summary.ran == (f"stage:{component}",)
    assert (root / STAGE / staged).read_bytes() == data
    assert source.read_bytes() == data, "the user's own file is left alone"
    record = load_state(root).components[component]
    assert set(record.outputs) == {staged}
    assert set(record.inputs) == {rel}


def test_a_file_outside_the_project_is_copied(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere" / "course.kcl"
    outside.parent.mkdir()
    outside.write_bytes(kcl())
    summary, _ = stage(root, manual("kcl", str(outside)), "kcl")
    assert summary.outcome == "succeeded"
    assert (root / STAGE / "course.kcl").read_bytes() == kcl()


def test_an_unchanged_file_is_not_copied_again(root: Path) -> None:
    source = write(root, "files/course.kcl", kcl())
    manifest = manual("kcl", "files/course.kcl")
    stage(root, manifest, "kcl")
    summary, _ = stage(root, manifest, "kcl")
    assert summary.skipped == ("stage:kcl",)
    source.write_bytes(kcl(size=0x800))
    bump(source)
    summary, _ = stage(root, manifest, "kcl")
    assert summary.ran == ("stage:kcl",)
    assert (root / STAGE / "course.kcl").read_bytes() == kcl(size=0x800)


def test_post_effects_are_copied_as_a_whole_folder(root: Path) -> None:
    write(root, "fx/posteffect.bblm", postfx(b"PBLM"))
    write(root, "fx/posteffect.bfg", b"fog, no magic")
    write(root, "fx/more/posteffect.blight", postfx(b"LGHT"))
    write(root, "fx/old.bdof", postfx(b"PDOF"))
    manifest = manual("posteffect", "fx")
    assert stage(root, manifest, "posteffect")[0].outcome == "succeeded"
    out = root / STAGE / "posteffect"
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == [
        "more/posteffect.blight",
        "old.bdof",
        "posteffect.bblm",
        "posteffect.bfg",
    ]
    (root / "fx" / "old.bdof").unlink()
    summary, _ = stage(root, manifest, "posteffect")
    assert summary.ran == ("stage:posteffect",)
    assert not (out / "old.bdof").exists(), "a file the user removed is not left behind"
    assert (out / "more" / "posteffect.blight").read_bytes() == postfx(b"LGHT")
    assert [p.name for p in (root / STAGE).iterdir()] == ["posteffect"], "no old copy kept"


# --- clear failures ---------------------------------------------------------------------------


def test_a_wrong_file_type_fails_with_a_clear_issue(root: Path) -> None:
    write(root, "files/course.kcl", png())
    summary, recorder = stage(root, manual("kcl", "files/course.kcl"), "kcl")
    issue = only_issue(summary, recorder)
    assert issue == Issue(
        "error",
        "kcl",
        "STAGE_WRONG_TYPE",
        "files/course.kcl is the wrong type: expected collision file (KCL), found PNG image",
        "Choose a collision file (KCL) for the Collision.",
        "stage",
        root / "files" / "course.kcl",
        COMPONENT_BY_ID["kcl"].wiki,
    )
    assert not (root / STAGE / "course.kcl").exists()
    assert "kcl" not in load_state(root).components
    log = summary.log.read_text(encoding="utf-8") if summary.log else ""
    assert "[stage:kcl] FAILED: files/course.kcl is the wrong type" in log


def test_a_wrong_post_effect_folder_fails_with_a_clear_issue(root: Path) -> None:
    write(root, "fx/posteffect.bblm", png())
    summary, recorder = stage(root, manual("posteffect", "fx"), "posteffect")
    issue = only_issue(summary, recorder)
    assert issue.code == "STAGE_WRONG_TYPE"
    assert issue.message == (
        "fx/posteffect.bblm is the wrong type: expected bloom settings (BBLM), found PNG image"
    )
    assert issue.hint == (
        "Choose a folder of post-effect files (.bblm, .bdof, .blight, .blmap, .bfg)."
    )


@pytest.mark.parametrize(
    ("file", "code", "message", "hint"),
    [
        (
            None,
            "STAGE_NO_FILE",
            "No file is chosen for the Collision.",
            'Choose one in ctstudio.toml: [components.kcl] file = "...".',
        ),
        (
            "files/gone.kcl",
            "STAGE_NOT_FOUND",
            "files/gone.kcl was not found.",
            "Put the file back, or choose another in ctstudio.toml.",
        ),
    ],
)
def test_no_file_or_a_missing_file_fails_with_a_clear_issue(
    root: Path, file: str | None, code: str, message: str, hint: str
) -> None:
    summary, recorder = stage(root, manual("kcl", file), "kcl")
    issue = only_issue(summary, recorder)
    assert (issue.code, issue.message, issue.hint) == (code, message, hint)
    assert issue.file == (root / file if file else None)


@pytest.mark.parametrize(
    ("component", "file"),
    [
        ("kcl", ".ctstudio/stage/course.kcl"),  # the staged copy itself
        ("kcl", ".ctstudio/exports/course.kcl"),
        ("posteffect", "."),  # the whole project, .ctstudio/ included
        ("posteffect", ".ctstudio"),
    ],
)
def test_a_file_inside_ctstudio_is_refused(root: Path, component: str, file: str) -> None:
    write(root, ".ctstudio/stage/course.kcl", kcl())
    write(root, ".ctstudio/exports/course.kcl", kcl())
    node = stage_part(root, manual(component, file), COMPONENT_BY_ID[component])
    assert node.inputs == (), "not linked to the step that writes it"
    summary, recorder = stage(root, manual(component, file), component)
    issue = only_issue(summary, recorder)
    assert issue.code == "STAGE_INSIDE_CTSTUDIO"
    assert issue.message == f"{file} is inside the .ctstudio folder, which CT Studio manages."
    assert (
        issue.hint == "Copy it somewhere else in the project, choose that copy, then build again."
    )


def test_a_failed_copy_keeps_the_old_file_and_leaves_no_temporary_file(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write(root, "files/course.kcl", kcl())
    manifest = manual("kcl", "files/course.kcl")
    stage(root, manifest, "kcl")
    source.write_bytes(kcl(size=0x800))
    bump(source)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(shutil, "copyfileobj", broken)
    summary, recorder = stage(root, manifest, "kcl")
    issue = only_issue(summary, recorder)
    assert issue.code == "STAGE_COPY_FAILED"
    assert issue.message == "Could not copy files/course.kcl: No space left on device."
    assert issue.hint == "Close programs using the file and free some disk space, then build again."
    assert (root / STAGE / "course.kcl").read_bytes() == kcl(), "the old copy is untouched"
    assert sorted(p.name for p in (root / STAGE).iterdir()) == ["course.kcl"]


def test_a_failed_folder_copy_keeps_the_old_folder(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(root, "fx/posteffect.bblm", postfx(b"PBLM"))
    manifest = manual("posteffect", "fx")
    stage(root, manifest, "posteffect")
    write(root, "fx/posteffect.bfg", b"fog")
    real = shutil.copy2

    def copy(src: Path, dst: Path) -> object:
        if src.suffix == ".bfg":
            raise PermissionError(13, "Permission denied")
        return real(src, dst)

    monkeypatch.setattr(shutil, "copy2", copy)
    summary, recorder = stage(root, manifest, "posteffect")
    issue = only_issue(summary, recorder)
    assert issue.code == "STAGE_COPY_FAILED"
    assert issue.message == "Could not copy fx: Permission denied."
    assert sorted(p.name for p in (root / STAGE).iterdir()) == ["posteffect"]
    assert sorted(p.name for p in (root / STAGE / "posteffect").iterdir()) == ["posteffect.bblm"]


def test_a_failed_folder_swap_puts_the_old_folder_back(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(root, "fx/posteffect.bblm", postfx(b"PBLM"))
    manifest = manual("posteffect", "fx")
    stage(root, manifest, "posteffect")
    write(root, "fx/posteffect.bfg", b"fog")
    out = root / STAGE / "posteffect"
    real = Path.rename
    failures = [PermissionError(13, "Access is denied")]  # once: e.g. a virus scan

    def rename(self: Path, target: Path) -> Path:
        if Path(target) == out and failures:
            raise failures.pop()
        return real(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    summary, recorder = stage(root, manifest, "posteffect")
    assert only_issue(summary, recorder).message == "Could not copy fx: Access is denied."
    assert [p.name for p in (root / STAGE).iterdir()] == ["posteffect"]
    assert [p.name for p in out.iterdir()] == ["posteffect.bblm"], "the old folder is back"


# --- in the build graph -----------------------------------------------------------------------


def test_every_manual_part_gets_a_stage_step(root: Path) -> None:
    manifest = Manifest(project=ProjectInfo(name="T"))
    for spec in COMPONENTS:
        if spec.outputs and "manual" in spec.modes:
            manifest = manual(spec.id, f"files/{spec.id}", manifest)
    graph = from_manifest(root, manifest, manual_parts(root, manifest))
    assert [node.id for node in graph.nodes] == [
        "stage:course_model",
        "stage:kcl",
        "stage:minimap",
        "stage:skybox",
        "stage:kmp",
        "stage:posteffect",
    ]
    assert all(node.component == node.id.removeprefix("stage:") for node in graph.nodes)


def test_parts_in_other_modes_are_left_to_other_steps(root: Path) -> None:
    manifest = Manifest(project=ProjectInfo(name="T"))
    make = manual_parts(root, manifest)
    assert make(COMPONENT_BY_ID["kcl"], "auto") is None
    assert make(COMPONENT_BY_ID["posteffect"], "template") is None
    [node] = make(COMPONENT_BY_ID["kmp"], "manual") or []
    assert node.id == "stage:kmp"
