"""P4-T07a: build a whole project (``core/build/project_build.py``), as the CLI and GUI will.

The steps come from the manifest: a stage step per part in manual mode, then assemble and
validate (``only`` keeps one part's steps, without packing). The tools those steps use are
found the way doctor finds them, before anything runs, and a missing one stops the build
naming it. The fake Wiimm programs stand in for the real ones (``fake_tools_path``).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from build_runner_helpers import Recorder, make_root
from test_magic import brres, kcl, kmp, postfx

from ctstudio.core.build import assemble, project_build
from ctstudio.core.build.cache import CACHE_FILE
from ctstudio.core.build.objects import ObjectCheck
from ctstudio.core.build.project_build import build_project, plan_build
from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.errors import BuildGraphError, ToolNotFound
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.validation.issues import Issue

pytestmark = pytest.mark.timeout(60)
FILES = {
    "course_model": ("files/course_model.brres", brres()),
    "kcl": ("files/course.kcl", kcl(size=0x800)),
    "minimap": ("files/map_model.brres", brres()),
    "skybox": ("files/vrcorn_model.brres", brres()),
    "kmp": ("files/course.kmp", kmp()),
    "posteffect": ("files/fx/posteffect.bblm", postfx(b"PBLM")),
}
STAGES = [f"stage:{part}" for part in FILES]


def all_manual(root: Path) -> Manifest:
    """Every part in manual mode with a valid file of its type."""
    parts = {}
    for part, (rel, data) in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        chosen = "files/fx" if part == "posteffect" else rel
        table = getattr(Manifest(project=ProjectInfo(name="T")).components, part)
        parts[part] = dataclasses.replace(table, mode="manual", file=chosen)
    base = Manifest(project=ProjectInfo(name="Pistë", slot="castle_course"))
    return dataclasses.replace(base, components=dataclasses.replace(base.components, **parts))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_root(tmp_path)


@pytest.fixture
def no_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Only the fakes on PATH count: no developer tools (this checkout's ``.tools/``)."""
    monkeypatch.setattr(project_build, "default_dev_root", lambda: tmp_path / "no dev tools")


