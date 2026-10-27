"""P2-T03: streaming, decoding, logging and failure reporting of the process runner."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from process_fakes import fake

from ctstudio.core.errors import ProjectError, ToolFailed, ToolNotFound
from ctstudio.core.tools.process import TAIL_LINES, Stream, run

pytestmark = pytest.mark.timeout(10)


def test_lines_stream_live_in_order_across_both_pipes(tmp_path: Path) -> None:
    # Each line waits for the callback's acknowledgement, so buffering until exit would hang.
    code = """
base = pathlib.Path(sys.argv[1])
out("out-1"); wait_for(str(base / "ack1"))
err("err-1"); wait_for(str(base / "ack2"))
out("out-2"); wait_for(str(base / "ack3"))
err("err-2")
"""
    seen: list[tuple[Stream, str]] = []

    def on_line(stream: Stream, line: str) -> None:
        seen.append((stream, line))
        (tmp_path / f"ack{len(seen)}").touch()

    result = run(fake(code, tmp_path), cwd=tmp_path, timeout=8, on_line=on_line)
    assert seen == [
        ("stdout", "out-1"),
        ("stderr", "err-1"),
        ("stdout", "out-2"),
        ("stderr", "err-2"),
    ]
    assert result.exit_code == 0
    assert result.stdout_tail == "out-1\nout-2"
    assert result.stderr_tail == "err-1\nerr-2"
    assert result.duration > 0
    assert result.log_path is None


def test_fifty_megabytes_on_both_pipes_do_not_deadlock(tmp_path: Path) -> None:
    code = """
line = b"x" * 99 + b"\\n"
block = line * 10486
for _ in range(25):
    sys.stdout.buffer.write(block)
    sys.stderr.buffer.write(block)
out("done")
"""
    counts: dict[Stream, int] = {"stdout": 0, "stderr": 0}

    def count(stream: Stream, _line: str) -> None:
        counts[stream] += 1

    log = tmp_path / "big.log"
    started = time.monotonic()
    result = run(fake(code), cwd=tmp_path, timeout=9, on_line=count, log_path=log)
    assert time.monotonic() - started < 9
    assert counts == {"stdout": 25 * 10486 + 1, "stderr": 25 * 10486}
    assert result.stdout_tail.splitlines()[-1] == "done"
    assert len(result.stdout_tail.splitlines()) == TAIL_LINES
    assert log.stat().st_size > 50_000_000


def test_nonzero_exit_raises_tool_failed_with_a_bounded_stderr_tail(tmp_path: Path) -> None:
    code = """
for i in range(200):
    err(f"problem {i}")
out("stdout is separate")
sys.exit(7)
"""
    log = tmp_path / "tool.log"
    with pytest.raises(ToolFailed) as caught:
        run(fake(code), cwd=tmp_path, timeout=8, log_path=log)
    error = caught.value
    assert error.exit_code == 7
    assert error.log_path == log
    lines = error.stderr_tail.splitlines()
    assert len(lines) == TAIL_LINES
    assert lines[0] == f"problem {200 - TAIL_LINES}"
    assert lines[-1] == "problem 199"
    assert "stdout is separate" not in error.stderr_tail
    assert "problem" not in str(error)
    assert "# exit 7" in log.read_text(encoding="utf-8")


def test_check_false_returns_the_nonzero_result(tmp_path: Path) -> None:
    result = run(fake('out("partial"); sys.exit(3)'), cwd=tmp_path, timeout=8, check=False)
    assert result.exit_code == 3
    assert result.stdout_tail == "partial"


def test_unicode_paths_args_environment_and_undecodable_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "dir é 日本 space"
    folder.mkdir()
    monkeypatch.setenv("CTSTUDIO_INHERITED", "kept")
    code = """
out(os.getcwd())
out(sys.argv[1])
out(os.environ["CTSTUDIO_INHERITED"])
out(os.environ["CTSTUDIO_ADDED"])
sys.stdout.buffer.write(b"bad \\xff end\\n")
sys.stdout.buffer.write(b"crlf\\r\\n")
sys.stdout.buffer.write(b"caf\\xc3"); sys.stdout.buffer.flush(); time.sleep(0.2)
sys.stdout.buffer.write(b"\\xa9 split"); sys.stdout.buffer.flush()
"""
    lines: list[str] = []
    run(
        fake(code, "名前 é.txt"),
        cwd=folder,
        env={"CTSTUDIO_ADDED": "añadido 日本"},
        timeout=8,
        on_line=lambda _stream, line: lines.append(line),
    )
    assert os.path.samefile(lines[0], folder)
    assert lines[1:] == [
        "名前 é.txt",
        "kept",
        "añadido 日本",
        "bad \ufffd end",
        "crlf",
        "café split",
    ]


def test_log_file_appends_every_run_as_utf8(tmp_path: Path) -> None:
    log = tmp_path / "logs é" / "tool.log"
    first = run(fake('out("first é")'), cwd=tmp_path, timeout=8, log_path=log)
    run(fake('err("second 日本")'), cwd=tmp_path, timeout=8, log_path=log)
    text = log.read_text(encoding="utf-8")
    assert first.log_path == log
    assert text.index("[out] first é") < text.index("[err] second 日本")
    assert text.count("# run ") == 2
    assert text.count("# exit 0 after ") == 2


def test_missing_relative_and_misplaced_commands_are_typed(tmp_path: Path) -> None:
    with pytest.raises(ToolNotFound) as missing:
        run([tmp_path / "missing é.exe"], cwd=tmp_path, timeout=5)
    assert missing.value.tool == "missing é.exe"
    with pytest.raises(ValueError, match="absolute"):
        run(["python", "-c", "pass"], cwd=tmp_path, timeout=5)
    with pytest.raises(ProjectError):
        run(fake("pass"), cwd=tmp_path / "absent", timeout=5)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console windows only")
def test_windows_cli_tools_get_no_console_window(tmp_path: Path) -> None:
    # The test runner may itself have a windowless console, which a child would inherit and
    # report as "no window" even without CREATE_NO_WINDOW. So call run() from a hidden
    # intermediate that owns a real console window, which a flagless child would share.
    script = (
        "import ctypes, pathlib, sys\n"
        "from ctstudio.core.tools.process import run\n"
        "code = 'import ctypes; print(ctypes.windll.kernel32.GetConsoleWindow() or 0)'\n"
        "own = ctypes.windll.kernel32.GetConsoleWindow() or 0\n"
        "child = run([sys.executable, '-c', code], cwd=pathlib.Path.cwd(), timeout=8)\n"
        "pathlib.Path(sys.argv[1]).write_text(f'{own} {child.stdout_tail}')\n"
    )
    report = tmp_path / "console.txt"
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0  # SW_HIDE: never flash a window during the test
    subprocess.run(  # noqa: S603 - this interpreter, argv list
        [sys.executable, "-c", script, str(report)],
        cwd=tmp_path,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        startupinfo=startup,
        timeout=9,
        check=True,
    )
    own, child = report.read_text(encoding="utf-8").split()
    assert own != "0", "the intermediate should own a console window"
    assert child == "0"
