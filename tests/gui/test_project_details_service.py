"""Blocking details persistence on real, synthetic projects; no external tools."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from ctstudio.core import fsutil
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.project.slots import SLOTS
from ctstudio.gui.project_details import ProjectDetailsService


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "project café 空", "Synthetic café") as opened:
        (opened.root / "files" / "old.blend").write_bytes(b"synthetic Blender source")
        old = opened.manifest
        opened.save(
            replace(
                old,
                project=replace(
                    old.project,
                    author="Synthetic author",
                    blend="files/old.blend",
                    extra={"future_project": [1, 2]},
                ),
                build=replace(old.build, auto_add=False, extra={"future_build": True}),
                blender=replace(old.blender, extra={"future_blender": "kept"}),
                components=replace(old.components, extra={"future_component": {"n": 3}}),
                hooks=replace(old.hooks, post_build="echo synthetic", extra={"future_hook": 2.5}),
                extra={"future_top": {"nested": ["é", "空"]}},
            )
        )
        yield opened


def test_load_returns_immutable_exact_disk_snapshot_without_writes(project: Project) -> None:
    before = project.manifest_path.read_bytes()
    before_stat = project.manifest_path.stat()
    result = ProjectDetailsService().load(project)

    assert result.root == project.root.resolve()
    assert result.raw == before
    assert result.manifest == project.manifest
    assert result.backup is None
    assert project.manifest_path.stat().st_mtime_ns == before_stat.st_mtime_ns
    assert not list(project.root.glob("*.bak"))
    for field in fields(result):
        with pytest.raises(FrozenInstanceError):
            setattr(result, field.name, None)


@pytest.mark.parametrize("change_before_parse", [False, True])
def test_load_refuses_manifest_changing_during_read(
    project: Project, monkeypatch: pytest.MonkeyPatch, change_before_parse: bool
) -> None:
    real_load = manifest_io.load

    def changing_load(path: Path) -> Manifest:
        if change_before_parse:
            path.write_bytes(path.read_bytes() + b"\n# external edit\n")
        result = real_load(path)
        if not change_before_parse:
            path.write_bytes(path.read_bytes() + b"\n# external edit\n")
        return result

    monkeypatch.setattr(manifest_io, "load", changing_load)
    with pytest.raises(ProjectError, match="changed") as caught:
        ProjectDetailsService().load(project)
    assert caught.value.hint
    assert not list(project.root.glob("*.bak"))


def test_load_allows_read_only_inspection_of_latest_disk(project: Project) -> None:
    latest = replace(project.manifest, build=replace(project.manifest.build, auto_add=True))
    manifest_io.save(latest, project.manifest_path)
    with Project.open(project.root) as readonly:
        assert readonly.read_only
        snapshot = ProjectDetailsService().load(readonly)
        assert snapshot.manifest == latest
        assert snapshot.raw == project.manifest_path.read_bytes()


@pytest.mark.parametrize("error", [PermissionError("denied"), ValueError("bad path")])
def test_load_wraps_filesystem_errors(
    project: Project, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fail_read(_path: Path) -> bytes:
        raise error

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(ProjectError) as caught:
        ProjectDetailsService().load(project)
    assert caught.value.hint
    assert caught.value.__cause__ is error


def _source(project: Project, tmp_path: Path, kind: str) -> tuple[Path | None, str | None]:
    if kind == "clear":
        return None, None
    folder = project.root / "files" if kind == "internal" else tmp_path
    blend = folder / "new source café 空.BLEND"
    blend.write_bytes(b"synthetic content, deliberately no Blender magic")
    text = "files/new source café 空.BLEND" if kind == "internal" else str(blend)
    return blend, text


@pytest.mark.parametrize("source", ["internal", "external", "clear"])
def test_save_backs_up_and_preserves_all_other_settings_without_publishing(
    project: Project, tmp_path: Path, source: str
) -> None:
    service = ProjectDetailsService()
    snapshot = service.load(project)
    original = project.manifest
    blend, expected_text = _source(project, tmp_path, source)

    result = service.save(project, snapshot, "old_mario_gc", blend)

    expected = replace(
        original, project=replace(original.project, slot="old_mario_gc", blend=expected_text)
    )
    assert result.manifest == expected
    assert manifest_io.load(project.manifest_path) == expected
    assert result.raw == project.manifest_path.read_bytes()
    assert result.root == project.root.resolve()
    assert result.backup is not None
    assert result.backup.read_bytes() == snapshot.raw
    assert list(project.root.glob("*.bak")) == [result.backup]
    assert project.manifest is original


@pytest.mark.parametrize("kind", ["internal", "external"])
def test_save_never_changes_blender_sources(project: Project, tmp_path: Path, kind: str) -> None:
    blend, _ = _source(project, tmp_path, kind)
    assert blend is not None
    old_source = project.root / "files/old.blend"
    contents = {path: path.read_bytes() for path in (old_source, blend)}
    service = ProjectDetailsService()
    service.save(project, service.load(project), "old_mario_gc", blend)
    assert all(path.read_bytes() == data for path, data in contents.items())


@pytest.mark.parametrize("slot", ["", "LC", "Luigi Circuit", "invented_course"])
def test_save_rejects_invalid_slot(project: Project, slot: str) -> None:
    service = ProjectDetailsService()
    snapshot = service.load(project)
    with pytest.raises(ProjectError, match=r"track|arena|slot") as caught:
        service.save(project, snapshot, slot, None)
    assert caught.value.hint
    assert project.manifest_path.read_bytes() == snapshot.raw
    assert not list(project.root.glob("*.bak"))


@pytest.mark.parametrize("kind", ["relative", "nul", "suffix", "missing", "directory", "empty"])
def test_save_rejects_invalid_blender_path(
    project: Project, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    service = ProjectDetailsService()
    snapshot = service.load(project)
    monkeypatch.chdir(project.root)
    blend = project.root / "files" / "source.blend"
    if kind == "relative":
        blend = Path("files/old.blend")
    elif kind == "nul":
        blend = Path(str(blend) + "\x00")
    elif kind == "suffix":
        blend = blend.with_suffix(".txt")
        blend.write_bytes(b"synthetic")
    elif kind == "directory":
        blend.mkdir()
    elif kind == "empty":
        blend = Path("")
    with pytest.raises(ProjectError) as caught:
        service.save(project, snapshot, "old_mario_gc", blend)
    assert caught.value.hint
    assert project.manifest_path.read_bytes() == snapshot.raw
    assert not list(project.root.glob("*.bak"))


@pytest.mark.parametrize("state", ["closed", "readonly"])
def test_save_rejects_project_without_write_lock(project: Project, state: str) -> None:
    service = ProjectDetailsService()
    target = project if state == "closed" else Project.open(project.root)
    try:
        snapshot = service.load(target)
        if state == "closed":
            target.close()
        with pytest.raises(ProjectError, match=r"read-only|closed") as caught:
            service.save(target, snapshot, "old_mario_gc", None)
        assert caught.value.hint
        assert project.manifest_path.read_bytes() == snapshot.raw
        assert not list(project.root.glob("*.bak"))
    finally:
        target.close()


def test_save_rejects_snapshot_for_different_root(project: Project, tmp_path: Path) -> None:
    service = ProjectDetailsService()
    snapshot = service.load(project)
    with pytest.raises(ProjectError, match=r"project|folder"):
        service.save(project, replace(snapshot, root=tmp_path), "old_mario_gc", None)
    assert project.manifest_path.read_bytes() == snapshot.raw
    assert not list(project.root.glob("*.bak"))


def test_save_rejects_in_memory_manifest_changed_since_load(project: Project) -> None:
    service = ProjectDetailsService()
    snapshot = service.load(project)
    current = replace(project.manifest, build=replace(project.manifest.build, auto_add=True))
    project.manifest = current
    with pytest.raises(ProjectError, match="changed"):
        service.save(project, snapshot, "old_mario_gc", None)
    assert project.manifest is current
    assert project.manifest_path.read_bytes() == snapshot.raw
    assert not list(project.root.glob("*.bak"))


def _external_edit(project: Project, raw: bytes, kind: str) -> bytes | None:
    if kind == "deleted":
        project.manifest_path.unlink()
        return None
    if kind == "valid":
        changed = replace(
            project.manifest, project=replace(project.manifest.project, author="other")
        )
        manifest_io.save(changed, project.manifest_path)
    else:
        project.manifest_path.write_bytes(
            b"not valid TOML" if kind == "invalid" else raw + b"# external\n"
        )
    return project.manifest_path.read_bytes()


@pytest.mark.parametrize("kind", ["valid", "invalid", "deleted", "comment"])
@pytest.mark.parametrize("noop", [False, True])
def test_save_never_overwrites_external_change(project: Project, kind: str, noop: bool) -> None:
    service = ProjectDetailsService()
    snapshot = service.load(project)
    external = _external_edit(project, snapshot.raw, kind)
    slot = snapshot.manifest.project.slot if noop else "old_mario_gc"
    blend = project.root / "files" / "old.blend" if noop else None
    with pytest.raises(ProjectError) as caught:
        service.save(project, snapshot, slot, blend)
    assert caught.value.hint
    assert project.manifest == snapshot.manifest
    assert not list(project.root.glob("*.bak"))
    if external is None:
        assert not project.manifest_path.exists()
    else:
        assert project.manifest_path.read_bytes() == external


def test_unchanged_save_does_not_rewrite_or_back_up(project: Project) -> None:
    project.manifest_path.write_bytes(project.manifest_path.read_bytes() + b"\n# keep comment\n")
    service = ProjectDetailsService()
    snapshot = service.load(project)
    stat = project.manifest_path.stat()
    result = service.save(
        project, snapshot, snapshot.manifest.project.slot, project.root / "files/old.blend"
    )
    assert result.manifest == snapshot.manifest
    assert result.raw == snapshot.raw
    assert result.backup is None
    assert project.manifest_path.read_bytes() == snapshot.raw
    assert project.manifest_path.stat().st_mtime_ns == stat.st_mtime_ns
    assert not list(project.root.glob("*.bak"))


@pytest.mark.parametrize("slot", SLOTS)
def test_save_accepts_every_catalogue_track_and_arena(project: Project, slot: str) -> None:
    service = ProjectDetailsService()
    result = service.save(project, service.load(project), slot, None)
    assert result.manifest.project.slot == slot
    assert manifest_io.load(project.manifest_path).project.slot == slot


@pytest.mark.parametrize("stage", ["backup", "replace"])
def test_failed_backup_or_atomic_replace_preserves_original(
    project: Project, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    service = ProjectDetailsService()
    snapshot = service.load(project)
    original = project.manifest
    faults = [OSError("synthetic write failure")]
    real_copy = fsutil.shutil.copy2
    real_replace = fsutil.os.replace

    def copy(source: Path, target: Path) -> Path | str:
        if faults:
            raise faults.pop()
        return real_copy(source, target)

    def replace_file(source: Path, target: Path) -> None:
        if target == project.manifest_path and faults:
            raise faults.pop()
        real_replace(source, target)

    if stage == "backup":
        monkeypatch.setattr(fsutil.shutil, "copy2", copy)
    else:
        monkeypatch.setattr(fsutil.os, "replace", replace_file)
    with pytest.raises(ProjectError) as caught:
        service.save(project, snapshot, "old_mario_gc", None)
    assert caught.value.hint
    assert not faults
    assert project.manifest is original
    assert project.manifest_path.read_bytes() == snapshot.raw
    backups = list(project.root.glob("*.bak"))
    assert len(backups) == (0 if stage == "backup" else 1)
    assert all(path.read_bytes() == snapshot.raw for path in backups)
    assert not list(project.root.glob(".ctstudio.toml.*"))


@pytest.mark.parametrize("error", [OSError("denied"), ValueError("bad path"), RuntimeError("loop")])
def test_save_wraps_ordinary_path_errors(
    project: Project, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    service = ProjectDetailsService()
    snapshot = service.load(project)

    def fail_resolve(_path: Path) -> Path:
        raise error

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "resolve", fail_resolve)
        with pytest.raises(ProjectError) as caught:
            service.save(project, snapshot, "old_mario_gc", None)
    assert caught.value.hint
    assert caught.value.__cause__ is error
    assert project.manifest_path.read_bytes() == snapshot.raw
    assert project.manifest == snapshot.manifest


@pytest.mark.parametrize("operation", ["load", "save"])
@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(3)])
def test_interrupts_are_never_swallowed(
    project: Project, monkeypatch: pytest.MonkeyPatch, operation: str, error: BaseException
) -> None:
    service = ProjectDetailsService()
    snapshot = service.load(project)

    def interrupt(_path: Path) -> bytes:
        raise error

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "read_bytes", interrupt)
        with pytest.raises(type(error)):
            if operation == "load":
                service.load(project)
            else:
                service.save(project, snapshot, "old_mario_gc", None)
    assert project.manifest_path.read_bytes() == snapshot.raw


def test_repeated_noop_save_does_not_report_previous_backup(project: Project) -> None:
    service = ProjectDetailsService()
    saved = service.save(project, service.load(project), "old_mario_gc", None)
    project.manifest = saved.manifest  # Simulate the UI publishing after its worker joined.
    result = service.save(project, saved, "old_mario_gc", None)
    assert result.backup is None
    assert result.raw == saved.raw
    assert list(project.root.glob("*.bak")) == [saved.backup]


def test_latest_disk_load_does_not_publish_over_stale_memory(project: Project) -> None:
    original = project.manifest
    latest = replace(original, build=replace(original.build, auto_add=True))
    manifest_io.save(latest, project.manifest_path)
    service = ProjectDetailsService()
    snapshot = service.load(project)
    assert snapshot.manifest == latest
    assert project.manifest is original
    with pytest.raises(ProjectError, match="changed"):
        service.save(project, snapshot, "old_mario_gc", None)
    assert manifest_io.load(project.manifest_path) == latest
