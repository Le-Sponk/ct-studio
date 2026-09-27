"""Tests for bootstrap_tools' Windows paths: .exe resolution and NSIS expansion (P0-T13).

Split from test_bootstrap_tools.py for the 400-line budget. Platform-neutral: the Windows
branch is selected by monkeypatching platform.system, and 7-Zip is a stand-in.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bootstrap_tools as bt

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Temp dir on the repo volume (same override as test_bootstrap_tools.py)."""
    base = REPO_ROOT / ".ctstudio" / "pytest-tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_executable_path_reports_a_missing_binary(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(bt.BootstrapError, match="not found"):
        bt.executable_path(tmp_path / "empty", "wszst")


@pytest.mark.parametrize(
    ("system", "files", "expected"),
    [
        ("Linux", ["bin/wszst"], "bin/wszst"),
        ("Linux", ["wszst", "bin/wszst"], "wszst"),
        ("Windows", ["bin/wszst", "bin/wszst.exe"], "bin/wszst.exe"),
        ("Windows", ["7z.exe"], "7z.exe"),
        ("Windows", ["bin/blender.x.exe"], "bin/blender.x.exe"),
    ],
)
def test_executable_path_prefers_exe_on_windows_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    files: list[str],
    expected: str,
) -> None:
    """The Windows branch appends .exe; with_suffix() would have mangled 'blender.x'."""
    monkeypatch.setattr(bt.platform, "system", lambda: system)
    for name in files:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"")
    stem = Path(expected).name.removesuffix(".exe")
    assert bt.executable_path(tmp_path, stem) == tmp_path / expected


# --- NSIS installers (Windows ABMatt) ---------------------------------------------


def _fake_seven_zip(monkeypatch: pytest.MonkeyPatch, payload: dict[str, str]) -> list[list[str]]:
    """Replace run_checked with a stand-in 7z that writes payload into its -o dir."""
    calls: list[list[str]] = []

    def fake(argv: list[str], what: str, timeout: float = 0) -> str:
        calls.append(argv)
        out = Path(next(a for a in argv if a.startswith("-o"))[2:])
        for name, text in payload.items():
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            (out / name).write_text(text, encoding="utf-8")
        return "Everything is Ok"

    monkeypatch.setattr(bt, "run_checked", fake)
    return calls


def test_expand_nsis_replaces_the_dir_with_the_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool_dir = tmp_path / "abmatt"
    tool_dir.mkdir()
    (tool_dir / "install.exe").write_bytes(b"MZ")
    calls = _fake_seven_zip(
        monkeypatch,
        {
            "bin/abmatt.exe": "exe",
            "etc/abmatt/presets.txt": "p",
            "$PLUGINSDIR/EnVar.dll": "nsis runtime",
            "uninstall.exe": "nsis uninstaller",
        },
    )
    bt.expand_nsis(tmp_path / "7z.exe", tool_dir, "install.exe")

    assert calls[0][:3] == [str(tmp_path / "7z.exe"), "x", "-y"]
    assert calls[0][-1] == str(tool_dir / "install.exe"), "the installer is read, not run"
    assert (tool_dir / "bin" / "abmatt.exe").is_file()
    assert (tool_dir / "etc" / "abmatt" / "presets.txt").is_file()
    assert not (tool_dir / "install.exe").exists()
    assert not (tool_dir / "$PLUGINSDIR").exists(), "NSIS runtime plugins are not the tool"
    assert not (tool_dir / "uninstall.exe").exists()


def test_expand_nsis_names_a_missing_installer(tmp_path: Path) -> None:
    (tmp_path / "abmatt").mkdir()
    with pytest.raises(bt.BootstrapError, match=r"install\.exe"):
        bt.expand_nsis(tmp_path / "7z.exe", tmp_path / "abmatt", "install.exe")
