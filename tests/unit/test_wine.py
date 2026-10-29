"""P2-T05g2: running a Windows editor through Wine (``ctstudio.core.tools.wine``).

Contracts measured on Linux Mint 22.3, Wine 9.0 (Ubuntu), winetricks 20240105 by
spikes/p2t05g2_wine_probe.py (TOOLS.md "Wine / winetricks"):

* BrawlCrate is PE32 i386, RiiStudio and Lorenzi are PE32+ x86-64. A PE32+ program in a
  win32 prefix exits 1 in 0.5 s with ``ShellExecuteEx failed: Bad EXE format for …``.
* ``system.reg`` starts with ``#arch=win32`` or ``#arch=win64``.
* ``winepath.exe -w`` turns ``/home/…/dossier é 日本/x`` into ``Z:\\home\\…\\dossier é 日本\\x``,
  for missing files too, and round-trips; a non-ASCII prefix folder changes nothing.
* BrawlCrate without .NET exits 255 at once with ``Wine Mono is not installed``.
* Good launches were still running 25 s later; ``wine`` itself stays up (``start.exe``).
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from ctstudio.core.errors import ToolFailed, ToolNotFound
from ctstudio.core.tools import wine
from ctstudio.core.tools.process import RunResult
from ctstudio.core.tools.wine import WineError, exe_arch, launch, prefix_arch, windows_path

pytestmark = pytest.mark.timeout(30)

I386, AMD64, ARM64 = 0x14C, 0x8664, 0xAA64
PE32, PE32_PLUS = 0x10B, 0x20B


def _pe(path: Path, machine: int = AMD64, magic: int = PE32_PLUS) -> Path:
    header = bytearray(0x200)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 0x3C, 0x80)
    header[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", header, 0x84, machine)
    struct.pack_into("<H", header, 0x80 + 24, magic)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header))
    return path


def _prefix(folder: Path, arch: str | None = "win64") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["WINE REGISTRY Version 2", ";; All keys relative to \\\\Machine", ""]
    if arch is not None:
        lines.insert(2, f"#arch={arch}")
    (folder / "system.reg").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def _doc(tmp_path: Path, name: str = "pièce course.kmp") -> Path:
    path = tmp_path / "home" / "dossier é 日本" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RKMD")
    return path


def _wine(tmp_path: Path) -> Path:
    path = tmp_path / "usr" / "bin" / "wine"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"#!")
    return path


# --- executable architecture --------------------------------------------------------------


@pytest.mark.parametrize(
    ("machine", "magic", "arch"),
    [(I386, PE32, "win32"), (AMD64, PE32_PLUS, "win64")],
)
def test_executable_architecture_comes_from_the_pe_header(
    machine: int, magic: int, arch: str, tmp_path: Path
) -> None:
    assert exe_arch(_pe(tmp_path / "editor.exe", machine, magic)) == arch


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"", "not a Windows program"),
        (b"#!/bin/sh\necho hi\n", "not a Windows program"),
        (b"MZ" + b"\0" * 0x3A + struct.pack("<I", 0x80) + b"\0" * 0x40, "not a Windows program"),
    ],
)
def test_non_programs_are_refused(data: bytes, reason: str, tmp_path: Path) -> None:
    path = tmp_path / "editor.exe"
    path.write_bytes(data)
    with pytest.raises(WineError, match=reason):
        exe_arch(path)


@pytest.mark.parametrize(
    ("machine", "magic"),
    [(ARM64, PE32_PLUS), (I386, PE32_PLUS), (AMD64, PE32), (AMD64, 0x107)],
)
def test_other_or_inconsistent_architectures_are_refused(
    machine: int, magic: int, tmp_path: Path
) -> None:
    with pytest.raises(WineError, match="x86"):
        exe_arch(_pe(tmp_path / "editor.exe", machine, magic))


@pytest.mark.parametrize(("start", "end", "bad"), [(0, 2, b"ZM"), (0x80, 0x84, b"NE\0\0")])
def test_a_damaged_mz_or_pe_signature_is_refused(
    start: int, end: int, bad: bytes, tmp_path: Path
) -> None:
    path = _pe(tmp_path / "editor.exe")  # otherwise a valid x86-64 header
    data = bytearray(path.read_bytes())
    data[start:end] = bad
    path.write_bytes(bytes(data))
    with pytest.raises(WineError, match="not a Windows program"):
        exe_arch(path)


def test_a_header_offset_past_the_end_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "editor.exe"
    path.write_bytes(b"MZ" + b"\0" * 0x3A + struct.pack("<I", 0x10_0000))
    with pytest.raises(WineError, match="not a Windows program"):
        exe_arch(path)


# --- prefix architecture ------------------------------------------------------------------


@pytest.mark.parametrize("arch", ["win32", "win64"])
def test_prefix_architecture_comes_from_system_reg(arch: str, tmp_path: Path) -> None:
    assert prefix_arch(_prefix(tmp_path / "préfixe é", arch)) == arch


def test_a_folder_that_is_not_a_prefix_is_refused_with_how_to_make_one(tmp_path: Path) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()
    with pytest.raises(WineError, match="not a Wine prefix") as caught:
        prefix_arch(folder)
    assert caught.value.hint is not None and "wineboot" in caught.value.hint
    with pytest.raises(WineError, match="not a Wine prefix"):
        prefix_arch(tmp_path / "missing")


@pytest.mark.parametrize("arch", [None, "arm64"])
def test_an_unknown_prefix_architecture_is_refused(arch: str | None, tmp_path: Path) -> None:
    with pytest.raises(WineError, match="architecture"):
        prefix_arch(_prefix(tmp_path / "p", arch))


def test_only_the_header_marks_the_architecture(tmp_path: Path) -> None:
    folder = _prefix(tmp_path / "p", None)
    with (folder / "system.reg").open("a", encoding="utf-8") as reg:
        reg.write("[Software\\\\Notes] 1700000000\n#arch=win32\n")
    with pytest.raises(WineError, match="architecture"):
        prefix_arch(folder)


# --- winepath ------------------------------------------------------------------------------


def _converted(path: Path) -> str:
    return f"Z:\\converted\\{path.name}"


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_run(cmd: list[object], **kwargs: object) -> RunResult:
        calls.append({"cmd": list(cmd), **kwargs})
        return RunResult(0, 0.1, f"{_converted(Path(str(cmd[-1])))}\n", "wine: noise", None)

    monkeypatch.setattr(wine, "run", fake_run)
    return calls


def test_windows_path_asks_winepath_in_the_prefix(
    runs: list[dict[str, object]], tmp_path: Path
) -> None:
    doc, exe, prefix = _doc(tmp_path), _wine(tmp_path), _prefix(tmp_path / "pfx")
    assert windows_path(doc, wine=exe, prefix=prefix) == "Z:\\converted\\pièce course.kmp"
    [call] = runs
    assert call["cmd"] == [exe, "winepath.exe", "-w", doc]
    assert call["env"] == {"WINEPREFIX": str(prefix)}
    assert call["cwd"] == doc.parent
    assert isinstance(call["timeout"], int | float) and call["timeout"] > 0


@pytest.mark.parametrize(
    "stdout",
    ["", "\n", "/home/user/x.kmp\n", "C:\n", "relative\\x.kmp\n"],
)
def test_an_answer_that_is_not_a_windows_path_is_refused(
    stdout: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(wine, "run", lambda *_a, **_k: RunResult(0, 0.1, stdout, "", None))
    with pytest.raises(WineError, match="winepath"):
        windows_path(_doc(tmp_path), wine=_wine(tmp_path), prefix=_prefix(tmp_path / "p"))


def test_the_last_stdout_line_is_the_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = RunResult(0, 0.1, "wine: updated\nZ:\\home\\é 日本\\x.kmp  \n", "", None)
    monkeypatch.setattr(wine, "run", lambda *_a, **_k: result)
    path = windows_path(_doc(tmp_path), wine=_wine(tmp_path), prefix=_prefix(tmp_path / "p"))
    assert path == "Z:\\home\\é 日本\\x.kmp"


# --- launch --------------------------------------------------------------------------------


@pytest.fixture
def launches(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_launch(cmd: list[object], *, cwd: Path, env: object = None, watch: float = 0) -> int:
        calls.append({"cmd": list(cmd), "cwd": cwd, "env": env, "watch": watch})
        return 777

    monkeypatch.setattr(wine, "launch_detached", fake_launch)
    return calls


def test_launch_runs_the_editor_on_the_windows_path_with_options_after(
    runs: list[dict[str, object]], launches: list[dict[str, object]], tmp_path: Path
) -> None:
    exe = _pe(tmp_path / "editors" / "BrawlCrate.exe", I386, PE32)
    doc, wine_exe, prefix = (
        _doc(tmp_path, "a.brres"),
        _wine(tmp_path),
        _prefix(tmp_path / "p32", "win32"),
    )
    pid = launch(exe, doc, ("/audio:none",), wine=wine_exe, prefix=prefix)
    assert pid == 777
    assert launches == [
        {
            "cmd": [wine_exe, exe, "Z:\\converted\\a.brres", "/audio:none"],
            "cwd": doc.parent,
            "env": {"WINEPREFIX": str(prefix)},
            "watch": wine.WATCH_SECONDS,
        }
    ]
    assert 1.0 <= wine.WATCH_SECONDS <= 5.0


def test_a_64_bit_editor_is_refused_in_a_32_bit_prefix_before_starting(
    runs: list[dict[str, object]], launches: list[dict[str, object]], tmp_path: Path
) -> None:
    exe = _pe(tmp_path / "RiiStudio.exe")
    with pytest.raises(WineError, match="64-bit") as caught:
        launch(
            exe, _doc(tmp_path), (), wine=_wine(tmp_path), prefix=_prefix(tmp_path / "p", "win32")
        )
    assert caught.value.hint is not None and "WINEARCH=win64" in caught.value.hint
    assert runs == [] and launches == []


def test_a_32_bit_editor_may_use_a_64_bit_prefix(
    runs: list[dict[str, object]], launches: list[dict[str, object]], tmp_path: Path
) -> None:
    exe = _pe(tmp_path / "old.exe", I386, PE32)
    launch(exe, _doc(tmp_path), (), wine=_wine(tmp_path), prefix=_prefix(tmp_path / "p"))
    assert len(launches) == 1


def _failing(monkeypatch: pytest.MonkeyPatch, code: int, tail: str) -> None:
    def fake_launch(cmd: list[object], **_kwargs: object) -> int:
        raise ToolFailed([str(c) for c in cmd], code, tail, None)

    monkeypatch.setattr(wine, "launch_detached", fake_launch)


def test_missing_dotnet_is_explained_with_the_winetricks_fix(
    runs: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _failing(
        monkeypatch,
        255,
        "0024:err:mscoree:CLRRuntimeInfo_GetRuntimeHost Wine Mono is not installed",
    )
    prefix = _prefix(tmp_path / "p32", "win32")
    with pytest.raises(WineError, match=r"\.NET") as caught:
        launch(
            _pe(tmp_path / "BrawlCrate.exe", I386, PE32),
            _doc(tmp_path, "a.brres"),
            (),
            wine=_wine(tmp_path),
            prefix=prefix,
        )
    hint = caught.value.hint or ""
    assert "winetricks" in hint and "dotnet48" in hint and str(prefix) in hint
    assert "Wine Mono is not installed" in (caught.value.details or "")


def test_bad_exe_format_reported_by_wine_is_explained(
    runs: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _failing(monkeypatch, 1, "ShellExecuteEx failed: Bad EXE format for Z:\\x\\RiiStudio.exe.")
    with pytest.raises(WineError, match="architecture"):
        launch(
            _pe(tmp_path / "RiiStudio.exe"),
            _doc(tmp_path),
            (),
            wine=_wine(tmp_path),
            prefix=_prefix(tmp_path / "p"),
        )


def test_other_early_failures_stay_tool_failed(
    runs: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _failing(monkeypatch, 3, "err:module:import_dll Library X.dll not found")
    with pytest.raises(ToolFailed) as caught:
        launch(
            _pe(tmp_path / "RiiStudio.exe"),
            _doc(tmp_path),
            (),
            wine=_wine(tmp_path),
            prefix=_prefix(tmp_path / "p"),
        )
    assert not isinstance(caught.value, WineError)
    assert caught.value.exit_code == 3


def test_missing_wine_is_tool_not_found(tmp_path: Path) -> None:
    with pytest.raises(ToolNotFound, match="Wine"):
        launch(
            _pe(tmp_path / "RiiStudio.exe"),
            _doc(tmp_path),
            (),
            wine=tmp_path / "no-wine",
            prefix=_prefix(tmp_path / "p"),
        )
