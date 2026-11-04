"""Mode persistence on synthetic projects; no Qt widgets or external tools."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from ctstudio.core import fsutil
from ctstudio.core.components.registry import COMPONENTS, ComponentSpec
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.gui.component_modes import ComponentModeService
from ctstudio.gui.project_details import DetailsSnapshot


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "mode café 空", "Synthetic modes") as opened:
        yield opened


def test_mode_save_backs_up_original_without_publishing(project: Project) -> None:
    service = ComponentModeService()
    snapshot = service.load(project)
    result = service.save(project, snapshot, "course_model", "manual")
    expected = replace(
        snapshot.manifest,
        components=replace(
            snapshot.manifest.components,
            course_model=replace(snapshot.manifest.components.course_model, mode="manual"),
        ),
    )
    assert result.manifest == manifest_io.load(project.manifest_path) == expected
    assert project.manifest == snapshot.manifest
    assert result.raw == project.manifest_path.read_bytes()
    assert result.root == snapshot.root
    assert result.backup is not None
    assert result.backup.read_bytes() == snapshot.raw


@pytest.mark.parametrize("component_id", ["unknown", "objects", "track_info", "__class__"])
def test_components_without_mode_settings_are_refused(project: Project, component_id: str) -> None:
    service = ComponentModeService()
    snapshot = service.load(project)
    with pytest.raises(ProjectError) as caught:
        service.save(project, snapshot, component_id, "auto")
    assert caught.value.hint
    assert project.manifest_path.read_bytes() == snapshot.raw
    assert not list(project.root.glob("*.bak"))


@pytest.mark.parametrize("spec", COMPONENTS)
@pytest.mark.parametrize("mode", ["invalid", "AUTO", "", "auto\x00", "manual/../"])
def test_invalid_modes_are_refused(project: Project, spec: ComponentSpec, mode: str) -> None:
    service = ComponentModeService()
    snapshot = service.load(project)
    with pytest.raises(ProjectError) as caught:
        service.save(project, snapshot, spec.id, mode)
    assert caught.value.hint
    assert project.manifest_path.read_bytes() == snapshot.raw
    assert not list(project.root.glob("*.bak"))


@pytest.mark.parametrize(
    ("spec", "before", "after"),
    [
        (s, a, b)
        for s in COMPONENTS
        if s.manifest_table not in (None, "project")
        for a in s.modes
        for b in s.modes
    ],
)
def test_every_legal_transition_preserves_other_data(
    project: Project, spec: ComponentSpec, before: str, after: str
) -> None:
    components = project.manifest.components
    table = spec.manifest_table
    assert table is not None
    part = replace(
        getattr(components, table),
        mode=before,
        file="files/user data.bin",
        extra={"future": [1, 2]},
    )
    original = replace(
        project.manifest,
        components=replace(components, **{table: part}, extra={"future_component": {"value": 7}}),
        extra={"future_top": ["空", "é"]},
        build=replace(project.manifest.build, auto_add=False),
        hooks=replace(project.manifest.hooks, post_build="user hook"),
    )
    project.save(original)
    paths = [project.root / "files" / "user data.bin", project.root / "build" / "keep.bin"]
    for path in paths:
        path.write_bytes(b"synthetic user work")
    untouched = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    service = ComponentModeService()
    snapshot = service.load(project)
    result = service.save(project, snapshot, spec.id, after)
    expected = replace(
        original, components=replace(original.components, **{table: replace(part, mode=after)})
    )
    assert result.manifest == manifest_io.load(project.manifest_path) == expected
    assert project.manifest == original
    assert result.raw == project.manifest_path.read_bytes()
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths} == untouched
    _assert_backup(result, snapshot, changed=before != after)


def _assert_backup(result: DetailsSnapshot, snapshot: DetailsSnapshot, *, changed: bool) -> None:
    if changed:
        assert result.backup is not None
        assert result.backup.read_bytes() == snapshot.raw
    else:
        assert result.backup is None
        assert result.raw == snapshot.raw


@pytest.mark.parametrize(
    ("component", "mode"), [("kmp", "auto"), ("posteffect", "auto"), ("kcl", "template")]
)
def test_mode_valid_for_another_component_is_not_accepted(
    project: Project, component: str, mode: str
) -> None:
    service = ComponentModeService()
    snapshot = service.load(project)
    with pytest.raises(ProjectError, match="not supported"):
        service.save(project, snapshot, component, mode)
    assert project.manifest_path.read_bytes() == snapshot.raw


def test_noop_keeps_original_bytes_mtime_and_clears_old_backup(project: Project) -> None:
    project.manifest_path.write_bytes(
        project.manifest_path.read_bytes() + b"\n# preserve comment\n"
    )
    service = ComponentModeService()
    snapshot = replace(service.load(project), backup=Path("old.bak"))
    before = project.manifest_path.stat()
    result = service.save(project, snapshot, "course_model", "auto")
    assert result.raw == snapshot.raw
    assert result.backup is None
    assert project.manifest_path.stat().st_mtime_ns == before.st_mtime_ns
    assert not list(project.root.glob("*.bak"))


@pytest.mark.parametrize("state", ["readonly", "closed", "memory", "disk", "deleted", "foreign"])
@pytest.mark.parametrize("mode", ["auto", "manual"])
def test_stale_or_unowned_saves_refused_even_for_noops(
    project: Project, state: str, mode: str
) -> None:
    service = ComponentModeService()
    snapshot = service.load(project)
    if state == "readonly":
        with Project.open(project.root) as readonly:
            with pytest.raises(ProjectError, match="read-only"):
                service.save(readonly, snapshot, "course_model", mode)
        return
    snapshot = _prepare_conflict(project, snapshot, state)
    retained = _disk_bytes(project)
    current = project.manifest
    with pytest.raises(ProjectError) as caught:
        service.save(project, snapshot, "course_model", mode)
    assert caught.value.hint
    assert project.manifest == current
    assert _disk_bytes(project) == retained
    assert not list(project.root.glob("*.bak"))


def _disk_bytes(project: Project) -> bytes | None:
    return project.manifest_path.read_bytes() if project.manifest_path.exists() else None


def _prepare_conflict(project: Project, snapshot: DetailsSnapshot, state: str) -> DetailsSnapshot:
    if state == "closed":
        project.close()
    elif state == "memory":
        project.manifest = replace(project.manifest, extra={"changed": True})
    elif state == "disk":
        project.manifest_path.write_bytes(snapshot.raw + b"\n# EXTERNAL EDIT\n")
    elif state == "deleted":
        project.manifest_path.unlink()
    elif state == "foreign":
        snapshot = replace(snapshot, root=snapshot.root / "different")
    return snapshot


@pytest.mark.parametrize(
    "error", [PermissionError("denied"), ValueError("bad path"), RuntimeError("busy")]
)
def test_write_errors_are_actionable_without_publication(
    project: Project, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    service = ComponentModeService()
    snapshot = service.load(project)

    def fail(*_args: object, **_kwargs: object) -> Path:
        raise error

    monkeypatch.setattr(fsutil, "replace_with_backup", fail)
    with pytest.raises(ProjectError) as caught:
        service.save(project, snapshot, "course_model", "manual")
    assert caught.value.hint
    assert caught.value.__cause__ is error
    assert project.manifest == snapshot.manifest
    assert project.manifest_path.read_bytes() == snapshot.raw


@pytest.mark.parametrize("external", ["edit", "delete"])
def test_staging_conflict_retains_external_state(
    project: Project, monkeypatch: pytest.MonkeyPatch, external: str
) -> None:
    service = ComponentModeService()
    snapshot = service.load(project)
    real_stage = fsutil._stage_bytes
    changed = snapshot.raw + b"\n# external work during staging\n"

    def stage(path: Path, data: bytes) -> Path:
        staged = real_stage(path, data)
        if path == project.manifest_path:
            if external == "edit":
                path.write_bytes(changed)
            else:
                path.unlink()
        return staged

    monkeypatch.setattr(fsutil, "_stage_bytes", stage)
    with pytest.raises(ProjectError) as caught:
        service.save(project, snapshot, "course_model", "manual")
    assert caught.value.hint
    assert _disk_bytes(project) == (changed if external == "edit" else None)
    assert project.manifest == snapshot.manifest
    backups = list(project.root.glob("*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == snapshot.raw
    assert not list(project.root.glob(".ctstudio.toml.*"))


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(7)])
def test_interrupts_propagate(
    project: Project, monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    service = ComponentModeService()
    snapshot = service.load(project)

    def fail(*_args: object, **_kwargs: object) -> Path:
        raise error

    monkeypatch.setattr(fsutil, "replace_with_backup", fail)
    with pytest.raises(type(error)) as caught:
        service.save(project, snapshot, "course_model", "manual")
    assert caught.value is error
    assert project.manifest_path.read_bytes() == snapshot.raw


def test_loading_current_disk_does_not_publish_or_write(project: Project) -> None:
    original = project.manifest
    project.manifest_path.write_bytes(
        project.manifest_path.read_bytes().replace(b"auto_add = true", b"auto_add = false")
    )
    before = project.manifest_path.stat()
    snapshot = ComponentModeService().load(project)
    assert project.manifest is original
    assert not snapshot.manifest.build.auto_add
    assert snapshot.raw == project.manifest_path.read_bytes()
    assert project.manifest_path.stat().st_mtime_ns == before.st_mtime_ns
    assert not list(project.root.glob("*.bak"))
    with pytest.raises(ProjectError, match="changed"):
        ComponentModeService().save(project, snapshot, "course_model", "manual")


def test_loading_corrupt_manifest_is_actionable(project: Project) -> None:
    project.manifest_path.write_bytes(b"[broken")
    with pytest.raises(ProjectError) as caught:
        ComponentModeService().load(project)
    assert caught.value.hint
    assert project.manifest_path.read_bytes() == b"[broken"
    assert not list(project.root.glob("*.bak"))


@pytest.mark.parametrize("external", ["before", "after", "delete"])
def test_load_refuses_changes_during_parsing(
    project: Project, monkeypatch: pytest.MonkeyPatch, external: str
) -> None:
    original = project.manifest
    raw = project.manifest_path.read_bytes()
    changed = raw + b"\n# external edit while loading\n"
    real_load = manifest_io.load

    def changing_load(path: Path) -> Manifest:
        if external == "before":
            path.write_bytes(changed)
        loaded = real_load(path)
        if external == "after":
            path.write_bytes(changed)
        elif external == "delete":
            path.unlink()
        return loaded

    monkeypatch.setattr(manifest_io, "load", changing_load)
    with pytest.raises(ProjectError) as caught:
        ComponentModeService().load(project)
    assert caught.value.hint
    assert project.manifest is original
    assert _disk_bytes(project) == (None if external == "delete" else changed)
    assert not list(project.root.glob("*.bak"))


@pytest.mark.parametrize(
    "error",
    [PermissionError("read denied"), ValueError("bad read path"), RuntimeError("read busy")],
)
def test_load_io_errors_keep_their_cause(
    project: Project, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    original = project.manifest
    raw = project.manifest_path.read_bytes()

    def failing_load(_path: Path) -> Manifest:
        raise error

    monkeypatch.setattr(manifest_io, "load", failing_load)
    with pytest.raises(ProjectError) as caught:
        ComponentModeService().load(project)
    assert caught.value.hint
    assert caught.value.__cause__ is error
    assert project.manifest is original
    assert project.manifest_path.read_bytes() == raw
    assert not list(project.root.glob("*.bak"))
