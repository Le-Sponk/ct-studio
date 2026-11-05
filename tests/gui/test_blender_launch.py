"""Blocking launch contracts using synthetic documents, never game assets or real editors."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

import pytest

from ctstudio.core.errors import ProjectError, ToolFailedToStart, ToolNotFound
from ctstudio.core.project import settings
from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors
from ctstudio.gui.blender_launch import BlenderLaunchService


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    with Project.create(tmp_path / "project café 空", "Synthetic launch") as opened:
        source = opened.root / "source café 空.blend"
        source.write_bytes(b"synthetic document; not a Blender file")
        opened.manifest = replace(
            opened.manifest,
            project=replace(opened.manifest.project, blend=source.name),
        )
        yield opened


def test_default_opener_forwards_current_source_and_settings_to_core(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "Blender café 空"
    executable.write_bytes(b"stand-in; launch_detached is intercepted")
    path = tmp_path / "settings.json"
    settings.save(settings.UserSettings({"blender": str(executable)}), path)
    calls: list[tuple[tuple[str | Path, ...], Path | None]] = []

    def detached(argv: Sequence[str | Path], *, cwd: Path | None = None) -> int:
        calls.append((tuple(argv), cwd))
        return 4321

    def forbidden_discovery(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("configured launch must not discover Blender")

    monkeypatch.setattr(editors, "discover", forbidden_discovery)
    monkeypatch.setattr(editors, "launch_detached", detached)
    result = BlenderLaunchService(settings_path=path).launch(project)
    document = (project.root / "source café 空.blend").resolve()
    assert calls == [((executable.resolve(), document), document.parent)]
    assert result == editors.Launched("blender", 4321, document, ())


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path, Path | None]] = []
        self.result = editors.Launched("blender", 8765, Path("receipt.blend"), ("show me",))

    def __call__(
        self, tool_id: str, document: Path, *, executable: Path | None = None
    ) -> editors.Launched:
        self.calls.append((tool_id, document, executable))
        return self.result


@pytest.mark.parametrize("state", ["missing", "empty", "readonly", "closed"])
def test_initial_guards_precede_settings_or_editor_side_effects(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    if state in ("missing", "empty"):
        project.manifest = replace(
            project.manifest,
            project=replace(project.manifest.project, blend=None if state == "missing" else ""),
        )
    elif state == "closed":
        project.close()
    else:
        project = Project(project.root, project.manifest, None, "owned elsewhere")

    def forbidden(_path: Path | None = None) -> settings.UserSettings:
        raise AssertionError("refused projects must not read settings")

    monkeypatch.setattr(settings, "load", forbidden)
    opener = Recorder()
    with pytest.raises(Exception) as caught:
        BlenderLaunchService(settings_path=tmp_path / "settings.json", open_editor=opener).launch(
            project
        )
    assert isinstance(caught.value, ProjectError) and caught.value.hint
    assert not opener.calls


@pytest.mark.parametrize("change", ["root", "manifest", "equal_manifest", "closed"])
def test_project_changes_during_settings_preparation_refuse_launch(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    def changing_load(_path: Path | None = None) -> settings.UserSettings:
        if change == "root":
            project.root = project.root / "different"
        elif change == "closed":
            project.close()
        else:
            project.manifest = replace(
                project.manifest, extra={} if change == "equal_manifest" else {"changed": True}
            )
        return settings.UserSettings()

    monkeypatch.setattr(settings, "load", changing_load)
    opener = Recorder()
    with pytest.raises(Exception) as caught:
        BlenderLaunchService(settings_path=tmp_path / "settings.json", open_editor=opener).launch(
            project
        )
    assert isinstance(caught.value, ProjectError) and caught.value.hint
    assert not opener.calls


def tree(root: Path) -> dict[Path, tuple[bytes | None, int]]:
    return {
        p: (p.read_bytes() if p.is_file() else None, p.stat().st_mtime_ns) for p in root.rglob("*")
    }


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("mode", ["explicit", "default", "missing"])
def test_fresh_settings_source_result_and_no_writes(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, external: bool, mode: str
) -> None:
    document = (tmp_path if external else project.root) / "current café 空.blend"
    document.write_bytes(b"synthetic current source")
    project.manifest = replace(
        project.manifest,
        project=replace(
            project.manifest.project, blend=str(document) if external else document.name
        ),
    )
    path = tmp_path / "settings café.json"
    monkeypatch.setattr(settings, "default_path", lambda: path)
    opener = Recorder()
    service = BlenderLaunchService(
        settings_path=None if mode == "default" else path, open_editor=opener
    )
    for number in (1, 2):
        executable = tmp_path / f"Blender café {number}"
        expected = None if mode == "missing" and number == 1 else executable
        if expected is not None:
            settings.save(settings.UserSettings({"blender": str(expected)}), path)
        assert_launch_unchanged(service, project, opener, document, expected, tmp_path)
    assert len(opener.calls) == 2


def assert_launch_unchanged(
    service: BlenderLaunchService,
    project: Project,
    opener: Recorder,
    document: Path,
    expected: Path | None,
    tmp_path: Path,
) -> None:
    manifest, lock = project.manifest, project.lock
    before = tree(tmp_path)
    assert service.launch(project) is opener.result
    assert opener.calls[-1] == ("blender", document.resolve(), expected)
    assert project.manifest is manifest and project.lock is lock
    assert tree(tmp_path) == before


@pytest.mark.parametrize(
    "raw", [b"{", b"[]", b'{"format":999}', b'{"tools":{"blender":3}}', b"\xff"]
)
def test_corrupt_settings_fail_closed_unchanged(
    project: Project, tmp_path: Path, raw: bytes
) -> None:
    path = tmp_path / "broken.json"
    path.write_bytes(raw)
    before = tree(tmp_path)
    opener = Recorder()
    with pytest.raises(settings.SettingsError) as caught:
        BlenderLaunchService(settings_path=path, open_editor=opener).launch(project)
    assert caught.value.path == path and caught.value.hint
    assert not opener.calls
    assert tree(tmp_path) == before


@pytest.mark.parametrize("stage", ["resolve", "settings", "editor"])
@pytest.mark.parametrize(
    "error",
    [
        PermissionError("denied"),
        ValueError("invalid path"),
        RuntimeError("busy"),
        ProjectError("typed project"),
        settings.SettingsError(Path("settings"), "damaged"),
        editors.EditorError("blender", Path("source.blend"), "invalid"),
        ToolNotFound("Blender"),
        ToolFailedToStart("Blender", "OS refused"),
        KeyboardInterrupt(),
        SystemExit(7),
    ],
)
def test_errors_preserve_types_causes_and_interrupts(
    project: Project,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    error: BaseException,
) -> None:
    cause = OSError("original cause")
    error.__cause__ = cause

    def fail(*_args: object, **_kwargs: object) -> NoReturn:
        raise error

    opener = Recorder()
    if stage == "resolve":
        monkeypatch.setattr(Path, "resolve", fail)
    elif stage == "settings":
        monkeypatch.setattr(settings, "load", fail)
    service = BlenderLaunchService(
        settings_path=tmp_path / "settings.json",
        open_editor=fail if stage == "editor" else opener,
    )
    with pytest.raises(BaseException) as caught:
        service.launch(project)
    assert_preserved_error(caught.value, error, cause)
    assert not opener.calls


def assert_preserved_error(caught: BaseException, error: BaseException, cause: OSError) -> None:
    if isinstance(error, (OSError, ValueError, RuntimeError)):
        assert caught.__cause__ is error
        assert isinstance(caught, ProjectError) and caught.hint
        assert caught.details == str(error)
    else:
        assert caught is error and caught.__cause__ is cause


@pytest.mark.parametrize("fault", ["missing", "directory", "suffix", "executable", "discovery"])
def test_real_core_refusals_never_launch(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    source = project.root / "source café 空.blend"
    path = tmp_path / "settings.json"
    if fault == "missing":
        source.unlink()
    elif fault == "directory":
        source.unlink()
        source.mkdir()
    elif fault == "suffix":
        project.manifest = replace(
            project.manifest, project=replace(project.manifest.project, blend="wrong.txt")
        )
    elif fault == "executable":
        settings.save(settings.UserSettings({"blender": str(tmp_path / "absent")}), path)

    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("invalid launch must not spawn")

    def undiscovered(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(editors, "discover", undiscovered)
    monkeypatch.setattr(editors, "launch_detached", forbidden)
    expected = ToolNotFound if fault in ("executable", "discovery") else editors.EditorError
    with pytest.raises(expected) as caught:
        BlenderLaunchService(settings_path=path).launch(project)
    assert caught.value.hint
