"""Checked Wine runtime and opaque argv; synthetic programs, not Wine/editor loading."""

from __future__ import annotations

import json
import os
import struct
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import cast

import pytest
from fakes.install import install_program

from ctstudio.core.errors import ToolFailed, ToolNotFound
from ctstudio.core.tools import wine
from ctstudio.core.tools.process import RunResult

pytestmark = pytest.mark.timeout(30)


def _outcome[T](call: Callable[[], T]) -> T | BaseException:
    try:
        return call()
    except BaseException as error:
        return error


def _pe(path: Path, arch: str = "win32") -> Path:
    data = bytearray(256)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, 0x14C if arch == "win32" else 0x8664)
    struct.pack_into("<H", data, 0x98, 0x10B if arch == "win32" else 0x20B)
    path.write_bytes(data)
    return path


def _prefix(path: Path, arch: str = "win64") -> Path:
    path.mkdir()
    (path / "system.reg").write_text(f"WINE REGISTRY Version 2\n#arch={arch}\n", encoding="utf-8")
    return path


def _spies(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    calls: list[tuple[str, list[str]]] = []

    def convert(cmd: Sequence[str | Path], **_kwargs: object) -> RunResult:
        assert Path(cmd[0]).is_absolute()
        calls.append(("convert", list(map(str, cmd))))
        return RunResult(0, 0.1, "Z:\\converted\\document\n", "", None)

    def launch(cmd: Sequence[str | Path], **_kwargs: object) -> int:
        assert Path(cmd[0]).is_absolute()
        calls.append(("launch", list(map(str, cmd))))
        return 734

    monkeypatch.setattr(wine, "run", convert)
    monkeypatch.setattr(wine, "launch_detached", launch)
    return calls


@pytest.mark.parametrize("damage", ["missing", "no-registry", "unknown"])
def test_32_bit_launch_checks_prefix_before_any_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    exe = _pe(tmp_path / "editor.exe")
    launcher = tmp_path / "wine"
    launcher.write_bytes(b"synthetic Wine")
    document = tmp_path / "document"
    document.write_bytes(b"synthetic document")
    prefix = tmp_path / "prefix"
    if damage != "missing":
        prefix.mkdir()
    if damage == "unknown":
        (prefix / "system.reg").write_bytes(b"#arch=unknown\n")
    calls = _spies(monkeypatch)
    result = _outcome(lambda: wine.launch(exe, document, (), wine=launcher, prefix=prefix))
    assert isinstance(result, wine.WineError), result
    assert result.hint and calls == []
    assert document.read_bytes() == b"synthetic document"


def _runtime(
    tmp_path: Path, arch: str = "win32", prefix_arch: str = "win64"
) -> tuple[Path, Path, Path]:
    exe = _pe(tmp_path / "editor.exe", arch)
    launcher = tmp_path / "wine"
    launcher.write_bytes(b"synthetic Wine")
    return exe, launcher, _prefix(tmp_path / "prefix é", prefix_arch)


@pytest.mark.parametrize(
    ("arch", "prefix_arch"), [("win32", "win32"), ("win32", "win64"), ("win64", "win64")]
)
def test_complete_argv_preserves_every_token_and_startup_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arch: str, prefix_arch: str
) -> None:
    exe, launcher, prefix = _runtime(tmp_path, arch, prefix_arch)
    calls = _spies(monkeypatch)
    observed: list[tuple[list[str], dict[str, object]]] = []

    def start(cmd: Sequence[str | Path], **kwargs: object) -> int:
        assert Path(cmd[0]).is_absolute()
        observed.append((list(map(str, cmd)), kwargs))
        return 734

    monkeypatch.setattr(wine, "launch_detached", start)
    tokens = ("Z:\\dossier é 日本\\document", "", "a b", "{file}", "; & | > $", '"quoted"')
    result = _outcome(
        lambda: wine.launch_argv(exe, tokens, cwd=tmp_path, wine=launcher, prefix=prefix)
    )
    assert result == 734, result
    assert observed == [
        (
            [str(launcher.resolve()), str(exe.resolve()), *tokens],
            {
                "cwd": tmp_path.resolve(),
                "env": {"WINEPREFIX": str(prefix.resolve())},
                "watch": wine.WATCH_SECONDS,
            },
        )
    ]
    assert calls == []


@pytest.mark.parametrize("arch", ["win32", "win64"])
def test_complete_argv_refuses_incompatible_or_damaged_prefixes_before_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arch: str
) -> None:
    exe, launcher, prefix = _runtime(tmp_path, arch, "win32")
    if arch == "win32":
        (prefix / "system.reg").unlink()
    calls = _spies(monkeypatch)
    result = _outcome(lambda: wine.launch_argv(exe, (), cwd=tmp_path, wine=launcher, prefix=prefix))
    assert isinstance(result, wine.WineError), result
    assert result.hint and calls == []


