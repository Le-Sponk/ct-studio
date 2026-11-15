"""Public custom-Wine header faults, helper output and fresh post-helper runtime."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from custom_wine_helpers import converted, outcome, request

from ctstudio.core.errors import ToolFailed, ToolFailedToStart, ToolNotFound
from ctstudio.core.tools import wine
from ctstudio.core.tools.process import RunResult


@pytest.mark.parametrize("role", ["exe", "registry"])
@pytest.mark.parametrize(
    "failure",
    [
        PermissionError("denied"),
        RuntimeError("loop"),
        ValueError("invalid"),
        KeyboardInterrupt(),
        SystemExit(29),
    ],
)
def test_public_header_read_causes_and_interrupts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, failure: BaseException
) -> None:
    r = request(tmp_path, monkeypatch)
    target = r.exe if role == "exe" else r.prefix / "system.reg"
    real = Path.open
    seen: list[Path] = []

    def fault(
        self: Path, mode: str = "r", *, encoding: str | None = None, errors: str | None = None
    ) -> object:
        if self == target:
            seen.append(self)
            raise failure
        return real(self, mode, encoding=encoding, errors=errors)

    with monkeypatch.context() as context:
        context.setattr(Path, "open", fault)
        result = outcome(r.open)
    assert seen == [target] and r.conversions == [] and r.launches == []
    if isinstance(failure, Exception):
        assert isinstance(result, wine.WineError), result
        assert result.__cause__ is failure and result.hint
    else:
        assert result is failure


@pytest.mark.parametrize("role", ["exe", "launcher", "registry"])
@pytest.mark.parametrize("damage", ["missing", "damaged"])
def test_real_launch_boundary_revalidates_after_helper_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, damage: str
) -> None:
    r = request(tmp_path, monkeypatch)
    target = r.prefix / "system.reg" if role == "registry" else getattr(r, role)
    seen: list[Path] = []

    def change(path: Path, *, wine: Path, prefix: Path) -> str:
        seen.append(path)
        if damage == "missing":
            target.unlink()
        elif role == "launcher":
            target.unlink()
            target.mkdir()
        else:
            target.write_bytes(b"damaged header")
        return converted(path)

    monkeypatch.setattr(wine, "windows_path", change)
    result = outcome(r.open)
    assert isinstance(result, ToolNotFound if role == "launcher" else wine.WineError), result
    assert result.hint and seen == [r.document.resolve()] and r.launches == []


@pytest.mark.parametrize("answer", ["", "not a Windows path", "Z:\\unsafe\0", "Z:\\unsafe\ud800"])
def test_real_converter_output_cannot_bypass_safe_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    from ctstudio.core.tools.editors import EditorError

    r = request(tmp_path, monkeypatch)

    def output(cmd: Sequence[str | Path], **kwargs: object) -> RunResult:
        r.convert(cmd, **kwargs)
        return RunResult(0, 0, answer + "\n", "", None)

    monkeypatch.setattr(wine, "run", output)
    result = outcome(r.open)
    assert isinstance(result, (wine.WineError, EditorError)), result
    assert result.hint and len(r.conversions) == 1 and r.launches == []


@pytest.mark.parametrize("stage", ["helper", "start"])
@pytest.mark.parametrize("failure", [ToolFailedToStart("Wine", "denied"), ToolNotFound("Wine")])
def test_typed_process_failures_keep_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, failure: Exception
) -> None:
    r = request(tmp_path, monkeypatch)
    previous = OSError("original cause")
    failure.__cause__ = previous
    seen: list[str] = []

    def fail(*args: object, **kwargs: object) -> int:
        seen.append(stage)
        raise failure

    monkeypatch.setattr(wine, "run" if stage == "helper" else "launch_detached", fail)
    result = outcome(r.open)
    assert isinstance(result, BaseException) and result is failure
    assert result.__cause__ is previous and seen == [stage] and r.launches == []


@pytest.mark.parametrize(
    "stderr", ["Wine Mono is not installed", "Bad EXE format", "other startup failure"]
)
def test_public_start_errors_use_existing_wine_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stderr: str
) -> None:
    r = request(tmp_path, monkeypatch)
    failure = ToolFailed([str(r.launcher)], 42, stderr, tmp_path / "synthetic.log")
    previous = PermissionError("original cause")
    failure.__cause__ = previous

    def fail(*args: object, **kwargs: object) -> int:
        raise failure

    monkeypatch.setattr(wine, "launch_detached", fail)
    result = outcome(r.open)
    if stderr == "other startup failure":
        assert result is failure and failure.__cause__ is previous
    else:
        assert isinstance(result, wine.WineError), result
        assert result.__cause__ is failure and result.details == failure.details and result.hint
        assert (".NET" if "Mono" in stderr else "architecture") in result.user_message
    assert len(r.conversions) == 1 and r.launches == []
