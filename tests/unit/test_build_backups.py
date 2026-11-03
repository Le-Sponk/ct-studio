"""P4-GATE Should fix: a file CT Studio made and the user then edited is backed up first.

ARCHITECTURE §8: "Before any overwrite of a file whose hash differs from what the app last
wrote, a timestamped backup is made — no exceptions." A step whose outputs were edited by hand
runs again; before it does, the runner copies those files to ``.ctstudio/backups/<time>/``
(same project-relative path) and says so in the step's log. If the backup cannot be made,
the step fails and the edited file is left as it is.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from build_runner_helpers import build, make_root, step

from ctstudio.core.build import backups
from ctstudio.core.build.backups import BACKUP_DIR
from ctstudio.core.build.events import LogLine, NodeFailed

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_root(tmp_path)


def made(root: Path) -> Path:
    return root / ".ctstudio" / "stage" / "a"  # what step(root, "a") writes


def kept(root: Path) -> list[Path]:
    folder = root / BACKUP_DIR
    return sorted(p for p in folder.rglob("*") if p.is_file()) if folder.exists() else []


def test_an_untouched_output_is_not_backed_up(root: Path) -> None:
    build(root, [step(root, "a")])
    made(root).unlink()  # gone: nothing to lose
    build(root, [step(root, "a", params={"changed": True})])
    assert kept(root) == []


def test_an_edited_output_is_backed_up_before_the_step_runs_again(root: Path) -> None:
    build(root, [step(root, "a")])
    made(root).write_text("my hand edit", encoding="utf-8")
    summary, rec = build(root, [step(root, "a")])
    assert summary.ran == ("a",)
    [copy] = kept(root)
    assert copy.read_text(encoding="utf-8") == "my hand edit"
    assert copy.relative_to(root / BACKUP_DIR).parts[1:] == (".ctstudio", "stage", "a")
    shown = copy.parent.parent.parent.relative_to(root).as_posix()
    said = [e.text for e in rec.events if isinstance(e, LogLine) and e.node_id == "a"]
    assert said == [f"Backed up 1 file you edited to {shown}/ before replacing it."]
    assert made(root).read_text(encoding="utf-8") == "a", "then the step ran as usual"


def test_two_backups_never_share_a_folder(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backups, "_stamp", lambda: "2026-11-03T00-00-00.000000Z")
    build(root, [step(root, "a")])
    for edit in ("first edit", "second edit"):
        made(root).write_text(edit, encoding="utf-8")
        build(root, [step(root, "a")])
    texts = sorted(p.read_text(encoding="utf-8") for p in kept(root))
    assert texts == ["first edit", "second edit"]


def test_a_backup_folder_that_cannot_be_created_keeps_the_edit(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(root, [step(root, "a")])
    made(root).write_text("my hand edit", encoding="utf-8")

    def denied(*_a: object, **_k: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(backups, "_new_folder", denied)
    summary, rec = build(root, [step(root, "a")])
    [failed] = [e for e in rec.events if isinstance(e, NodeFailed)]
    assert summary.failed == ("a",)
    assert "Could not back up .ctstudio/stage/a" in failed.message
    assert made(root).read_text(encoding="utf-8") == "my hand edit"


def test_a_backup_that_fails_stops_the_step_and_keeps_the_edit(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(root, [step(root, "a")])
    made(root).write_text("my hand edit", encoding="utf-8")

    def full(*_a: object, **_k: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(backups.shutil, "copy2", full)
    summary, rec = build(root, [step(root, "a")])
    [failed] = [e for e in rec.events if isinstance(e, NodeFailed)]
    assert summary.failed == ("a",)
    assert failed.message == (
        "Could not back up .ctstudio/stage/a, which you edited, before replacing it: "
        "No space left on device."
    )
    assert failed.hint == "Free some disk space, then build again. Your edit was not touched."
    assert made(root).read_text(encoding="utf-8") == "my hand edit"
