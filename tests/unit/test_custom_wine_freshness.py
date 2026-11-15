"""Custom request freshness, validation ordering and original failure identities."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from custom_wine_helpers import converted, outcome, request

from ctstudio.core.errors import ToolNotFound
from ctstudio.core.tools import wine
from ctstudio.core.tools.editors import EditorError, Launched


@pytest.mark.parametrize("role", ["document", "project"])
def test_helper_changes_cannot_dispatch_stale_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    r = request(tmp_path, monkeypatch)
    target = getattr(r, role)

    def change(path: Path, *, wine: Path, prefix: Path) -> str:
        if target.is_dir():
            target.rmdir()
        else:
            target.unlink()
        return converted(path)

    monkeypatch.setattr(wine, "windows_path", change)
    result = outcome(r.open)
    assert isinstance(result, EditorError), result
    assert result.hint and r.launches == []


@pytest.mark.parametrize("role", ["exe", "document", "project", "launcher", "prefix"])
@pytest.mark.parametrize("damage", ["missing", "kind", "nul", "unicode"])
def test_invalid_paths_refuse_before_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, damage: str
) -> None:
    r = request(tmp_path, monkeypatch)
    target = getattr(r, role)
    if damage in ("nul", "unicode"):
        setattr(r, role, Path(str(target) + ("\0" if damage == "nul" else "\ud800")))
    else:
        if target.is_dir():
            if role == "prefix":
                (target / "system.reg").unlink()
            target.rmdir()
            if damage == "kind":
                target.write_bytes(b"not a directory")
        else:
            target.unlink()
            if damage == "kind":
                target.mkdir()
    result = outcome(r.open)
    expected = (
        ToolNotFound
        if role in ("exe", "launcher")
        else EditorError
        if role in ("document", "project")
        else wine.WineError
    )
    assert isinstance(result, expected), result
    assert result.hint and r.conversions == [] and r.launches == []


@pytest.mark.parametrize("arch", ["win32", "win64"])
@pytest.mark.parametrize(
    "damage", ["registry-missing", "registry-damaged", "pe-damaged", "incompatible"]
)
def test_headers_refuse_before_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arch: str, damage: str
) -> None:
    r = request(tmp_path, monkeypatch, arch, "win32" if damage == "incompatible" else "win64")
    if damage == "incompatible" and arch == "win32":
        r.exe.write_bytes(b"MZ truncated")
    elif damage == "pe-damaged":
        r.exe.write_bytes(b"bad PE")
    elif damage == "registry-missing":
        (r.prefix / "system.reg").unlink()
    elif damage == "registry-damaged":
        (r.prefix / "system.reg").write_bytes(b"#arch=damaged\n")
    result = outcome(r.open)
    assert isinstance(result, wine.WineError), result
    assert result.hint and r.conversions == [] and r.launches == []


@pytest.mark.parametrize("role", ["exe", "document", "project", "launcher", "prefix", "registry"])
@pytest.mark.parametrize(
    "failure",
    [
        PermissionError("denied"),
        RuntimeError("loop"),
        ValueError("bad stat"),
        KeyboardInterrupt(),
        SystemExit(29),
    ],
)
def test_inspection_causes_interrupts_and_no_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, failure: BaseException
) -> None:
    r = request(tmp_path, monkeypatch)
    target = r.prefix / "system.reg" if role == "registry" else getattr(r, role)
    real = Path.stat
    observed: list[Path] = []

    def fault(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == target:
            observed.append(self)
            raise failure
        return real(self, follow_symlinks=follow_symlinks)

    with monkeypatch.context() as context:
        context.setattr(Path, "stat", fault)
        result = outcome(r.open)
    assert observed and r.conversions == [] and r.launches == []
    if isinstance(failure, Exception):
        expected = (
            ToolNotFound
            if role in ("exe", "launcher")
            else EditorError
            if role in ("document", "project")
            else wine.WineError
        )
        assert isinstance(result, expected), result
        assert result.__cause__ is failure and result.hint
    else:
        assert result is failure


@pytest.mark.parametrize("stage", ["helper", "start"])
@pytest.mark.parametrize(
    "failure",
    [
        PermissionError("denied"),
        RuntimeError("original"),
        ValueError("invalid"),
        KeyboardInterrupt(),
        SystemExit(29),
    ],
)
def test_helper_start_failures_escape_identically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, failure: BaseException
) -> None:
    r = request(tmp_path, monkeypatch)
    original = OSError("earlier cause")
    failure.__cause__ = original
    observed: list[str] = []

    def fault(*args: object, **kwargs: object) -> object:
        observed.append(stage)
        raise failure

    monkeypatch.setattr(wine, "run" if stage == "helper" else "launch_detached", fault)
    result = outcome(r.open)
    assert isinstance(result, BaseException) and result is failure
    assert result.__cause__ is original
    assert observed == [stage] and r.launches == []
    assert len(r.conversions) == (0 if stage == "helper" else 1)


@pytest.mark.parametrize("role", ["exe", "document", "project", "launcher", "prefix", "registry"])
def test_each_request_freshly_checks_deleted_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    r = request(tmp_path, monkeypatch)
    assert isinstance(r.open(), Launched)
    r.conversions.clear()
    r.launches.clear()
    target = r.prefix / "system.reg" if role == "registry" else getattr(r, role)
    if target.is_dir():
        if role == "prefix":
            (target / "system.reg").unlink()
        target.rmdir()
    else:
        target.unlink()
    result = outcome(r.open)
    assert isinstance(result, (EditorError, ToolNotFound, wine.WineError)), result
    assert result.hint and r.conversions == [] and r.launches == []
