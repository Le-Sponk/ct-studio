"""Read-only location inspection using synthetic projects, without desktop launches."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

import pytest

from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.errors import ProjectError, ToolFailedToStart, ToolNotFound
from ctstudio.core.project import settings
from ctstudio.core.project.project import Project
from ctstudio.core.tools import folders
from ctstudio.gui import folder_reveal
from ctstudio.gui.folder_reveal import FolderRevealService


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "project café 空", "Synthetic reveal") as opened:
        yield opened


class Recorder:
    def __init__(self) -> None:
        self.calls: list[Path] = []
        self.result = folders.OpenedFolder(Path("exact receipt café 空"), 8765)

    def __call__(self, folder: Path) -> folders.OpenedFolder:
        self.calls.append(folder)
        return self.result


def test_track_info_returns_exact_adapter_receipt(project: Project) -> None:
    opener = Recorder()
    result = FolderRevealService(open_folder=opener).reveal(project, "track_info")
    assert result is opener.result
    assert opener.calls == [project.root.resolve()]


def set_component(project: Project, component_id: str, mode: str, file: str | None) -> None:
    components = project.manifest.components
    table = replace(getattr(components, component_id), mode=mode, file=file)
    project.manifest = replace(
        project.manifest, components=replace(components, **{component_id: table})
    )


@pytest.mark.parametrize(
    ("component_id", "mode"),
    [(spec.id, mode) for spec in COMPONENTS for mode in spec.modes],
)
def test_every_registry_mode_uses_current_location(
    project: Project, component_id: str, mode: str
) -> None:
    supplied = project.root / "files" / "manual café 空" / "chosen.asset"
    if component_id not in ("objects", "track_info"):
        set_component(project, component_id, mode, supplied.relative_to(project.root).as_posix())
    opener = Recorder()
    service = FolderRevealService(open_folder=opener)
    if component_id == "objects":
        with pytest.raises(ProjectError) as caught:
            service.reveal(project, component_id)
        assert caught.value.hint
        assert "single" in str(caught.value).lower()
        assert not opener.calls
        return
    expected = expected_location(project.root, supplied, component_id, mode)
    assert service.reveal(project, component_id) is opener.result
    assert opener.calls == [expected.resolve()]


def expected_location(root: Path, supplied: Path, component_id: str, mode: str) -> Path:
    if component_id == "track_info":
        return root
    if mode == "manual":
        return supplied if component_id == "posteffect" else supplied.parent
    expected = root / ".ctstudio" / "stage"
    return expected / "posteffect" if component_id == "posteffect" else expected


@pytest.mark.parametrize("file", [None, ""])
@pytest.mark.parametrize(
    "component_id", ["course_model", "kcl", "minimap", "skybox", "kmp", "posteffect"]
)
def test_unassigned_manual_location_never_falls_back_to_generated_or_root(
    project: Project, component_id: str, file: str | None
) -> None:
    set_component(project, component_id, "manual", file)
    opener = Recorder()
    with pytest.raises(ProjectError) as caught:
        FolderRevealService(open_folder=opener).reveal(project, component_id)
    assert caught.value.hint and "single" in str(caught.value).lower()
    assert not opener.calls


def test_unknown_component_is_actionable_project_error(project: Project) -> None:
    opener = Recorder()
    with pytest.raises(ProjectError) as caught:
        FolderRevealService(open_folder=opener).reveal(project, "not-a-component")
    assert "not-a-component" in str(caught.value) and caught.value.hint
    assert not opener.calls


@pytest.mark.parametrize("change", ["root", "manifest", "equal_manifest"])
def test_project_changes_during_location_preparation_refuse_dispatch(
    project: Project, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    resolve = Path.resolve
    original_root, original_manifest = project.root, project.manifest

    def changing_resolve(path: Path, strict: bool = False) -> Path:
        result = resolve(path, strict=strict)
        if change == "root":
            project.root = original_root / "different"
        else:
            project.manifest = replace(
                original_manifest, extra={} if change == "equal_manifest" else {"changed": True}
            )
        return result

    opener = Recorder()
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", changing_resolve)
        with pytest.raises(ProjectError) as caught:
            FolderRevealService(open_folder=opener).reveal(project, "track_info")
    assert "changed" in str(caught.value).lower() and caught.value.hint
    assert not opener.calls
    project.root = original_root


@pytest.mark.parametrize("stage", ["preparation", "adapter"])
@pytest.mark.parametrize(
    "error",
    [
        OSError("unavailable"),
        PermissionError("denied"),
        ValueError("invalid location"),
        RuntimeError("busy"),
        ProjectError("typed folder failure"),
        ToolNotFound("desktop opener"),
        ToolFailedToStart("desktop opener", "OS refused"),
        KeyboardInterrupt(),
        SystemExit(7),
    ],
)
def test_errors_preserve_types_causes_and_interrupts(
    project: Project, monkeypatch: pytest.MonkeyPatch, stage: str, error: BaseException
) -> None:
    cause = OSError("original cause")
    error.__cause__ = cause

    def fail(*_args: object, **_kwargs: object) -> NoReturn:
        raise error

    opener = Recorder()
    with monkeypatch.context() as patch:
        if stage == "preparation":
            patch.setattr(Path, "resolve", fail)
        service = FolderRevealService(open_folder=fail if stage == "adapter" else opener)
        with pytest.raises(BaseException) as caught:
            service.reveal(project, "track_info")
    if isinstance(error, (OSError, ValueError, RuntimeError)):
        assert isinstance(caught.value, ProjectError) and caught.value.hint
        assert caught.value.__cause__ is error
        assert caught.value.details == str(error)
    else:
        assert caught.value is error and caught.value.__cause__ is cause
    assert not opener.calls


def tree(root: Path) -> dict[Path, tuple[bytes | None, int]]:
    return {
        path: (path.read_bytes() if path.is_file() else None, path.stat().st_mtime_ns)
        for path in root.rglob("*")
    }


@pytest.mark.parametrize("state", ["writable", "readonly", "closed"])
@pytest.mark.parametrize("external", [False, True])
def test_successive_calls_use_fresh_snapshot_preserve_files_without_settings_or_locks(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str, external: bool
) -> None:
    if state == "readonly":
        project = Project(project.root, project.manifest, None, "owned elsewhere")
    elif state == "closed":
        project.close()

    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("inspection must not access settings, save, or acquire locks")

    monkeypatch.setattr(settings, "load", forbidden)
    monkeypatch.setattr(settings, "save", forbidden)
    monkeypatch.setattr(Project, "save", forbidden)
    monkeypatch.setattr("ctstudio.core.project.project.acquire", forbidden)
    opener = Recorder()
    service = FolderRevealService(open_folder=opener)
    for number in (1, 2):
        location = (tmp_path if external else project.root / "files") / f"fresh café 空 {number}"
        location.mkdir()
        source = location / "supplied.asset"
        source.write_bytes(b"synthetic manual file; preserve exactly\x00\xff")
        set_component(
            project,
            "course_model",
            "manual",
            str(source) if external else source.relative_to(project.root).as_posix(),
        )
        assert_inspection_unchanged(service, project, opener, location, tmp_path)
    assert len(opener.calls) == 2


def assert_inspection_unchanged(
    service: FolderRevealService, project: Project, opener: Recorder, location: Path, root: Path
) -> None:
    manifest, lock, reason = project.manifest, project.lock, project.read_only_reason
    before = tree(root)
    assert service.reveal(project, "course_model") is opener.result
    assert opener.calls[-1] == location.resolve()
    assert project.manifest is manifest
    assert project.lock is lock
    assert project.read_only_reason == reason
    assert tree(root) == before


@pytest.mark.parametrize("component_id", ["course_model", "posteffect", "track_info"])
@pytest.mark.parametrize("exists", [False, True])
def test_default_adapter_validates_exact_location_without_fallback_or_creation(
    project: Project,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    component_id: str,
    exists: bool,
) -> None:
    expected = {
        "course_model": project.root / ".ctstudio" / "stage",
        "posteffect": project.root / ".ctstudio" / "stage" / "posteffect",
        "track_info": project.root,
    }[component_id]
    if exists:
        expected.mkdir(parents=True, exist_ok=True)
    elif component_id == "track_info":
        project.close()
        shutil.rmtree(project.root)
    windows = tmp_path / "Windows synthetic"
    windows.mkdir()
    executable = windows / "explorer.exe"
    executable.write_bytes(b"synthetic program; process dispatch is intercepted")
    monkeypatch.setenv("WINDIR", str(windows))
    monkeypatch.setattr(folders.platform, "current_os", lambda: "windows")
    calls: list[tuple[tuple[str | Path, ...], Path | None]] = []

    def detached(argv: list[str | Path], *, cwd: Path | None = None, watch: float = 0.0) -> int:
        calls.append((tuple(argv), cwd))
        return 4321

    monkeypatch.setattr(folders.process, "launch_detached", detached)
    before = tree(tmp_path)
    if exists:
        result = FolderRevealService().reveal(project, component_id)
        assert result == folders.OpenedFolder(expected.resolve(), 4321)
        assert calls == [((executable.resolve(), str(expected.resolve())), expected.resolve())]
    else:
        assert_missing(project, component_id, expected)
        assert not calls
    assert tree(tmp_path) == before


def assert_missing(project: Project, component_id: str, expected: Path) -> None:
    with pytest.raises(ProjectError) as caught:
        FolderRevealService().reveal(project, component_id)
    assert caught.value.hint
    assert str(expected.resolve()) in str(caught.value)
    assert not expected.exists()


@pytest.mark.parametrize("fault", ["no_table", "no_outputs"])
def test_registry_parts_without_one_location_are_refused(
    project: Project, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    spec = folder_reveal.COMPONENT_BY_ID["course_model"]
    changed = (
        replace(spec, manifest_table=None) if fault == "no_table" else replace(spec, outputs=())
    )
    monkeypatch.setattr(folder_reveal, "COMPONENT_BY_ID", {spec.id: changed})
    opener = Recorder()
    with pytest.raises(ProjectError) as caught:
        FolderRevealService(open_folder=opener).reveal(project, spec.id)
    assert "single" in str(caught.value).lower() and caught.value.hint
    assert not opener.calls


@pytest.mark.parametrize("output", ["nested café 空/first.asset", "nested café 空/folder/"])
def test_generated_locations_follow_first_registry_output_not_hardcoded_names(
    project: Project, monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    spec = folder_reveal.COMPONENT_BY_ID["course_model"]
    monkeypatch.setattr(
        folder_reveal, "COMPONENT_BY_ID", {spec.id: replace(spec, outputs=(output, "ignored/"))}
    )
    opener = Recorder()
    FolderRevealService(open_folder=opener).reveal(project, spec.id)
    expected = project.root / ".ctstudio" / "stage" / "nested café 空"
    if output.endswith("/"):
        expected /= "folder"
    assert opener.calls == [expected.resolve()]


@pytest.mark.parametrize("component_id", ["course_model", "posteffect"])
@pytest.mark.parametrize("exists", [False, True])
def test_external_manual_paths_use_file_parent_or_directory_even_when_missing(
    project: Project, tmp_path: Path, component_id: str, exists: bool
) -> None:
    supplied = tmp_path / "external café 空" / "chosen.asset"
    if exists:
        supplied.parent.mkdir()
        if component_id == "posteffect":
            supplied.mkdir()
        else:
            supplied.write_bytes(b"synthetic external asset")
    set_component(project, component_id, "manual", str(supplied))
    opener = Recorder()
    before = tree(tmp_path)
    FolderRevealService(open_folder=opener).reveal(project, component_id)
    expected = supplied if component_id == "posteffect" else supplied.parent
    assert opener.calls == [expected.resolve()]
    assert tree(tmp_path) == before


def test_service_does_not_cache_project_root_or_component_mode(
    project: Project, tmp_path: Path
) -> None:
    opener = Recorder()
    service = FolderRevealService(open_folder=opener)
    service.reveal(project, "course_model")
    set_component(project, "course_model", "manual", "files/chosen.asset")
    service.reveal(project, "course_model")
    previous_root = project.root
    project.root = tmp_path / "second café 空"
    try:
        service.reveal(project, "course_model")
        set_component(project, "course_model", "auto", "inactive/must-not-open.asset")
        service.reveal(project, "course_model")
        assert opener.calls == [
            (previous_root / ".ctstudio" / "stage").resolve(),
            (previous_root / "files").resolve(),
            (project.root / "files").resolve(),
            (project.root / ".ctstudio" / "stage").resolve(),
        ]
    finally:
        project.root = previous_root


def test_close_during_preparation_keeps_snapshot_readable(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolve = Path.resolve

    def closing_resolve(path: Path, strict: bool = False) -> Path:
        result = resolve(path, strict=strict)
        project.close()
        return result

    opener = Recorder()
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", closing_resolve)
        assert (
            FolderRevealService(open_folder=opener).reveal(project, "track_info") is opener.result
        )
    assert opener.calls == [project.root.resolve()]
    assert project.read_only_reason == "the project was closed"


@pytest.mark.parametrize("component_id", ["course_model", "posteffect"])
@pytest.mark.parametrize("fault", ["missing", "file_instead_of_directory"])
def test_missing_manual_directory_is_refused_by_real_adapter(
    project: Project, tmp_path: Path, component_id: str, fault: str
) -> None:
    target = tmp_path / "missing café 空"
    if fault == "file_instead_of_directory":
        target.write_bytes(b"not a directory")
    source = target if component_id == "posteffect" else target / "unbuilt.asset"
    set_component(project, component_id, "manual", str(source))
    before = tree(tmp_path)
    with pytest.raises(ProjectError) as caught:
        FolderRevealService().reveal(project, component_id)
    assert caught.value.hint
    assert str(target.resolve()) in str(caught.value)
    assert tree(tmp_path) == before
