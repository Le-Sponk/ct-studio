"""Folder discovery, filesystem and dispatch failure boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.errors import (
    Cancelled,
    CTStudioError,
    ProjectError,
    ToolFailed,
    ToolFailedToStart,
    ToolNotFound,
)
from ctstudio.core.tools import folders

pytestmark = pytest.mark.timeout(30)
_STAGES = ["resolve", "is_dir", "platform", "discovery", "launch"]


def inject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stage: str, fault: BaseException
) -> list[tuple[list[str | Path], Path, float]]:
    exe = tmp_path / "synthetic-opener"
    exe.write_bytes(b"synthetic identity; mock runner only")
    calls: list[tuple[list[str | Path], Path, float]] = []
    monkeypatch.setattr(folders.platform, "current_os", lambda: "linux")

    def which(_name: str) -> str:
        return str(exe)

    monkeypatch.setattr(folders.shutil, "which", which)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise fault

    def launch(cmd: list[str | Path], *, cwd: Path, watch: float) -> int:
        assert Path(cmd[0]).is_absolute(), "mock must enforce the real runner contract"
        calls.append((cmd, cwd, watch))
        raise fault

    monkeypatch.setattr(folders.process, "launch_detached", launch)
    if stage in ("resolve", "is_dir"):
        original_resolve, original_is_dir = Path.resolve, Path.is_dir

        def resolve(path: Path, strict: bool = False) -> Path:
            if path == tmp_path:
                raise fault
            return original_resolve(path, strict=strict)

        def is_dir(path: Path) -> bool:
            if path == tmp_path:
                raise fault
            return original_is_dir(path)

        monkeypatch.setattr(Path, stage, resolve if stage == "resolve" else is_dir)
    elif stage == "platform":
        monkeypatch.setattr(folders.platform, "current_os", broken)
    elif stage == "discovery":
        monkeypatch.setattr(folders.shutil, "which", broken)
    return calls


@pytest.mark.parametrize("stage", _STAGES)
@pytest.mark.parametrize("fault_type", [OSError, ValueError, RuntimeError])
def test_ordinary_failures_are_actionable_project_errors_with_original_cause(
    stage: str,
    fault_type: type[Exception],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fault = fault_type("synthetic failure detail")
    calls = inject(monkeypatch, tmp_path, stage, fault)
    with pytest.raises((OSError, ValueError, RuntimeError, ProjectError)) as caught:
        folders.open_folder(tmp_path)
    error = caught.value
    assert isinstance(error, ProjectError)
    assert error is not fault
    assert error.__cause__ is fault
    assert str(tmp_path) in error.user_message
    assert "synthetic failure detail" in error.user_message
    assert error.hint and "folder" in error.hint
    assert len(calls) == (1 if stage == "launch" else 0)


@pytest.mark.parametrize("stage", _STAGES)
@pytest.mark.parametrize(
    "fault",
    [
        CTStudioError("original", hint="original hint", details="original details"),
        ProjectError("original project error"),
        ToolNotFound("synthetic-opener"),
        ToolFailed(["synthetic-opener"], 4, "original diagnostic", None),
        ToolFailedToStart("synthetic-opener", "permission denied"),
        Cancelled("folder dispatch"),
        KeyboardInterrupt("original interrupt"),
        SystemExit(7),
    ],
)
def test_typed_errors_and_interrupts_preserve_identity_and_cause(
    stage: str,
    fault: BaseException,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_cause = OSError("original cause")
    fault.__cause__ = original_cause
    calls = inject(monkeypatch, tmp_path, stage, fault)
    with pytest.raises((CTStudioError, KeyboardInterrupt, SystemExit)) as caught:
        folders.open_folder(tmp_path)
    assert caught.value is fault
    assert caught.value.__cause__ is original_cause
    assert len(calls) == (1 if stage == "launch" else 0)


def test_malformed_absolute_folder_is_typed_without_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> int:
        pytest.fail("Malformed folders must never reach desktop dispatch")

    monkeypatch.setattr(folders.process, "launch_detached", forbidden)
    with pytest.raises(ProjectError) as caught:
        folders.open_folder(tmp_path / "bad\0folder")
    assert caught.value.hint
    assert isinstance(caught.value.__cause__, (OSError, ValueError))
