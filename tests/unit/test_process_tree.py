"""P2-T03: timeouts, cancellation and detached launches stop or spare the process tree."""

from __future__ import annotations

import ast
import os
import time
from pathlib import Path

import pytest
from process_fakes import fake

from ctstudio.core.errors import Cancelled, ToolTimedOut
from ctstudio.core.tools.process import CancelToken, Stream, launch_detached, run

pytestmark = pytest.mark.timeout(10)

SRC = Path(__file__).resolve().parents[2] / "src" / "ctstudio"

# A grandchild proves tree termination: it bumps a counter until it is killed (max 30 s).
# It explicitly inherits the tool's pipes (Windows passes std handles only when asked), so
# it also proves a descendant holding the pipes open cannot hang the runner.
SPAWN_HEARTBEAT = """
beat = pathlib.Path(sys.argv[1])
loop = "import pathlib,sys,time\\nfor i in range(600):\\n"
loop += "    pathlib.Path(sys.argv[1]).write_text(str(i)); time.sleep(0.05)"
subprocess.Popen([sys.executable, "-c", loop, str(beat)], stdout=sys.stdout, stderr=sys.stderr)
wait_for(str(beat))
out("ready")
"""


def assert_stopped(heartbeat: Path) -> None:
    assert heartbeat.exists(), "the grandchild never started"
    time.sleep(0.3)
    before = heartbeat.read_text(encoding="utf-8")
    time.sleep(0.5)
    assert heartbeat.read_text(encoding="utf-8") == before, "a grandchild is still running"


def test_timeout_kills_the_whole_tree_and_reports_the_limit(tmp_path: Path) -> None:
    beat = tmp_path / "beat é"
    started = time.monotonic()
    with pytest.raises(ToolTimedOut) as caught:
        run(fake(SPAWN_HEARTBEAT + "time.sleep(30)", beat), cwd=tmp_path, timeout=3)
    assert time.monotonic() - started < 6
    assert caught.value.timeout == 3
    assert "3 s" in caught.value.user_message
    assert_stopped(beat)


def test_cancel_mid_run_kills_the_whole_tree(tmp_path: Path) -> None:
    beat = tmp_path / "beat"
    token = CancelToken()

    def cancel_when_ready(_stream: Stream, line: str) -> None:
        if line == "ready":
            token.cancel()

    started = time.monotonic()
    with pytest.raises(Cancelled):
        run(
            fake(SPAWN_HEARTBEAT + "time.sleep(30)", beat),
            cwd=tmp_path,
            timeout=9,
            on_line=cancel_when_ready,
            cancel=token,
        )
    assert token.cancelled
    assert time.monotonic() - started < 6
    assert_stopped(beat)


def test_a_cancelled_token_never_starts_the_tool(tmp_path: Path) -> None:
    token = CancelToken()
    token.cancel()
    marker = tmp_path / "started"
    log = tmp_path / "tool.log"
    with pytest.raises(Cancelled):
        run(
            fake("pathlib.Path(sys.argv[1]).touch()", marker),
            cwd=tmp_path,
            cancel=token,
            log_path=log,
        )
    time.sleep(0.5)
    assert not marker.exists()
    assert not log.exists(), "a run header means the process was spawned"


def test_a_failing_callback_stops_the_tree_and_propagates(tmp_path: Path) -> None:
    beat = tmp_path / "beat"

    def explode(_stream: Stream, _line: str) -> None:
        raise RuntimeError("callback failed")

    log = tmp_path / "tool.log"
    with pytest.raises(RuntimeError, match="callback failed"):
        run(
            fake(SPAWN_HEARTBEAT + "time.sleep(30)", beat),
            cwd=tmp_path,
            timeout=9,
            on_line=explode,
            log_path=log,
        )
    assert_stopped(beat)
    assert "# stopped: RuntimeError" in log.read_text(encoding="utf-8")


def test_a_descendant_holding_the_pipes_cannot_outlive_the_run(tmp_path: Path) -> None:
    beat = tmp_path / "beat"
    started = time.monotonic()
    result = run(fake(SPAWN_HEARTBEAT, beat), cwd=tmp_path, timeout=9)
    assert result.exit_code == 0
    assert result.stdout_tail == "ready"
    assert time.monotonic() - started < 7
    assert_stopped(beat)


def test_a_background_helper_left_after_a_clean_exit_is_stopped(tmp_path: Path) -> None:
    # No inherited pipes, so only the session/job cleanup can find it once the tool exits.
    beat = tmp_path / "beat"
    code = SPAWN_HEARTBEAT.replace(", stdout=sys.stdout, stderr=sys.stderr", "")
    assert code != SPAWN_HEARTBEAT
    result = run(fake(code, beat), cwd=tmp_path, timeout=9)
    assert result.exit_code == 0
    assert_stopped(beat)


def test_detached_launch_returns_at_once_and_the_editor_keeps_running(tmp_path: Path) -> None:
    folder = tmp_path / "editor é 日本"
    folder.mkdir()
    code = 'time.sleep(1.0); pathlib.Path("opened.txt").write_text(os.getcwd(), encoding="utf-8")'
    started = time.monotonic()
    pid = launch_detached(fake(code), cwd=folder)
    assert time.monotonic() - started < 1.0
    assert pid > 0
    marker = folder / "opened.txt"
    for _ in range(80):
        if marker.exists() and marker.read_text(encoding="utf-8"):
            break
        time.sleep(0.1)
    assert os.path.samefile(marker.read_text(encoding="utf-8"), folder)


def _spawning_calls(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] == "subprocess"]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("subprocess"):
            found.append(node.module or "")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            name = f"{node.value.id}.{node.attr}"
            if node.value.id == "os" and node.attr.startswith(("system", "popen", "spawn", "exec")):
                found.append(name)
            if name in {"os.startfile", "os.posix_spawn", "os.posix_spawnp"}:
                found.append(name)
        elif isinstance(node, ast.keyword) and node.arg == "shell":
            found.append("shell=")
    return found


def test_only_the_process_module_may_spawn_in_src() -> None:
    allowed = SRC / "core" / "tools" / "process.py"
    offenders: dict[str, list[str]] = {}
    for path in SRC.rglob("*.py"):
        calls = _spawning_calls(ast.parse(path.read_text(encoding="utf-8")))
        if path == allowed:
            calls = [call for call in calls if call == "shell="]
        if calls:
            offenders[path.relative_to(SRC).as_posix()] = calls
    assert offenders == {}
    assert "subprocess" in _spawning_calls(ast.parse("import subprocess"))
    assert _spawning_calls(ast.parse("os.system('x'); f(shell=True)")) == ["os.system", "shell="]
