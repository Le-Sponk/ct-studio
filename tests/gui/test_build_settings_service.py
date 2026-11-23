"""P5-T08b: the Build page's project settings on disk (``gui/build_settings.py``).

Loading reads the project file the way Project details does; saving goes through the same
stale-input checks (``persist_snapshot``): the live manifest and the file's bytes must still
match what was loaded, a read-only project is refused, keys this version does not know are
kept and the old file is backed up. Synthetic projects only; no external tools.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from editor_owner_helpers import outcome

from ctstudio.core import fsutil
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.build_settings import BuildChoices, BuildSettingsService
from ctstudio.gui.project_details import ProjectDetailsService

CHANGED = BuildChoices("none", "fast", make_d_variant=False, auto_add=True)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "Build café 空", "Build café") as opened:
        old = opened.manifest
        opened.save(
            replace(
                old,
                build=replace(
                    old.build,
                    auto_add=False,
                    extra_wszst_args=("--reserved",),
                    extra={"future_build": [1, "é"]},
                ),
                extra={"future_top": {"kept": True}},
            )
        )
        yield opened


def backups(project: Project) -> list[Path]:
    return sorted(project.root.glob(f"{manifest_io.FILE_NAME}.*.bak"))


def test_load_is_the_project_details_read(project: Project) -> None:
    loaded = BuildSettingsService().load(project)
    details = ProjectDetailsService().load(project)
    assert loaded == details, "not the same exact-byte read as Project details"
    assert BuildChoices.of(loaded.manifest.build) == BuildChoices(
        "fast", "best", make_d_variant=True, auto_add=False
    )


def test_save_writes_the_four_choices_and_keeps_everything_else(project: Project) -> None:
    service = BuildSettingsService()
    snapshot = service.load(project)
    before = project.manifest_path.read_bytes()
    saved = service.save(project, snapshot, CHANGED)
    on_disk = manifest_io.load(project.manifest_path)
    assert on_disk == saved.manifest and saved.raw == project.manifest_path.read_bytes()
    assert BuildChoices.of(on_disk.build) == CHANGED
    assert on_disk.build.extra_wszst_args == ("--reserved",), "the reserved list was lost"
    assert on_disk.build.extra == {"future_build": [1, "é"]}, "an unknown build key was lost"
    assert on_disk.extra == {"future_top": {"kept": True}}, "an unknown table was lost"
    assert replace(on_disk, build=snapshot.manifest.build) == snapshot.manifest
    assert project.manifest == snapshot.manifest, "the service published the manifest itself"
    assert saved.backup is not None and saved.backup.read_bytes() == before
    assert backups(project) == [saved.backup], "not exactly one backup"


def test_saving_the_same_choices_writes_nothing(project: Project) -> None:
    service = BuildSettingsService()
    snapshot = service.load(project)
    before = project.manifest_path.read_bytes()
    saved = service.save(project, snapshot, BuildChoices.of(snapshot.manifest.build))
    assert saved.backup is None and saved.manifest == snapshot.manifest
    assert project.manifest_path.read_bytes() == before and backups(project) == []


def test_an_unknown_compression_is_refused_and_nothing_is_written(project: Project) -> None:
    service = BuildSettingsService()
    snapshot = service.load(project)
    before = project.manifest_path.read_bytes()
    wrong = replace(CHANGED, release_compression="ultra")  # type: ignore[arg-type]
    raised = outcome(lambda: service.save(project, snapshot, wrong))
    assert isinstance(raised, ProjectError), f"not refused: {raised!r}"
    assert "compression" in str(raised).casefold()
    assert project.manifest_path.read_bytes() == before and backups(project) == []


def test_a_file_changed_after_loading_is_not_overwritten(project: Project) -> None:
    service = BuildSettingsService()
    snapshot = service.load(project)
    outside = project.manifest_path.read_bytes() + b"\n# changed outside\n"
    project.manifest_path.write_bytes(outside)
    raised = outcome(lambda: service.save(project, snapshot, CHANGED))
    assert isinstance(raised, ProjectError), f"not refused: {raised!r}"
    assert "changed" in str(raised) and "build settings" in str(raised), str(raised)
    assert project.manifest_path.read_bytes() == outside and backups(project) == []


def test_a_changed_live_manifest_is_not_overwritten(project: Project) -> None:
    service = BuildSettingsService()
    snapshot = service.load(project)
    project.manifest = replace(
        project.manifest, project=replace(project.manifest.project, author="x")
    )
    before = project.manifest_path.read_bytes()
    raised = outcome(lambda: service.save(project, snapshot, CHANGED))
    assert isinstance(raised, ProjectError), f"not refused: {raised!r}"
    assert project.manifest_path.read_bytes() == before and backups(project) == []


def test_a_read_only_project_is_refused(project: Project, tmp_path: Path) -> None:
    viewer = Project.open(project.root)
    try:
        assert viewer.read_only, "the second open was not read-only"
        service = BuildSettingsService()
        snapshot = service.load(viewer)
        before = project.manifest_path.read_bytes()
        raised = outcome(lambda: service.save(viewer, snapshot, CHANGED))
        assert isinstance(raised, ProjectError), f"not refused: {raised!r}"
        assert "read-only" in str(raised)
        assert project.manifest_path.read_bytes() == before and backups(project) == []
    finally:
        viewer.close()


def test_a_disk_failure_is_explained(project: Project, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("synthetic: no write access")

    service = BuildSettingsService()
    snapshot = service.load(project)
    monkeypatch.setattr(fsutil, "replace_with_backup", refuse)
    raised = outcome(lambda: service.save(project, snapshot, CHANGED))
    assert isinstance(raised, ProjectError), f"not explained: {raised!r}"
    assert str(raised).startswith("Could not save the build settings.")
    assert "synthetic: no write access" in (raised.details or "")
