"""P2-T06d: ``rszst_wine.install_wine`` — the official Windows ``rszst.exe`` run through Wine.

Measured in P2-T06c (Mint 22.3, wine-9.0): 48/49 recorded Windows cases equal under Wine. The
route makes its own quiet win64 prefix, downloads the pinned release with the banner read
through Wine, and writes ``setup.json`` (route ``wine``) last. Wine itself is a recording
stand-in that enforces the runner's absolute-program rule, so these run on any OS.
"""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from ctstudio.core.errors import ToolTimedOut
from ctstudio.core.tools import rszst_install
from ctstudio.core.tools.process import RunResult
from ctstudio.core.tools.rszst_install import SetupFailed
from ctstudio.core.tools.rszst_setup import (
    PIN,
    SetupRecord,
    read_record,
    wine_environment,
    wine_executable,
    wine_root,
)
from ctstudio.core.tools.rszst_wine import install_wine

pytestmark = pytest.mark.timeout(60)
BANNER = "rszst_arg_parser 0.1.6\n\nRiiStudio CLI Alpha 5.11.5 (Built May 22 2025, Clang 19.1.5)"
QUIET = {"WINEDEBUG": "-all", "WINEDLLOVERRIDES": "mscoree,mshtml="}


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


GOOD = _zip({"rszst.exe": b"MZ cli", "RiiStudio.exe": b"MZ gui"})


@pytest.fixture(autouse=True)
def pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = replace(
        PIN, windows_zip_sha256=hashlib.sha256(GOOD).hexdigest(), windows_zip_bytes=len(GOOD)
    )
    monkeypatch.setattr(rszst_install, "PIN", fake)


def _opener(url: str) -> io.BytesIO:
    assert url == PIN.windows_zip_url
    return io.BytesIO(GOOD)


class Wine:
    """Stands in for ``process.run`` running Wine: makes the prefix, answers the banner."""

    def __init__(self, arch: str | None = "win64", banner: str = BANNER) -> None:
        self.calls: list[dict[str, Any]] = []
        self.arch, self.banner = arch, banner

    def __call__(self, cmd: Sequence[str | Path], **kwargs: Any) -> RunResult:
        if not Path(str(cmd[0])).is_absolute():
            raise ValueError("cmd[0] must be an absolute executable path from tool discovery")
        argv = [str(part) for part in cmd]
        self.calls.append({"argv": argv, **kwargs})
        env = kwargs["env"]
        if argv[1:] == ["wineboot", "-u"] and self.arch is not None:
            prefix = Path(env["WINEPREFIX"])
            prefix.mkdir(parents=True, exist_ok=True)
            header = f"WINE REGISTRY Version 2\n\n#arch={self.arch}\n\n[Software]\n"
            (prefix / "system.reg").write_text(header, encoding="utf-8")
        if argv[-1] == "--version":
            return RunResult(255, 0.2, self.banner, "", None)
        return RunResult(0, 0.1, "", "", None)


def _wine(tmp_path: Path) -> Path:
    wine = tmp_path / "usr" / "bin" / "wine"
    wine.parent.mkdir(parents=True, exist_ok=True)
    wine.write_text("#!/bin/sh\n", encoding="utf-8")
    (wine.parent / "wineserver").write_text("#!/bin/sh\n", encoding="utf-8")
    return wine


def _no_which(_name: str, mode: int = 0, path: str | None = None) -> str | None:
    return None


def _install(tmp_path: Path, wine: Wine, **kwargs: Any) -> Path:
    root = wine_root(tmp_path / "données é")
    defaults: dict[str, Any] = {"runner": wine, "opener": _opener, "which": _no_which}
    return install_wine(root, wine=_wine(tmp_path), **{**defaults, **kwargs})


def test_the_layout_is_its_own_folder_beside_the_native_one(tmp_path: Path) -> None:
    root = wine_root(tmp_path)
    assert root == tmp_path / "tools" / "riistudio-5.11.5-wine"
    assert wine_executable(root) == root / "rszst" / "rszst.exe"
    assert wine_environment(root) == {**QUIET, "WINEPREFIX": str(root / "prefix")}