@pytest.fixture
def packed(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Packing stands in for wszst: the fake cannot pack the post-effects folder, nor wkmpt
    read a KMP (``test_build_assemble.py``, ``test_build_objects.py`` and the real-tool test
    cover those). Returns each archive "made"."""
    made: list[Path] = []
    staged: list[str] = []

    def create(stage: Path, dest: Path, **_k: object) -> Path:
        files = [p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file()]
        staged[:] = files
        dest.write_bytes(b"Yaz0 " + ",".join(sorted(files)).encode())
        made.append(dest)
        return dest

    monkeypatch.setattr(assemble, "check_objects", lambda *_a: ObjectCheck(None, ()))
    monkeypatch.setattr(assemble, "create_szs", create)
    monkeypatch.setattr(assemble, "list_files", lambda *_a, **_k: tuple(staged))
    return made


@pytest.fixture
def quiet_validate(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """The fake wszst cannot analyze an archive it did not record, so validate is stubbed."""
    from ctstudio.core.build import validate

    seen: list[Path] = []

    def analyze(szs: Path, **_k: object) -> dict[str, object]:
        seen.append(szs)
        return {f"sha1_{k}": "c9" for k in ("course", "kcl", "minimap", "vrcorn", "kmp")}

    monkeypatch.setattr(validate, "analyze", analyze)
    monkeypatch.setattr(validate, "check", lambda _szs, **_k: [])
    return seen


def test_every_manual_part_is_staged_then_packed_then_checked(
    root: Path, fake_tools_path: Any, no_settings: None
) -> None:
    plan = plan_build(root, all_manual(root), "test")
    assert [node.id for node in plan.graph.nodes] == [*STAGES, "assemble", "validate"]
    assert plan.request.profile == "test"
    assert set(plan.request.tools) == {"wszst", "wkmpt"}
    assert plan.request.tools["wszst"].path == fake_tools_path.resolve("wszst")
    assert plan.request.versions == {"wszst": "2.42a", "wkmpt": "2.42a"}


def test_only_one_part_builds_just_its_steps_and_needs_no_tools(
    root: Path, no_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    plan = plan_build(root, all_manual(root), "test", only="kcl")
    assert [node.id for node in plan.graph.nodes] == ["stage:kcl"]
    assert plan.request.tools == {} and plan.request.versions == {}


def test_only_a_part_without_a_step_is_refused_naming_those_with_one(root: Path) -> None:
    with pytest.raises(BuildGraphError) as caught:
        plan_build(root, all_manual(root), "test", only="objects")
    assert caught.value.user_message == "Objects is not built on its own."
    assert caught.value.hint == (
        "Choose one of: course_model, kcl, minimap, skybox, kmp, posteffect."
    )
    with pytest.raises(BuildGraphError, match="There is no part called ''"):
        plan_build(root, all_manual(root), "test", only="")
    with pytest.raises(BuildGraphError) as unknown:
        plan_build(root, all_manual(root), "test", only="kmpp")
    assert unknown.value.user_message == "There is no part called 'kmpp'. Did you mean kmp?"


def test_a_part_ct_studio_cannot_make_yet_stops_the_plan(root: Path) -> None:
    manifest = all_manual(root)
    auto = dataclasses.replace(manifest.components.kcl, mode="auto")
    manifest = dataclasses.replace(
        manifest, components=dataclasses.replace(manifest.components, kcl=auto)
    )
    with pytest.raises(BuildGraphError, match="cannot make the Collision in auto mode yet"):
        plan_build(root, manifest, "test")


def test_a_missing_tool_stops_the_build_before_anything_runs(
    root: Path, no_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(ToolNotFound) as caught:
        plan_build(root, all_manual(root), "test")
    assert caught.value.user_message == "Wiimms SZS Tool was not found."
    assert caught.value.hint == (
        "Install Wiimms SZS Tools, or set its path on the Tools page; "
        "`ctstudio doctor` shows what is missing."
    )
    assert not (root / ".ctstudio" / "stage").exists()


def test_a_tool_that_would_run_through_wine_is_not_used_yet(
    root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only programs this OS starts directly; the steps do not start tools through Wine."""

    def through_wine(spec: Any, **_k: object) -> ToolLocation:
        return ToolLocation(tmp_path / f"{spec.id}.exe", None, "path", "wine")

    monkeypatch.setattr(project_build, "discover", through_wine)
    with pytest.raises(ToolNotFound, match="Wiimms SZS Tool was not found"):
        plan_build(root, all_manual(root), "test")


def test_a_tool_path_set_in_ct_studio_is_used(
    root: Path, fake_tools_path: Any, no_settings: None, tmp_path: Path
) -> None:
    wszst = fake_tools_path.resolve("wszst")
    plan = plan_build(root, all_manual(root), "test", configured={"wszst": wszst})
    assert plan.request.tools["wszst"].source == "setting"
    with pytest.raises(ToolNotFound, match="Configured Wiimms SZS Tool"):
        plan_build(
            root, all_manual(root), "test", configured={"wszst": tmp_path / "gone" / "w.exe"}
        )


def test_a_tool_whose_version_is_unknown_still_builds(
    root: Path, fake_tools_path: Any, no_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_version(items: list[Any], **_k: object) -> list[Any]:
        from ctstudio.core.tools.versions import VersionResult

        return [VersionResult(spec.id, where, "timeout", "slow") for spec, where in items]

    monkeypatch.setattr(project_build, "probe_versions", no_version)
    plan = plan_build(root, all_manual(root), "test")
    assert plan.request.versions == {"wszst": None, "wkmpt": None}


def test_the_auto_add_library_reaches_the_assemble_step(
    root: Path, fake_tools_path: Any, no_settings: None, tmp_path: Path
) -> None:
    library = tmp_path / "auto-add"
    plan = plan_build(root, all_manual(root), "release", library=library)
    [assemble] = [n for n in plan.graph.nodes if n.id == "assemble"]
    assert assemble.params["library"] == str(library)
    assert assemble.params["compression"] == "best"
    assert plan.request.profile == "release"
    [validate] = [n for n in plan.graph.nodes if n.id == "validate"]
    assert validate.params == {"strict": True}


def test_a_build_runs_and_a_second_one_skips_everything(
    root: Path,
    fake_tools_path: Any,
    no_settings: None,
    quiet_validate: list[Path],
    packed: list[Path],
) -> None:
    plan = plan_build(root, all_manual(root), "test")
    recorder = Recorder()
    first = build_project(plan, recorder, cancel=CancelToken())
    assert first.outcome == "succeeded", first
    assert first.ran == (*STAGES, "assemble", "validate")
    szs = root / "build" / "castle_course.szs"
    assert packed == [szs.parent / packed[0].parent.name / szs.name]
    assert szs.read_bytes() == (
        b"Yaz0 course.kcl,course.kmp,course_model.brres,map_model.brres,"
        b"posteffect/posteffect.bblm,vrcorn_model.brres"
    )
    assert quiet_validate == [szs]
    again = build_project(
        plan_build(root, all_manual(root), "test"), Recorder(), cancel=CancelToken()
    )
    assert again.ran == () and len(again.skipped) == 8


def test_force_forgets_what_was_built_before(
    root: Path,
    fake_tools_path: Any,
    no_settings: None,
    quiet_validate: list[Path],
    packed: list[Path],
) -> None:
    build_project(plan_build(root, all_manual(root), "test"), Recorder(), cancel=CancelToken())
    old = json.loads((root / CACHE_FILE).read_text(encoding="utf-8"))
    assert set(old["nodes"]) == {*STAGES, "assemble", "validate"}
    plan = plan_build(root, all_manual(root), "test")
    forced = build_project(plan, Recorder(), cancel=CancelToken(), force=True)
    assert forced.ran == (*STAGES, "assemble", "validate") and forced.skipped == ()


def test_force_with_only_forgets_just_that_part(
    root: Path,
    fake_tools_path: Any,
    no_settings: None,
    quiet_validate: list[Path],
    packed: list[Path],
) -> None:
    build_project(plan_build(root, all_manual(root), "test"), Recorder(), cancel=CancelToken())
    plan = plan_build(root, all_manual(root), "test", only="kcl")
    forced = build_project(plan, Recorder(), cancel=CancelToken(), force=True)
    assert forced.ran == ("stage:kcl",)
    whole = build_project(
        plan_build(root, all_manual(root), "test"), Recorder(), cancel=CancelToken()
    )
    assert whole.ran == (), "the rest was kept, and kcl's copy is unchanged"


def test_issues_from_a_step_reach_the_summary(
    root: Path,
    fake_tools_path: Any,
    no_settings: None,
    packed: list[Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ctstudio.core.build import validate

    monkeypatch.setattr(validate, "analyze", lambda _s, **_k: {"sha1_minimap": ""})
    found = Issue("hint", "kmp", "WSZST_HINT", "Self linked item route.", None, "wszst check")
    monkeypatch.setattr(validate, "check", lambda _s, **_k: [found])
    summary = build_project(
        plan_build(root, all_manual(root), "test"), Recorder(), cancel=CancelToken()
    )
    assert [i.code for i in summary.issues] == ["VALIDATE_PART_MISSING", "WSZST_HINT"]


def test_every_part_with_a_file_has_a_stage_step() -> None:
    """``only`` accepts exactly the parts that put a file into the track."""
    assert [s.id for s in COMPONENTS if s.outputs] == list(FILES)
