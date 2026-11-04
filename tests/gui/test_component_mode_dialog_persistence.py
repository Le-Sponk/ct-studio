"""Disk-backed mode selection, exact save arguments and inactive-data preservation."""

import threading
from dataclasses import replace
from pathlib import Path

import pytest
from mode_helpers import ModeWork, modes
from pytestqt.qtbot import QtBot

from ctstudio.core.components.registry import COMPONENTS, ComponentSpec
from ctstudio.core.project import manifest_io

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@pytest.mark.parametrize(
    ("spec", "selected"),
    [
        (s, m)
        for s in COMPONENTS
        if s.manifest_table not in (None, "project") and len(s.modes) > 1
        for m in s.modes
    ],
)
def test_each_supported_save_changes_only_mode_and_keeps_files_and_settings(
    qtbot: QtBot, tmp_path: Path, spec: ComponentSpec, selected: str
) -> None:
    work = ModeWork()
    gate = threading.Event()
    work.load_gate = gate
    with modes(qtbot, tmp_path, work, component_id=spec.id, wait_loaded=False) as (
        dialog,
        _services,
        project,
        work,
    ):
        table = spec.manifest_table
        assert table is not None
        part = getattr(project.manifest.components, table)
        initial_part = replace(part, file="files/kept.dat", extra={"future": "retained"})
        components = replace(project.manifest.components, **{table: initial_part})
        seeded = replace(project.manifest, components=components, extra={"future": {"yes": True}})
        project.save(seeded)
        files = {project.root / "files/kept.dat": b"manual", project.root / "build/kept": b"built"}
        for path, raw in files.items():
            path.write_bytes(raw)
        before = project.manifest_path.read_bytes()
        gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert dialog.mode.currentData() == part.mode
        dialog.mode.setCurrentIndex(dialog.mode.findData(selected))
        dialog.save_button.click()
        qtbot.waitUntil(lambda: not dialog.busy)
        expected = replace(
            seeded, components=replace(components, **{table: replace(initial_part, mode=selected)})
        )
        assert (
            dialog.saved and project.manifest == manifest_io.load(project.manifest_path) == expected
        )
        saved_project, snapshot, component_id, mode = work.save_args[0]
        assert saved_project is project and snapshot.manifest == seeded and snapshot.raw == before
        assert component_id == spec.id and mode == selected
        assert all(t is not threading.main_thread() for _name, t in work.calls)
        assert {path: path.read_bytes() for path in files} == files


def test_initial_selection_comes_from_disk_not_stale_live_manifest(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = ModeWork()
    gate = threading.Event()
    work.load_gate = gate
    with modes(qtbot, tmp_path, work, wait_loaded=False) as (dialog, _services, project, _work):
        disk = replace(
            project.manifest,
            components=replace(
                project.manifest.components,
                course_model=replace(project.manifest.components.course_model, mode="manual"),
            ),
        )
        manifest_io.save(disk, project.manifest_path)
        gate.set()
        qtbot.waitUntil(lambda: not dialog.busy)
        assert dialog.mode.currentData() == "manual"
        assert project.manifest.components.course_model.mode == "auto"
        assert not dialog.saved
