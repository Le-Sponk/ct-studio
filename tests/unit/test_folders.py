"""P5-T03h portable directory dispatch, never document associations."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from ctstudio.core.errors import ProjectError, ToolNotFound
from ctstudio.core.tools import folders

pytestmark = pytest.mark.timeout(30)


def test_windows_dispatches_only_the_resolved_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "dossier café 日本"
    target.mkdir()
    windows = tmp_path / "Windows"
    windows.mkdir()
    exe = windows / "explorer.exe"
    exe.write_bytes(b"synthetic executable identity; never launched")
    (windows / "other.exe").write_bytes(b"synthetic executable-name decoy")
    monkeypatch.setenv("WINDIR", str(windows))
    monkeypatch.setattr(folders.platform, "current_os", lambda: "windows")
    calls: list[tuple[list[str | Path], Path, float]] = []

    def launch(cmd: list[str | Path], *, cwd: Path, watch: float) -> int:
        assert Path(cmd[0]).is_absolute(), "real runner rejects bare executable names"
        calls.append((cmd, cwd, watch))
        return 4321

    monkeypatch.setattr(folders.process, "launch_detached", launch)
    result = folders.open_folder(target / ".." / target.name)
    assert calls == [([exe.resolve(), str(target.resolve())], target.resolve(), 0.0)]
    assert result == folders.OpenedFolder(target.resolve(), 4321)


@pytest.fixture
def launches(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str | Path], Path, float]]:
    calls: list[tuple[list[str | Path], Path, float]] = []

    def launch(cmd: list[str | Path], *, cwd: Path, watch: float) -> int:
        assert Path(cmd[0]).is_absolute(), "real runner rejects bare executable names"
        calls.append((cmd, cwd, watch))
        return 4321

    monkeypatch.setattr(folders.process, "launch_detached", launch)
    return calls


def test_linux_resolves_which_result_and_watches_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[tuple[list[str | Path], Path, float]],
) -> None:
    target = tmp_path / "-folder café 日本.blend"
    target.mkdir()
    exe = tmp_path / "bin café" / "xdg-open"
    exe.parent.mkdir()
    exe.write_bytes(b"synthetic Linux opener identity")
    queries: list[str] = []

    def which(name: str) -> str:
        queries.append(name)
        return str(exe.relative_to(tmp_path))

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WINDIR", raising=False)
    monkeypatch.setattr(folders.platform, "current_os", lambda: "linux")
    monkeypatch.setattr(folders.shutil, "which", which)
    result = folders.open_folder(Path(target.name))
    assert queries == ["xdg-open"]
    assert launches == [([exe.resolve(), str(target.resolve())], target.resolve(), 0.4)]
    assert result == folders.OpenedFolder(target.resolve(), 4321)


def test_receipt_is_frozen_and_contains_only_folder_and_dispatch_pid() -> None:
    receipt = folders.OpenedFolder(Path("folder"), 23)
    assert [field.name for field in fields(receipt)] == ["folder", "pid"]
    field_name = "pid"
    with pytest.raises(FrozenInstanceError):
        setattr(receipt, field_name, 99)


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_missing_directories_and_document_associations_are_refused_without_writes(
    kind: str,
    tmp_path: Path,
    launches: list[tuple[list[str | Path], Path, float]],
) -> None:
    target = tmp_path / "document.blend"
    if kind == "file":
        target.write_bytes(b"synthetic document; never launch its association")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ProjectError, match=r"folder|directory") as caught:
        folders.open_folder(target)
    assert caught.value.hint
    assert launches == []
    assert target.exists() == (kind == "file")
    assert before == {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("windir", [None, "", "relative", "missing", "no-exe", "exe-dir"])
def test_windows_requires_absolute_windir_and_existing_explorer(
    windir: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[tuple[list[str | Path], Path, float]],
) -> None:
    monkeypatch.setattr(folders.platform, "current_os", lambda: "windows")
    if windir is None:
        monkeypatch.delenv("WINDIR", raising=False)
    elif windir in ("missing", "no-exe", "exe-dir"):
        root = tmp_path / windir
        if windir != "missing":
            root.mkdir()
        if windir == "exe-dir":
            (root / "explorer.exe").mkdir()
        monkeypatch.setenv("WINDIR", str(root))
    else:
        monkeypatch.setenv("WINDIR", windir)
    with pytest.raises(ToolNotFound, match=r"Explorer|explorer") as caught:
        folders.open_folder(tmp_path)
    assert caught.value.hint
    assert launches == []


@pytest.mark.parametrize("found", [None, "missing", "directory"])
def test_linux_missing_opener_is_actionable_tool_not_found(
    found: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[tuple[list[str | Path], Path, float]],
) -> None:
    path = tmp_path / str(found)
    if found == "directory":
        path.mkdir()
    monkeypatch.setattr(folders.platform, "current_os", lambda: "linux")

    def which(_name: str) -> str | None:
        return None if found is None else str(path)

    monkeypatch.setattr(folders.shutil, "which", which)
    with pytest.raises(ToolNotFound, match="xdg-open") as caught:
        folders.open_folder(tmp_path)
    assert caught.value.hint and "xdg" in caught.value.hint
    assert launches == []


def test_windows_relative_windir_is_refused_even_with_a_real_decoy_explorer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[tuple[list[str | Path], Path, float]],
) -> None:
    decoy = tmp_path / "relative" / "explorer.exe"
    decoy.parent.mkdir()
    decoy.write_bytes(b"synthetic decoy: do not trust cwd or PATH")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WINDIR", "relative")
    monkeypatch.setattr(folders.platform, "current_os", lambda: "windows")
    with pytest.raises(ToolNotFound):
        folders.open_folder(tmp_path)
    assert launches == []


def test_windows_never_uses_path_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[tuple[list[str | Path], Path, float]],
) -> None:
    exe = tmp_path / "explorer.exe"
    exe.write_bytes(b"synthetic system explorer")
    monkeypatch.setenv("WINDIR", str(tmp_path))
    monkeypatch.setattr(folders.platform, "current_os", lambda: "windows")

    def forbidden(_name: str) -> str:
        pytest.fail("Explorer must be found only inside absolute WINDIR, never on PATH")

    monkeypatch.setattr(folders.shutil, "which", forbidden)
    folders.open_folder(tmp_path)
    assert launches == [([exe.resolve(), str(tmp_path.resolve())], tmp_path.resolve(), 0.0)]


def test_unsupported_platform_is_typed_and_never_launches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[tuple[list[str | Path], Path, float]],
) -> None:
    monkeypatch.setattr(folders.platform, "current_os", lambda: "other")
    with pytest.raises(ProjectError, match="support") as caught:
        folders.open_folder(tmp_path)
    assert caught.value.hint
    assert launches == []
