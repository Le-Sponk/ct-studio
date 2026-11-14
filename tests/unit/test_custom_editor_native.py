"""Explicit custom launches prove dispatch, not editor loading or health."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest
from fakes.install import install_program

from ctstudio.core.errors import ToolFailedToStart, ToolNotFound
from ctstudio.core.tools import custom_editors as adapter
from ctstudio.core.tools.editors import EditorError, Launched
from ctstudio.core.tools.spec import CustomTool


def _open(tool: CustomTool, document: Path, project: Path, tool_id: str = "custom") -> object:
    try:
        return adapter.open_custom(tool_id, tool, document, project=project)
    except Exception as exc:
        return exc


def _receipt(folder: Path) -> dict[str, object]:
    path = folder / "receipt.json"
    deadline = time.monotonic() + 10
    while not path.is_file() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.is_file(), "detached writer did not publish its receipt"
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def test_two_real_launches_keep_exact_argv_and_bytes(tmp_path: Path) -> None:
    code = (
        "import json, os, pathlib, sys\n"
        "pending = pathlib.Path('receipt.pending')\n"
        "with pending.open('w', encoding='utf-8') as stream:\n"
        "    json.dump({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'pid': os.getpid()}, stream)\n"
        "os.replace(pending, 'receipt.json')\n"
    )
    exe = install_program(tmp_path / "éditeur 日本" / "viewer", code)
    project = tmp_path / "project é"
    project.mkdir()
    tokens = ("{file:}", "", "{dir:}", "{project:}", "{{file}}", "--text=é 日本", "; & | > $")
    tool = CustomTool("Éditeur 日本", exe, tokens)
    launches: list[Launched] = []
    writers: list[object] = []
    for index, tool_id in enumerate(("brawlcrate", "riistudio")):
        folder = tmp_path / f"outside project é 日本 {index}"
        folder.mkdir()
        document = folder / "unknown suffix.custom"
        original = b"synthetic only\x00\xff"
        document.write_bytes(original)
        result = _open(tool, document, project, tool_id)
        assert isinstance(result, Launched), result
        launches.append(result)
        receipt = _receipt(folder)
        assert receipt["argv"] == [
            str(document.resolve()),
            "",
            str(folder.resolve()),
            str(project.resolve()),
            "{file}",
            "--text=é 日本",
            "; & | > $",
        ]
        assert Path(str(receipt["cwd"])) == folder.resolve()
        assert result == Launched(tool_id, result.pid, document.resolve(), ())
        assert result.pid > 0
        assert isinstance(receipt["pid"], int) and receipt["pid"] > 0
        writers.append(receipt["pid"])
        assert document.read_bytes() == original
        assert not (folder / "receipt.pending").exists()
    assert launches[0].pid != launches[1].pid
    assert writers[0] != writers[1]


@pytest.mark.parametrize(
    "failure",
    [
        ToolFailedToStart("editor", "denied"),
        ToolNotFound("editor"),
        EditorError("custom", Path("d"), "bad"),
    ],
)
def test_runner_errors_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    tool, document, project, _ = _case(tmp_path, monkeypatch)

    def launch(cmd: Sequence[str | Path], *, cwd: Path) -> int:
        raise failure

    monkeypatch.setattr(adapter, "launch_detached", launch)
    assert _open(tool, document, project) is failure


def _case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[CustomTool, Path, Path, list[tuple[tuple[str, ...], Path]]]:
    exe, document, project = tmp_path / "editor", tmp_path / "document.any", tmp_path / "project"
    exe.write_bytes(b"synthetic executable")
    document.write_bytes(b"original")
    project.mkdir()
    calls: list[tuple[tuple[str, ...], Path]] = []

    def launch(cmd: Sequence[str | Path], *, cwd: Path) -> int:
        assert Path(cmd[0]).is_absolute()
        calls.append((tuple(map(str, cmd)), cwd))
        return 481

    monkeypatch.setattr(adapter, "launch_detached", launch)
    return CustomTool("Custom", exe, ("{file}", "{dir}", "{project}")), document, project, calls


@pytest.mark.parametrize("target", ["document", "executable", "project"])
@pytest.mark.parametrize("kind", ["missing", "wrong-kind"])
def test_fresh_prerequisites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, kind: str
) -> None:
    tool, document, project, calls = _case(tmp_path, monkeypatch)
    assert isinstance(_open(tool, document, project), Launched)
    path = {"document": document, "executable": tool.exe, "project": project}[target]
    if target == "project":
        path.rmdir()
        if kind == "wrong-kind":
            path.write_bytes(b"not a directory")
    else:
        path.unlink()
        if kind == "wrong-kind":
            path.mkdir()
    calls.clear()
    result = _open(tool, document, project)
    expected = ToolNotFound if target == "executable" else EditorError
    assert isinstance(result, expected), result
    assert result.hint and target in str(result).lower()
    assert result.__cause__ is not None
    assert calls == []
    if kind == "wrong-kind":
        path.unlink() if target == "project" else path.rmdir()
    path.mkdir() if target == "project" else path.write_bytes(b"restored")
    assert isinstance(_open(tool, document, project), Launched)
    assert len(calls) == 1


def test_document_failure_precedes_executable_and_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool, document, project, calls = _case(tmp_path, monkeypatch)
    document.unlink()
    tool.exe.unlink()
    project.rmdir()
    result = _open(tool, document, project)
    assert isinstance(result, EditorError) and "document" in str(result).lower()
    assert calls == []


@pytest.mark.parametrize("target", ["name", "executable", "document", "project", "token"])
@pytest.mark.parametrize("bad", ["\0", "\ud800"])
def test_unsafe_text_never_dispatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, bad: str
) -> None:
    tool, document, project, calls = _case(tmp_path, monkeypatch)
    name, exe, tokens = tool.name, tool.exe, tool.args_template
    if target == "name":
        name += bad
    elif target == "executable":
        exe = Path(str(exe) + bad)
    elif target == "document":
        document = Path(str(document) + bad)
    elif target == "project":
        project = Path(str(project) + bad)
    else:
        tokens = ("{file}", "literal" + bad)
    result = _open(CustomTool(name, exe, tokens), document, project)
    expected = ToolNotFound if target == "executable" else EditorError
    assert isinstance(result, expected), result
    assert result.hint and result.__cause__ is not None
    assert calls == []


@pytest.mark.parametrize("system", ["linux", "windows"])
@pytest.mark.parametrize("suffix", [".exe", ".EXE", ""])
def test_native_platform_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str, suffix: str
) -> None:
    tool, document, project, calls = _case(tmp_path, monkeypatch)
    exe = tool.exe.with_name("viewer" + suffix)
    tool.exe.rename(exe)
    tool = CustomTool(tool.name, exe, tool.args_template)
    monkeypatch.setattr(adapter, "current_os", lambda: system, raising=False)
    result = _open(tool, document, project)
    if system == "linux" and suffix:
        assert isinstance(result, ToolNotFound), result
        assert "Wine" in str(result) and "native" in str(result)
        assert calls == []
    else:
        assert result == Launched("custom", 481, document.resolve(), ())
        assert len(calls) == 1


@pytest.mark.parametrize(
    "literal",
    [
        "; touch injected",
        "&& echo injected",
        "| cat",
        ">out",
        "$(echo injected)",
        "`echo injected`",
        "%PATH%",
        "",
        '"quoted space"',
        "{{dir}}",
        "{{project}}",
        "{{{{file}}}}",
    ],
)
def test_tokens_are_inert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, literal: str) -> None:
    tool, document, project, calls = _case(tmp_path, monkeypatch)
    tool = CustomTool(tool.name, tool.exe, ("{file}", literal))
    result = _open(tool, document, project)
    assert isinstance(result, Launched), result
    assert calls == [
        (
            (
                str(tool.exe.resolve()),
                str(document.resolve()),
                literal.replace("{{", "{").replace("}}", "}"),
            ),
            document.parent.resolve(),
        )
    ]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["document.any", "editor", "project"]


@pytest.mark.parametrize("role", ["document", "executable", "project"])
@pytest.mark.parametrize("method", ["resolve", "stat"])
@pytest.mark.parametrize(
    "failure", [PermissionError("denied"), ValueError("bad path"), RuntimeError("resolution loop")]
)
def test_inspection_failure_is_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, method: str, failure: Exception
) -> None:
    tool, document, project, calls = _case(tmp_path, monkeypatch)
    target = {"document": document, "executable": tool.exe, "project": project}[role]
    original_resolve, original_stat = Path.resolve, Path.stat

    def resolve(path: Path, strict: bool = False) -> Path:
        if path == target:
            raise failure
        return original_resolve(path, strict=strict)

    def stat_path(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if path == target:
            raise failure
        return original_stat(path, follow_symlinks=follow_symlinks)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, method, resolve if method == "resolve" else stat_path)
        result = _open(tool, document, project)
    expected = ToolNotFound if role == "executable" else EditorError
    assert isinstance(result, expected), result
    assert result.__cause__ is failure and result.hint
    assert role in str(result).lower()
    assert calls == []


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit(), GeneratorExit()])
def test_inspection_interrupts_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    tool, document, project, calls = _case(tmp_path, monkeypatch)

    def resolve(path: Path, strict: bool = False) -> Path:
        raise failure

    outcome: object = None
    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "resolve", resolve)
        try:
            outcome = _open(tool, document, project)
        except BaseException as exc:
            outcome = exc
    assert outcome is failure
    assert calls == []


def test_relative_paths_are_resolved_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = CustomTool("Custom", Path("editor"), ("{file:}", "{dir:}", "{project:}"))
    for name in ("first é", "second 日本"):
        folder = tmp_path / name
        folder.mkdir()
        _, document, project, calls = _case(folder, monkeypatch)
        (project / "ctstudio.toml").write_bytes(b"not a manifest")
        monkeypatch.chdir(folder)
        result = _open(tool, Path("project/../document.any"), Path("project"))
        assert result == Launched("custom", 481, document.resolve(), ())
        assert calls == [
            (
                (
                    str(folder / "editor"),
                    str(document.resolve()),
                    str(folder),
                    str(project.resolve()),
                ),
                folder,
            )
        ]
        assert document.read_bytes() == b"original"


def test_executable_failure_precedes_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool, document, project, calls = _case(tmp_path, monkeypatch)
    tool.exe.unlink()
    project.rmdir()
    result = _open(tool, document, project)
    assert isinstance(result, ToolNotFound), result
    assert calls == []