@pytest.mark.parametrize("role", ["exe", "wine", "prefix", "cwd"])
@pytest.mark.parametrize("damage", ["missing", "wrong-kind", "\0", "\ud800"])
def test_runtime_path_damage_is_typed_before_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, damage: str
) -> None:
    exe, launcher, prefix = _runtime(tmp_path)
    cwd = tmp_path / "working"
    cwd.mkdir()
    paths = {"exe": exe, "wine": launcher, "prefix": prefix, "cwd": cwd}
    target = paths[role]
    if damage in ("missing", "wrong-kind"):
        if target.is_dir():
            if role == "prefix":
                (target / "system.reg").unlink()
            target.rmdir()
        else:
            target.unlink()
        if damage == "wrong-kind":
            if role in ("exe", "wine"):
                target.mkdir()
            else:
                target.write_bytes(b"not a directory")
    else:
        paths[role] = Path(str(target) + damage)
    calls = _spies(monkeypatch)
    result = _outcome(
        lambda: wine.launch_argv(
            paths["exe"], (), cwd=paths["cwd"], wine=paths["wine"], prefix=paths["prefix"]
        )
    )
    assert isinstance(result, ToolNotFound if role == "wine" else wine.WineError), result
    assert result.hint and calls == []


@pytest.mark.parametrize("role", ["exe", "wine", "prefix", "cwd"])
@pytest.mark.parametrize(
    "failure", [PermissionError("denied"), RuntimeError("loop"), ValueError("invalid")]
)
def test_runtime_inspection_cause_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, failure: Exception
) -> None:
    exe, launcher, prefix = _runtime(tmp_path)
    cwd = tmp_path / "working"
    cwd.mkdir()
    target = {"exe": exe, "wine": launcher, "prefix": prefix, "cwd": cwd}[role]
    calls = _spies(monkeypatch)
    real = Path.resolve
    observed: list[Path] = []

    def fault(self: Path, strict: bool = False) -> Path:
        if self == target:
            observed.append(self)
            raise failure
        return real(self, strict=strict)

    with monkeypatch.context() as context:
        context.setattr(Path, "resolve", fault)
        result = _outcome(lambda: wine.launch_argv(exe, (), cwd=cwd, wine=launcher, prefix=prefix))
    assert isinstance(result, ToolNotFound if role == "wine" else wine.WineError), result
    assert result.hint and result.__cause__ is failure
    assert observed == [target] and calls == []


def test_runtime_is_fresh_and_returns_canonical_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe, launcher, prefix = _runtime(tmp_path)
    monkeypatch.chdir(tmp_path)
    relative = (Path(exe.name), Path(launcher.name), Path(prefix.name))
    result = _outcome(
        lambda: wine.validate_runtime(relative[0], wine=relative[1], prefix=relative[2])
    )
    assert result == (exe.resolve(), launcher.resolve(), prefix.resolve())
    calls = _spies(monkeypatch)
    assert wine.launch_argv(exe, (), cwd=tmp_path, wine=launcher, prefix=prefix) == 734
    (prefix / "system.reg").write_bytes(b"#arch=damaged\n")
    result = _outcome(lambda: wine.launch_argv(exe, (), cwd=tmp_path, wine=launcher, prefix=prefix))
    assert isinstance(result, wine.WineError) and len(calls) == 1
    (prefix / "system.reg").write_bytes(b"#arch=win64\n")
    exe.write_bytes(b"damaged executable")
    result = _outcome(lambda: wine.launch_argv(exe, (), cwd=tmp_path, wine=launcher, prefix=prefix))
    assert isinstance(result, wine.WineError) and len(calls) == 1
    _pe(exe)
    assert wine.launch_argv(exe, (), cwd=tmp_path, wine=launcher, prefix=prefix) == 734
    assert len(calls) == 2


@pytest.mark.parametrize("token", ["a\0b", "\ud800"])
def test_unsafe_tokens_are_typed_before_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    exe, launcher, prefix = _runtime(tmp_path)
    calls = _spies(monkeypatch)
    result = _outcome(
        lambda: wine.launch_argv(exe, (token,), cwd=tmp_path, wine=launcher, prefix=prefix)
    )
    assert isinstance(result, wine.WineError), result
    assert result.hint and result.__cause__ is not None and calls == []


@pytest.mark.parametrize(
    "stderr", ["Wine Mono is not installed", "Bad EXE format", "other failure"]
)
def test_early_failures_share_explanation_and_preserve_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stderr: str
) -> None:
    exe, launcher, prefix = _runtime(tmp_path)
    original = ToolFailed([str(launcher)], 42, stderr, tmp_path / "log")
    previous = PermissionError("previous cause")
    original.__cause__ = previous
    calls = _spies(monkeypatch)

    def fail(cmd: Sequence[str | Path], **_kwargs: object) -> int:
        calls.append(("launch", [str(token) for token in cmd]))
        raise original

    monkeypatch.setattr(wine, "launch_detached", fail)
    result = _outcome(lambda: wine.launch_argv(exe, (), cwd=tmp_path, wine=launcher, prefix=prefix))
    if stderr == "other failure":
        assert result is original and original.__cause__ is previous
    else:
        assert isinstance(result, wine.WineError), result
        assert result.__cause__ is original and result.details == original.details
        assert (".NET" if "Mono" in stderr else "architecture") in result.user_message
        assert result.hint
    assert len(calls) == 1


