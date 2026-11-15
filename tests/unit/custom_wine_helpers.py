"""Synthetic custom-Wine fixtures and contract-enforcing process observations."""

from __future__ import annotations

import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from ctstudio.core.tools import custom_editors, wine
from ctstudio.core.tools.process import RunResult
from ctstudio.core.tools.spec import CustomTool


def outcome[T](call: Callable[[], T]) -> T | BaseException:
    try:
        return call()
    except BaseException as error:
        return error


def pe(path: Path, arch: str = "win32") -> Path:
    data = bytearray(256)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, 0x14C if arch == "win32" else 0x8664)
    struct.pack_into("<H", data, 0x98, 0x10B if arch == "win32" else 0x20B)
    path.write_bytes(data)
    return path


def converted(path: Path) -> str:
    return "Z:\\synthetic\\" + path.as_posix().replace("/", "\\")


@dataclass
class Request:
    root: Path
    exe: Path
    document: Path
    project: Path
    launcher: Path
    prefix: Path
    conversions: list[Path] = field(default_factory=list[Path])
    launches: list[tuple[list[str], dict[str, object]]] = field(
        default_factory=list[tuple[list[str], dict[str, object]]]
    )

    def tool(self, tokens: Sequence[str] = ("{file}",)) -> CustomTool:
        return CustomTool("Custom 日本", self.exe, tokens)

    def open(self, tool: CustomTool | None = None) -> object:
        return custom_editors.open_custom(
            "brawlcrate",
            tool or self.tool(),
            self.document,
            project=self.project,
            wine_executable=self.launcher,
            wine_prefix=self.prefix,
        )

    def convert(self, cmd: Sequence[str | Path], **kwargs: object) -> RunResult:
        assert list(map(str, cmd[:3])) == [str(self.launcher.resolve()), "winepath.exe", "-w"]
        target = Path(cmd[3])
        assert target.is_absolute()
        assert kwargs == {
            "cwd": target.parent,
            "env": {"WINEPREFIX": str(self.prefix.resolve())},
            "timeout": wine.WINEPATH_TIMEOUT,
        }
        self.conversions.append(target)
        return RunResult(0, 0.0, converted(target) + "\n", "", None)

    def launch(self, cmd: Sequence[str | Path], **kwargs: object) -> int:
        assert Path(cmd[0]).is_absolute()
        self.launches.append((list(map(str, cmd)), kwargs))
        return 917


def request(
    root: Path, monkeypatch: pytest.MonkeyPatch, arch: str = "win32", prefix_arch: str = "win64"
) -> Request:
    root.mkdir(parents=True, exist_ok=True)
    document = root / "document é 日本.brres"
    document.write_bytes(b"synthetic document unchanged")
    project = root / "project é 日本"
    project.mkdir()
    launcher = root / "wine"
    launcher.write_bytes(b"synthetic Wine; spies only")
    prefix = root / "prefix é"
    prefix.mkdir()
    (prefix / "system.reg").write_text(f"#arch={prefix_arch}\n", encoding="utf-8")
    result = Request(root, pe(root / "editor.ExE", arch), document, project, launcher, prefix)
    monkeypatch.setattr(custom_editors, "current_os", lambda: "linux")
    monkeypatch.setattr(wine, "run", result.convert)
    monkeypatch.setattr(wine, "launch_detached", result.launch)
    monkeypatch.setattr(custom_editors, "launch_detached", result.launch)
    return result