def test_install_makes_the_prefix_downloads_checks_through_wine_and_records(
    tmp_path: Path,
) -> None:
    runner = Wine()
    exe = _install(tmp_path, runner)
    root = wine_root(tmp_path / "données é")
    wine = str(_wine(tmp_path))
    assert exe == root / "rszst" / "rszst.exe" and exe.read_bytes() == b"MZ cli"
    assert read_record(root) == SetupRecord("wine", "5.11.5", "rszst/rszst.exe")
    boot, server, banner = runner.calls
    prefix_env = {**wine_environment(root), "WINEARCH": "win64"}
    assert boot["argv"] == [wine, "wineboot", "-u"] and boot["env"] == prefix_env
    assert server["argv"] == [str(Path(wine).parent / "wineserver"), "-w"]
    assert server["env"] == prefix_env
    assert banner["argv"][0] == wine and banner["argv"][-1] == "--version"
    assert Path(banner["argv"][1]).name == "rszst.exe" and banner["argv"][1] != str(exe)
    assert banner["env"] == wine_environment(root)
    assert boot["cwd"] == root and server["cwd"] == root
    assert Path(banner["cwd"]) == Path(banner["argv"][1]).parent
    for call in runner.calls:
        assert call["check"] is False and call["timeout"] > 0


def test_wineserver_is_taken_from_path_when_it_is_there(tmp_path: Path) -> None:
    runner = Wine()
    elsewhere = str(Path(os.path.abspath("/opt/wine/bin/wineserver")))

    def which(name: str, mode: int = 0, path: str | None = None) -> str | None:
        return elsewhere if name == "wineserver" else None

    _install(tmp_path, runner, which=which)
    assert runner.calls[1]["argv"] == [elsewhere, "-w"]


def test_a_record_lost_after_a_finished_install_is_rewritten_without_rework(tmp_path: Path) -> None:
    first = Wine()
    _install(tmp_path, first)
    root = wine_root(tmp_path / "données é")
    (root / "setup.json").unlink()
    again = Wine()
    _install(tmp_path, again, opener=None)  # the checked download is kept too
    assert again.calls == []
    assert read_record(root) == SetupRecord("wine", "5.11.5", "rszst/rszst.exe")


def test_a_finished_setup_runs_nothing(tmp_path: Path) -> None:
    _install(tmp_path, Wine())
    again = Wine()
    assert _install(tmp_path, again, opener=None) == wine_executable(
        wine_root(tmp_path / "données é")
    )
    assert again.calls == []


def _refused(tmp_path: Path, runner: Wine, *words: str, **kwargs: Any) -> None:
    with pytest.raises(SetupFailed) as caught:
        _install(tmp_path, runner, **kwargs)
    assert read_record(wine_root(tmp_path / "données é")) is None
    text = str(caught.value)
    for word in words:
        assert word in text


def test_a_prefix_wine_could_not_make_is_a_setup_failure(tmp_path: Path) -> None:
    _refused(tmp_path, Wine(arch=None), "Wine could not prepare", "wine --version")


def test_a_32_bit_prefix_is_refused_because_rszst_is_64_bit(tmp_path: Path) -> None:
    _refused(tmp_path, Wine(arch="win32"), "32-bit", "64-bit")


def test_a_wrong_banner_under_wine_installs_nothing(tmp_path: Path) -> None:
    _refused(tmp_path, Wine(banner="wine: could not load kernel32.dll"), "not RiiStudio 5.11.5")
    assert not wine_executable(wine_root(tmp_path / "données é")).exists()


def test_wine_that_hangs_while_making_the_prefix_is_a_setup_failure(tmp_path: Path) -> None:
    class Hangs(Wine):
        def __call__(self, cmd: Sequence[str | Path], **kwargs: Any) -> RunResult:
            raise ToolTimedOut([str(cmd[0])], 600, None)

    _refused(tmp_path, Hangs(), "Wine could not prepare")


def test_without_wine_nothing_is_attempted(tmp_path: Path) -> None:
    runner = Wine()
    root = wine_root(tmp_path / "d")
    with pytest.raises(SetupFailed) as caught:
        install_wine(root, wine=tmp_path / "no-wine", runner=runner, opener=_opener)
    assert "sudo apt install -y wine" in str(caught.value)
    assert runner.calls == [] and not root.exists()


def test_the_download_reports_progress(tmp_path: Path) -> None:
    seen: list[tuple[int, int]] = []
    _install(tmp_path, Wine(), on_progress=lambda done, total: seen.append((done, total)))
    assert seen[-1] == (len(GOOD), len(GOOD))


def test_wine_that_hangs_on_the_banner_installs_nothing(tmp_path: Path) -> None:
    class BannerHangs(Wine):
        def __call__(self, cmd: Sequence[str | Path], **kwargs: Any) -> RunResult:
            if str(cmd[-1]) == "--version":
                raise ToolTimedOut([str(cmd[0])], 30, None)
            return super().__call__(cmd, **kwargs)

    _refused(tmp_path, BannerHangs(), "not RiiStudio 5.11.5")