@pytest.mark.parametrize("role", ["exe", "prefix"])
@pytest.mark.parametrize(
    "failure",
    [
        PermissionError("denied"),
        RuntimeError("loop"),
        ValueError("invalid"),
        KeyboardInterrupt(),
        SystemExit(23),
    ],
)
def test_header_inspection_faults_are_typed_but_interrupts_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, failure: BaseException
) -> None:
    exe, launcher, prefix = _runtime(tmp_path)
    target = exe if role == "exe" else prefix / "system.reg"
    calls = _spies(monkeypatch)
    observed: list[Path] = []
    real = Path.open

    def fault(
        self: Path, mode: str = "r", *, encoding: str | None = None, errors: str | None = None
    ) -> object:
        if self == target:
            observed.append(self)
            raise failure
        return real(self, mode, encoding=encoding, errors=errors)

    with monkeypatch.context() as context:
        context.setattr(Path, "open", fault)
        result = _outcome(
            lambda: wine.launch_argv(exe, (), cwd=tmp_path, wine=launcher, prefix=prefix)
        )
    if isinstance(failure, Exception):
        assert isinstance(result, wine.WineError), result
        assert result.__cause__ is failure and result.hint
    else:
        assert result is failure
    assert observed == [target] and calls == []


def test_two_actual_synthetic_wine_processes_keep_tokens_and_bytes(tmp_path: Path) -> None:
    code = (
        "import json, os, pathlib, sys\n"
        "pending = pathlib.Path('receipt.pending')\n"
        "with pending.open('w', encoding='utf-8') as stream:\n"
        "    json.dump({'argv':sys.argv[1:], 'cwd':os.getcwd(),\n"
        "               'prefix':os.environ['WINEPREFIX'], 'pid':os.getpid()}, stream)\n"
        "os.replace(pending, 'receipt.json')\n"
    )
    launcher = install_program(tmp_path / "Wine é 日本" / "synthetic-wine", code)
    exe = _pe(tmp_path / "editor é.exe")
    prefix = _prefix(tmp_path / "prefix é 日本")
    launches: list[int] = []
    receipts: list[dict[str, object]] = []
    before = {path: path.read_bytes() for path in (launcher, exe, prefix / "system.reg")}
    for number in range(2):
        cwd = tmp_path / f"request é {number}"
        cwd.mkdir()
        document = cwd / "document 日本.brres"
        document.write_bytes(b"synthetic input")
        tokens = (str(document), "", "--name=日本 é", "a;b & c|d >$e", "{file}")
        result = _outcome(
            partial(wine.launch_argv, exe, tokens, cwd=cwd, wine=launcher, prefix=prefix)
        )
        assert isinstance(result, int) and result > 0, result
        receipt = cwd / "receipt.json"
        assert receipt.is_file(), "real watched process did not publish its receipt"
        data = cast("dict[str, object]", json.loads(receipt.read_text(encoding="utf-8")))
        assert data["argv"] == [str(exe.resolve()), *tokens]
        assert Path(str(data["cwd"])).resolve() == cwd.resolve()
        assert data["prefix"] == str(prefix.resolve())
        assert isinstance(data["pid"], int) and data["pid"] != os.getpid()
        assert document.read_bytes() == b"synthetic input"
        launches.append(result)
        receipts.append(data)
    assert launches[0] != launches[1] and receipts[0]["pid"] != receipts[1]["pid"]
    assert before == {path: path.read_bytes() for path in before}


@pytest.mark.parametrize("entrypoint", ["validate_runtime", "launch_argv", "launch"])
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
def test_registry_stat_cause_and_interrupts_reach_all_entrypoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entrypoint: str, failure: BaseException
) -> None:
    exe, launcher, prefix = _runtime(tmp_path)
    document = tmp_path / "synthetic document"
    document.write_bytes(b"unchanged input")
    target = prefix / "system.reg"
    calls = _spies(monkeypatch)
    observed: list[Path] = []
    real = Path.stat

    def fault(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == target:
            observed.append(self)
            raise failure
        return real(self, follow_symlinks=follow_symlinks)

    with monkeypatch.context() as context:
        context.setattr(Path, "stat", fault)
        if entrypoint == "validate_runtime":
            result = _outcome(lambda: wine.validate_runtime(exe, wine=launcher, prefix=prefix))
        elif entrypoint == "launch_argv":
            result = _outcome(
                lambda: wine.launch_argv(exe, (), cwd=tmp_path, wine=launcher, prefix=prefix)
            )
        else:
            result = _outcome(lambda: wine.launch(exe, document, (), wine=launcher, prefix=prefix))
    assert observed == [target] and calls == []
    if isinstance(failure, Exception):
        assert isinstance(result, wine.WineError), result
        assert result.__cause__ is failure and result.hint
    else:
        assert result is failure
    assert document.read_bytes() == b"unchanged input"
