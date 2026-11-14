"""P5-T07b2: bounded SZS dispatch, never a loaded-document receipt."""

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from types import MappingProxyType
from typing import Literal

import pytest
from editor_test_helpers import document as make_document
from fakes.install import install_program

from ctstudio.cli import open_file
from ctstudio.core.errors import ToolNotFound
from ctstudio.core.tools import editors, wine
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.editors import EditorError, Launched
from ctstudio.core.tools.spec import ToolSpec

pytestmark = pytest.mark.timeout(30)
TOOLS = ("brawlcrate", "riistudio")
RII_WARNING = (
    "RiiStudio cannot open paths with non-ASCII characters on Windows: it will start "
    "with an empty editor. Move or rename the file to an ASCII-only path."
)


def _outcome[T](action: Callable[[], T]) -> T | Exception:
    try:
        return action()
    except Exception as exc:
        return exc


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("os_name", ["windows", "linux"])
@pytest.mark.parametrize("configured", [False, True])
def test_szs_routes_preserve_path_first_options_after(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    os_name: Literal["windows", "linux"],
    configured: bool,
) -> None:
    document = make_document(tmp_path, "track.SzS", "track é 日本")
    exe = tmp_path / "editor.exe"
    exe.write_bytes(b"synthetic executable: spies only")
    calls: list[object] = []
    prefix = tmp_path / "prefix é"
    wine_exe = tmp_path / "wine"
    tail = ("/audio:none",) if tool == "brawlcrate" else ()

    def discover(spec: ToolSpec, **kwargs: object) -> ToolLocation:
        calls.append(spec.id)
        return ToolLocation(
            wine_exe if spec.id == "wine" else exe,
            None,
            "standard",
            "wine" if spec.id != "wine" and os_name == "linux" else "direct",
        )

    def native(cmd: list[object], *, cwd: Path) -> int:
        calls.append((cmd, cwd))
        return 123

    def through_wine(
        executable: Path, path: Path, options: tuple[str, ...], *, wine: Path, prefix: Path
    ) -> int:
        calls.append((executable, path, options, wine, prefix))
        return 456

    monkeypatch.setattr(editors, "current_os", lambda: os_name)
    monkeypatch.setattr(editors, "discover", discover)
    monkeypatch.setattr(editors, "launch_detached", native)
    monkeypatch.setattr(wine, "launch", through_wine)
    result = _outcome(
        lambda: editors.open_in(
            tool, document, executable=exe if configured else None, wine_prefix=prefix
        )
    )
    assert isinstance(result, Launched), "SZS must reach the existing dispatch API"
    expected: list[object] = [] if configured else [tool]
    if os_name == "linux":
        expected += ["wine", (exe.resolve(), document.resolve(), tail, wine_exe, prefix)]
    else:
        expected += [([exe.resolve(), document.resolve(), *tail], document.parent.resolve())]
    assert calls == expected
    assert result.tool_id == tool and result.document == document.resolve()
    assert result.pid == (456 if os_name == "linux" else 123)
    expected_warnings = (RII_WARNING,) if tool == "riistudio" and os_name == "windows" else ()
    assert result.warnings == expected_warnings
    assert [field.name for field in fields(result)] == ["tool_id", "pid", "document", "warnings"]
    assert document.read_bytes() == b"document"


def test_szs_table_is_bounded_immutable_and_keeps_existing_order() -> None:
    assert isinstance(editors.EDITOR_DOCUMENTS, MappingProxyType)
    assert list(editors.EDITOR_DOCUMENTS.items()) == [
        ("brawlcrate", (".brres", ".szs")),
        ("riistudio", (".brres", ".szs")),
        ("kmp_editor_lorenzi", (".kmp",)),
        ("kmp_cloud", (".kmp",)),
        ("blender", (".blend",)),
    ]


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("fault", ["document", "directory", "configured", "discovered", "prefix"])
def test_szs_refusals_do_not_dispatch_or_change_user_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    fault: str,
) -> None:
    document = make_document(tmp_path, "course.szs")
    original = document.read_bytes()
    exe = tmp_path / "editor.exe"
    exe.write_bytes(b"synthetic executable")
    calls: list[str] = []

    def discover(spec: ToolSpec, **kwargs: object) -> ToolLocation | None:
        calls.append(spec.id)
        return None if fault == "discovered" else ToolLocation(exe, None, "standard", "wine")

    def dispatch(*args: object, **kwargs: object) -> int:
        calls.append("dispatch")
        return 999

    monkeypatch.setattr(editors, "current_os", lambda: "linux")
    monkeypatch.setattr(editors, "discover", discover)
    monkeypatch.setattr(editors, "launch_detached", dispatch)
    monkeypatch.setattr(wine, "launch", dispatch)
    target = document
    if fault == "document":
        target = document.with_name("missing.szs")
    elif fault == "directory":
        target = document.with_name("directory.szs")
        target.mkdir()
    configured = exe.with_name("missing.exe") if fault == "configured" else None
    result = _outcome(lambda: editors.open_in(tool, target, executable=configured))
    expected = (
        EditorError
        if fault in ("document", "directory")
        else (wine.WineError if fault == "prefix" else ToolNotFound)
    )
    assert isinstance(result, expected), "SZS refusal must retain the intended typed boundary"
    assert result.hint
    assert "dispatch" not in calls
    assert calls == ([tool] if fault in ("discovered", "prefix") else [])
    assert document.is_file() and document.read_bytes() == original
    assert exe.read_bytes() == b"synthetic executable"
    if fault == "prefix":
        assert "Wine prefix" in str(result) and "wineboot" in result.hint


