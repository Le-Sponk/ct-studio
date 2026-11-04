"""P5-T02b: blocking recent-project history, using only synthetic settings."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import settings
from ctstudio.gui.recent_projects import RecentProject, RecentProjects, RecentResult

pytestmark = pytest.mark.timeout(30)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "config é" / "settings.json"
    monkeypatch.setattr(settings, "default_path", lambda: path)
    return path


def test_empty_history_never_creates_settings(isolated_settings: Path) -> None:
    assert RecentProjects().check() == RecentResult(())
    assert not isolated_settings.parent.exists()


def test_results_are_frozen_values(tmp_path: Path) -> None:
    entry = RecentProject(tmp_path, False)
    result = RecentResult((entry,))
    with pytest.raises(FrozenInstanceError):
        entry.__setattr__("missing", True)
    with pytest.raises(FrozenInstanceError):
        result.__setattr__("problem", "changed")
    assert result.entries == (entry,) and result.problem is None


def test_remember_persists_across_restart_with_backups_and_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "explicit settings é.json"
    first, second = tmp_path / "course 東京", tmp_path / "second é"
    first.mkdir()
    second.mkdir()
    original = {"format": 1, "tools": {"wszst": "/w", "future": "/f"}, "theme": {"x": [1]}}
    path.write_text(json.dumps(original), encoding="utf-8")
    before = path.read_bytes()
    service = RecentProjects(path)
    assert service.remember(first) == RecentResult((RecentProject(first.resolve(), False),))
    assert RecentProjects(path).check() == service.check()
    assert json.loads(path.read_text(encoding="utf-8")) == {
        **original,
        "recent_projects": [str(first.resolve())],
    }
    [backup] = path.parent.glob("*.bak")
    assert backup.read_bytes() == before
    previous = path.read_bytes()
    assert service.remember(second) == RecentResult(
        (RecentProject(second.resolve(), False), RecentProject(first.resolve(), False))
    )
    backups = list(path.parent.glob("*.bak"))
    assert len(backups) == 2 and previous in [p.read_bytes() for p in backups]
    assert RecentProjects(path).check() == service.check()


def test_check_marks_missing_and_files_without_pruning(
    tmp_path: Path, isolated_settings: Path
) -> None:
    folder, missing, file = tmp_path / "here é", tmp_path / "gone", tmp_path / "not a folder"
    folder.mkdir()
    file.write_text("user file", encoding="utf-8")
    settings.save(
        settings.UserSettings(
            other={"recent_projects": [str(p.resolve()) for p in (missing, folder, file)]}
        ),
        isolated_settings,
    )
    before = isolated_settings.read_bytes()
    assert RecentProjects().check() == RecentResult(
        (
            RecentProject(missing.resolve(), True),
            RecentProject(folder.resolve(), False),
            RecentProject(file.resolve(), True),
        )
    )
    assert isolated_settings.read_bytes() == before
    assert list(isolated_settings.parent.glob("*.bak")) == []
    missing.mkdir()
    assert RecentProjects().check().entries[0].missing is False


def test_newest_first_resolved_deduplication_and_ten_entry_limit(
    tmp_path: Path, isolated_settings: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    service = RecentProjects()
    roots = [tmp_path / f"track {number} é" for number in range(12)]
    for root in roots:
        service.remember(root)
    expected = list(reversed(roots[2:]))
    assert [entry.root for entry in service.check().entries] == expected
    assert all(entry.missing for entry in service.check().entries)
    alias = Path("track 4 é") / ".." / "track 4 é"
    result = service.remember(alias)
    expected = [roots[4], *[p for p in expected if p != roots[4]]]
    assert [entry.root for entry in result.entries] == expected
    stored = settings.load(isolated_settings).other["recent_projects"]
    assert stored == [str(p.resolve()) for p in expected]


def test_loaded_history_is_deduplicated_resolved_and_limited_without_writing(
    tmp_path: Path, isolated_settings: Path
) -> None:
    roots = [tmp_path / f"track {number}" for number in range(12)]
    values = [str(roots[0]), str(roots[0] / ".." / roots[0].name), *map(str, roots[1:])]
    settings.save(settings.UserSettings(other={"recent_projects": values}), isolated_settings)
    before = isolated_settings.read_bytes()
    assert [e.root for e in RecentProjects().check().entries] == roots[:10]
    assert isolated_settings.read_bytes() == before
    assert list(isolated_settings.parent.glob("*.bak")) == []


def test_remove_only_changes_history_and_preserves_missing_entries(
    tmp_path: Path, isolated_settings: Path
) -> None:
    first, missing = tmp_path / "user project", tmp_path / "gone"
    first.mkdir()
    marker = first / "keep.txt"
    marker.write_text("user work", encoding="utf-8")
    service = RecentProjects()
    service.remember(missing)
    service.remember(first)
    before = isolated_settings.read_bytes()
    result = service.remove(first / ".." / first.name)
    assert result == RecentResult((RecentProject(missing.resolve(), True),))
    assert marker.read_text(encoding="utf-8") == "user work"
    assert before in [p.read_bytes() for p in isolated_settings.parent.glob("*.bak")]
    assert RecentProjects().check() == result
    assert service.remove(tmp_path / "unknown") == result
    assert service.remove(missing) == RecentResult(())
    assert settings.load(isolated_settings).other["recent_projects"] == []


@pytest.mark.parametrize("operation", ["check", "remember", "remove"])
@pytest.mark.parametrize(
    "history", [None, {}, "", 7, [None], [5], [""], ["relative"], ["/bad\x00"]]
)
def test_malformed_history_is_reported_without_writing(
    operation: str, history: object, tmp_path: Path, isolated_settings: Path
) -> None:
    settings.save(settings.UserSettings(other={"recent_projects": history}), isolated_settings)
    before = isolated_settings.read_bytes()
    service = RecentProjects()
    method = getattr(service, operation)
    result = method() if operation == "check" else method(tmp_path / "opened")
    assert result.entries == ()
    assert result.problem is not None
    assert "recent_projects" in result.problem and "Next:" in result.problem
    assert str(isolated_settings) in result.problem
    assert isolated_settings.read_bytes() == before
    assert list(isolated_settings.parent.glob("*.bak")) == []


@pytest.mark.parametrize("operation", ["check", "remember", "remove"])
def test_absolute_history_with_nul_is_reported_without_writing(
    operation: str, tmp_path: Path, isolated_settings: Path
) -> None:
    history = [str(tmp_path / "invalid é") + "\x00"]
    settings.save(settings.UserSettings(other={"recent_projects": history}), isolated_settings)
    before = isolated_settings.read_bytes()
    method = getattr(RecentProjects(), operation)
    result = method() if operation == "check" else method(tmp_path)
    assert result.entries == () and result.problem
    assert "recent_projects" in result.problem
    assert isolated_settings.read_bytes() == before
    assert list(isolated_settings.parent.glob("*.bak")) == []


@pytest.mark.parametrize("operation", ["check", "remember", "remove"])
@pytest.mark.parametrize("raw", [b"{bad", b"[]", b'{"format": 2}', b'{"tools": []}', b"\xff"])
def test_corrupt_or_newer_settings_are_reported_without_writing(
    operation: str, raw: bytes, tmp_path: Path, isolated_settings: Path
) -> None:
    isolated_settings.parent.mkdir(parents=True)
    isolated_settings.write_bytes(raw)
    method = getattr(RecentProjects(), operation)
    result = method() if operation == "check" else method(tmp_path)
    assert result.entries == () and result.problem
    assert str(isolated_settings) in result.problem and "Next:" in result.problem
    assert isolated_settings.read_bytes() == raw
    assert list(isolated_settings.parent.glob("*.bak")) == []


def test_malformed_tail_is_not_hidden_by_the_limit(tmp_path: Path, isolated_settings: Path) -> None:
    roots = [str(tmp_path / str(i)) for i in range(10)]
    settings.save(
        settings.UserSettings(other={"recent_projects": [*roots, "relative"]}), isolated_settings
    )
    before = isolated_settings.read_bytes()
    assert RecentProjects().remember(tmp_path).problem is not None
    assert isolated_settings.read_bytes() == before
    assert list(isolated_settings.parent.glob("*.bak")) == []


@pytest.mark.parametrize("operation", ["check", "remember", "remove"])
def test_unreadable_settings_raise_a_typed_error(operation: str, isolated_settings: Path) -> None:
    isolated_settings.mkdir(parents=True)
    method = getattr(RecentProjects(), operation)
    with pytest.raises(ProjectError) as caught:
        method() if operation == "check" else method(isolated_settings.parent)
    assert caught.value.hint and caught.value.details
    assert isinstance(caught.value.__cause__, OSError)
    assert list(isolated_settings.iterdir()) == []


@pytest.mark.parametrize("operation", ["check", "remember", "remove"])
@pytest.mark.parametrize("failure", ["resolve", "is_dir", "loop"])
def test_filesystem_failures_are_typed_without_writing(
    operation: str,
    failure: str,
    tmp_path: Path,
    isolated_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "cannot check é"
    settings.save(settings.UserSettings(other={"recent_projects": [str(root)]}), isolated_settings)
    before = isolated_settings.read_bytes()
    error = RuntimeError("symlink loop") if failure == "loop" else PermissionError("denied")

    def fail(*args: object, **kwargs: object) -> object:
        raise error

    method = getattr(RecentProjects(), operation)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve" if failure == "loop" else failure, fail)
        with pytest.raises(ProjectError) as caught:
            method() if operation == "check" else method(tmp_path / "another")
    assert caught.value.hint and caught.value.details
    assert caught.value.__cause__ is error
    assert isolated_settings.read_bytes() == before
    assert list(isolated_settings.parent.glob("*.bak")) == []


@pytest.mark.parametrize("operation", ["remember", "remove"])
def test_save_oserror_is_typed(
    operation: str, isolated_settings: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = OSError("disk full")

    def fail(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(settings, "save", fail)
    with pytest.raises(ProjectError) as caught:
        getattr(RecentProjects(), operation)(isolated_settings.parent)
    assert caught.value.hint and caught.value.details
    assert caught.value.__cause__ is error
    assert not isolated_settings.exists()


def test_existing_project_error_is_not_hidden(
    isolated_settings: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = ProjectError("Could not back up settings.", hint="Check disk space.")

    def fail(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(settings, "save", fail)
    with pytest.raises(ProjectError) as caught:
        RecentProjects().remember(isolated_settings.parent)
    assert caught.value is error
    assert not isolated_settings.exists()


def test_blocking_check_runs_folder_checks_on_the_calling_worker(
    tmp_path: Path, isolated_settings: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "track é"
    settings.save(settings.UserSettings(other={"recent_projects": [str(root)]}), isolated_settings)
    seen: list[int] = []
    actual = Path.is_dir

    def observe(path: Path) -> bool:
        if path == root:
            seen.append(threading.get_ident())
        return actual(path)

    monkeypatch.setattr(Path, "is_dir", observe)
    service = RecentProjects()
    assert seen == []
    with ThreadPoolExecutor(max_workers=1) as worker:
        worker_id = worker.submit(threading.get_ident).result(timeout=5)
        result = worker.submit(service.check).result(timeout=5)
    assert result == RecentResult((RecentProject(root.resolve(), True),))
    assert seen == [worker_id] and worker_id != threading.get_ident()
