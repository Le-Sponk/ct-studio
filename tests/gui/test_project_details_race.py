"""P5-T03c: a save must not discard an external edit made during file staging."""

import threading
from dataclasses import replace
from pathlib import Path

import pytest
import tomli_w
from details_helpers import details
from pytestqt.qtbot import QtBot

from ctstudio.core import fsutil
from ctstudio.core.project import manifest_io
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.gui.views.project_details import ProjectDetailsDialog

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


def assert_failed_save(dialog: ProjectDetailsDialog, project: Project, original: Manifest) -> None:
    assert not dialog.saved and dialog.isVisible()
    assert "Could not save" in dialog.problem.text()
    assert project.manifest is original


@pytest.mark.parametrize("external", ["edit", "delete"])
def test_save_staging_conflict_keeps_external_file_and_current_snapshot(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, external: str
) -> None:
    with details(qtbot, tmp_path) as (dialog, _services, project, _work):
        staged = threading.Event()
        release = threading.Event()
        real_stage = fsutil._stage_bytes
        original = project.manifest
        before = project.manifest_path.read_bytes()
        changed = replace(original, project=replace(original.project, author="EXTERNAL USER EDIT"))
        changed_bytes = tomli_w.dumps(manifest_io.as_data(changed)).encode("utf8")

        def gated_stage(path: Path, data: bytes) -> Path:
            result = real_stage(path, data)
            if path == project.manifest_path:
                staged.set()
                assert release.wait(10)
            return result

        monkeypatch.setattr(fsutil, "_stage_bytes", gated_stage)
        try:
            dialog.slot.setCurrentIndex(1)
            dialog.accept()
            qtbot.waitUntil(staged.is_set)
            assert dialog.busy and project.manifest is original
            if external == "edit":
                project.manifest_path.write_bytes(changed_bytes)
            else:
                project.manifest_path.unlink()
            release.set()
            qtbot.waitUntil(lambda: not dialog.busy)
            assert_failed_save(dialog, project, original)
            if external == "edit":
                assert project.manifest_path.read_bytes() == changed_bytes
            else:
                assert not project.manifest_path.exists()
            assert all(backup.read_bytes() == before for backup in project.root.glob("*.bak"))
            assert not tuple(project.root.glob(".ctstudio.toml.*"))
        finally:
            release.set()
            qtbot.waitUntil(lambda: not dialog.busy)
