"""Real detached runner with synthetic executables, never a desktop program."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from install import install_program

from ctstudio.core.tools import folders

pytestmark = pytest.mark.timeout(30)


def wait_until(predicate: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 10
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert predicate(), "synthetic child/reaper did not complete within ten seconds"


def tree_bytes(root: Path) -> dict[Path, bytes]:
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def child_code(receipt: Path, release: Path) -> str:
    return (
        "import json, os, sys, time\nfrom pathlib import Path\n"
        f"target = Path({str(receipt)!r})\n"
        "temp = target.with_suffix('.tmp')\n"
        "temp.write_text(json.dumps({'argv': sys.argv[1:], 'cwd': str(Path.cwd())}), "
        "encoding='utf-8')\n"
        "temp.replace(target)\n"
        f"release = Path({str(release)!r})\n"
        "deadline = time.monotonic() + 12\n"
        "while not release.exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.01)\n"
    )


@pytest.mark.parametrize("system", ["windows", "linux"])
def test_real_runner_preserves_unicode_space_argv_cwd_bytes_and_reaps_own_child(
    system: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "-folder café 日本.blend"
    folder.mkdir()
    (folder / "synthetic.txt").write_bytes(b"synthetic input\x00\xff; never a game asset")
    (folder / "nested").mkdir()
    (folder / "nested" / "notes.txt").write_text("synthetic café", encoding="utf-8")
    receipt, release = tmp_path / "receipt.json", tmp_path / "release"
    name = "explorer" if os.name == "nt" else "explorer.exe"
    executable = install_program(tmp_path / "tools café 日本" / name, child_code(receipt, release))
    monkeypatch.setattr(folders.platform, "current_os", lambda: system)
    monkeypatch.setenv("WINDIR", str(executable.parent))

    def which(_name: str) -> str:
        return str(executable)

    monkeypatch.setattr(folders.shutil, "which", which)
    before, exe_bytes = tree_bytes(folder), executable.read_bytes()
    result = folders.open_folder(folder)
    reaper = f"reap-{result.pid}"
    try:
        wait_until(receipt.is_file)
        assert json.loads(receipt.read_text(encoding="utf-8")) == {
            "argv": [str(folder.resolve())],
            "cwd": str(folder.resolve()),
        }
        assert result == folders.OpenedFolder(folder.resolve(), result.pid)
        assert result.pid > 0
        assert any(thread.name == reaper for thread in threading.enumerate())
    finally:
        release.touch()
        wait_until(lambda: all(thread.name != reaper for thread in threading.enumerate()))
    assert tree_bytes(folder) == before
    assert executable.read_bytes() == exe_bytes
