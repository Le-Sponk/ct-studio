"""P2-T05g2: ``launch_detached(..., watch=s)`` reports a launch that dies straight away.

Measured on Linux Mint 22.3 / Wine 9.0 (spikes/p2t05g2_wine_probe.py): a wrong-architecture
prefix (``Bad EXE format``) and a .NET program without .NET (``Wine Mono is not installed``)
made ``wine`` exit within 0.5 s with the reason on its output, while every good launch was
still running 25 s later. Fakes here are this interpreter (portable-spawning rule).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from process_fakes import fake

from ctstudio.core.errors import ToolFailed
from ctstudio.core.tools.process import TAIL_LINES, launch_detached

pytestmark = pytest.mark.timeout(20)


def _wait_for(path: Path, seconds: float = 8.0) -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8"):
            return path.read_text(encoding="utf-8")
        time.sleep(0.05)
    raise AssertionError(f"{path.name} never appeared")


def test_a_launch_still_running_after_the_watch_returns_its_pid(tmp_path: Path) -> None:
    code = 'time.sleep(1.2); pathlib.Path("opened.txt").write_text("yes", encoding="utf-8")'
    started = time.monotonic()
    pid = launch_detached(fake(code), cwd=tmp_path, watch=0.4)
    waited = time.monotonic() - started
    assert pid > 0
    assert 0.4 <= waited < 1.1  # waited for the watch, not for the editor
    assert not (tmp_path / "opened.txt").exists()
    assert _wait_for(tmp_path / "opened.txt") == "yes"  # and it kept running afterwards


def test_an_early_failure_raises_with_its_output(tmp_path: Path) -> None:
    code = (
        'out("starting é 日本"); '
        'err("ShellExecuteEx failed: Bad EXE format for x.exe."); sys.exit(1)'
    )
    started = time.monotonic()
    with pytest.raises(ToolFailed) as caught:
        launch_detached(fake(code), cwd=tmp_path, watch=5.0)
    assert time.monotonic() - started < 3.0  # reported as soon as it exits
    assert caught.value.exit_code == 1
    assert "Bad EXE format for x.exe." in caught.value.stderr_tail
    assert "starting é 日本" in caught.value.stderr_tail  # one combined stream
    assert caught.value.log_path is None


def test_exit_255_is_a_failure_too(tmp_path: Path) -> None:
    with pytest.raises(ToolFailed) as caught:
        launch_detached(
            fake('err("Wine Mono is not installed"); sys.exit(255)'), cwd=tmp_path, watch=5.0
        )
    assert caught.value.exit_code == 255
    assert "Wine Mono is not installed" in caught.value.stderr_tail


def test_an_early_clean_exit_is_a_handed_off_launch(tmp_path: Path) -> None:
    started = time.monotonic()
    pid = launch_detached(fake('out("handed over"); sys.exit(0)'), cwd=tmp_path, watch=5.0)
    assert pid > 0
    assert time.monotonic() - started < 3.0


def test_the_failure_output_is_bounded_to_the_last_lines(tmp_path: Path) -> None:
    code = 'for i in range(400): out(f"line {i}")\nsys.exit(3)'
    with pytest.raises(ToolFailed) as caught:
        launch_detached(fake(code), cwd=tmp_path, watch=5.0)
    lines = caught.value.stderr_tail.splitlines()
    assert len(lines) == TAIL_LINES
    assert lines[-1] == "line 399"


def test_output_after_the_watch_does_not_disturb_the_editor(tmp_path: Path) -> None:
    code = (
        'time.sleep(0.6)\nfor i in range(2000): out("x" * 200)\n'
        'pathlib.Path("done.txt").write_text("done", encoding="utf-8")'
    )
    launch_detached(fake(code), cwd=tmp_path, watch=0.2)
    assert _wait_for(tmp_path / "done.txt") == "done"


def test_watch_must_not_be_negative(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="watch"):
        launch_detached(fake("pass"), cwd=tmp_path, watch=-1.0)