@pytest.mark.parametrize("tool", TOOLS)
def test_szs_two_requests_have_distinct_real_launches_and_atomic_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
) -> None:
    documents = [
        make_document(tmp_path, "one.SZS", "first é 日本"),
        make_document(tmp_path, "two.szs", "second é 日本"),
    ]
    exe = install_program(
        tmp_path / "fake editor é" / tool,
        "import json, os, sys\nfrom pathlib import Path\n"
        "target = Path.cwd() / 'receipt.json'\n"
        "pending = target.with_suffix('.pending')\n"
        "pending.write_text(json.dumps({'argv': sys.argv[1:], 'cwd': str(Path.cwd()), "
        "'pid': os.getpid()}), encoding='utf-8')\n"
        "pending.replace(target)\n",
    )
    monkeypatch.setattr(editors, "current_os", lambda: "windows")

    def request(document: Path) -> Launched | Exception:
        return _outcome(lambda: editors.open_in(tool, document, executable=exe))

    results = [request(document) for document in documents]
    assert all(isinstance(r, Launched) for r in results), results
    assert len({r.pid for r in results if isinstance(r, Launched)}) == 2
    receipts = [p.parent / "receipt.json" for p in documents]
    deadline = time.monotonic() + 8
    while not all(p.is_file() for p in receipts) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert all(p.is_file() for p in receipts), "each real child must publish its own receipt"
    rows: list[dict[str, object]] = [json.loads(p.read_text(encoding="utf-8")) for p in receipts]
    assert len({row["pid"] for row in rows}) == 2
    for document, result, row in zip(documents, results, rows, strict=True):
        assert isinstance(result, Launched) and result.pid > 0
        assert result.tool_id == tool and result.document == document.resolve()
        assert bool(result.warnings) == (tool == "riistudio")
        assert row["argv"] == [
            str(document.resolve()),
            *(["/audio:none"] if tool == "brawlcrate" else []),
        ]
        assert row["cwd"] == str(document.parent.resolve())
        assert document.is_file() and document.read_bytes() == b"document"


@pytest.mark.parametrize(
    "available, chosen", [(TOOLS, "brawlcrate"), (("riistudio",), "riistudio")]
)
def test_szs_cli_automatic_selection_preserves_launch_only_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    available: tuple[str, ...],
    chosen: str,
) -> None:
    document = make_document(tmp_path, "course.SZS", "CLI é 日本")
    exe = tmp_path / "editor"
    exe.write_bytes(b"synthetic executable")
    calls: list[object] = []

    def native(cmd: list[object], *, cwd: Path) -> int:
        calls.append((cmd, cwd))
        return 789

    monkeypatch.setattr(open_file, "configured_tools", lambda: {chosen: exe})

    def available_tools(**kwargs: object) -> frozenset[str]:
        return frozenset(available)

    monkeypatch.setattr(open_file, "available_tools", available_tools)
    monkeypatch.setattr(editors, "current_os", lambda: "windows")
    monkeypatch.setattr(editors, "launch_detached", native)
    parser = argparse.ArgumentParser()
    open_file.add_parser(parser.add_subparsers(dest="command"))
    assert _outcome(lambda: open_file.run(parser.parse_args(["open", str(document)]))) == 0
    tail = ["/audio:none"] if chosen == "brawlcrate" else []
    expected_cmd = [exe.resolve(), document.resolve(), *tail]
    assert calls == [(expected_cmd, document.parent.resolve())]
    captured = capsys.readouterr()
    name = "BrawlCrate" if chosen == "brawlcrate" else "RiiStudio"
    assert (
        captured.out
        == f"Started {name} for course.SZS (process 789).\n"
        + "CT Studio cannot tell whether the editor loaded the file; check its window.\n"
    )
    assert bool(captured.err) == (chosen == "riistudio")
    assert document.read_bytes() == b"document"


def test_open_help_names_szs_without_claiming_loaded_documents(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = argparse.ArgumentParser()
    open_file.add_parser(parser.add_subparsers(dest="command"))
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["open", "--help"])
    assert exc.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "a .brres or .szs in BrawlCrate or RiiStudio" in text
    assert "Start an installed editor" in text and "successfully" not in text
