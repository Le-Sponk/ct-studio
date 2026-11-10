"""P5-T03e33a: trusted command events come only from the process-spawning boundary.

``process.run`` reports the argv it starts (with caller-designated sensitive values replaced)
to the build step running on that thread; the runner turns each report into a ``CommandRun``.
Tool output and step log text never become commands, however much they look like one.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from build_runner_helpers import build, make_root, step
from process_fakes import fake

from ctstudio.core.build.events import BuildEvent, CommandRun, LogLine
from ctstudio.core.build.node import BuildContext
from ctstudio.core.errors import ToolFailed, ToolTimedOut
from ctstudio.core.tools import commands
from ctstudio.core.tools.commands import REDACTED, command_text, redact, reporting
from ctstudio.core.tools.process import run

SECRET = "synthetic-sensitive-value"  # noqa: S105 - made up; ASCII so JSON cannot hide it
ECHO_ARGS = "out(json.dumps(sys.argv[1:]))"
TRICKY = [
    "plain",
    "with space",
    'quo"te',
    "back\\slash\\",
    "",
    "trail\\\\",
    'a\\"b',
    "Pistë 日本",
    "100%",
    "$HOME & ^caret; `tick` 'single'",
    "tab\there",
    "a\\\n",
    "a b\\\n",
]


def _echo(*args: str) -> list[str]:
    return [str(part) for part in fake("import json\n" + ECHO_ARGS, *args)]


def _received(target: Path) -> list[str]:
    """A tool that writes the arguments it really received to ``target`` (not to output)."""
    code = f"pathlib.Path({str(target)!r}).write_text(__import__('json').dumps(sys.argv[1:]))"
    return [str(part) for part in fake(code)]


def test_command_text_round_trips_through_the_os_parser(tmp_path: Path) -> None:
    argv = _echo(*TRICKY)
    text = command_text(argv)
    if sys.platform == "win32":
        done = subprocess.run(text, capture_output=True, cwd=tmp_path, check=True)  # noqa: S603
    else:
        done = subprocess.run(  # noqa: S603 - our own interpreter, parsed by the shell
            ["/bin/sh", "-c", text], capture_output=True, cwd=tmp_path, check=True
        )
    assert json.loads(done.stdout.decode("utf-8")) == TRICKY


def test_run_reports_the_redacted_argv_it_starts_and_the_tool_gets_the_real_one(
    tmp_path: Path,
) -> None:
    reports: list[tuple[str, ...]] = []
    received = tmp_path / "received.json"
    argv = _received(received)
    log = tmp_path / "tool.log"
    with reporting(reports.append):
        run(
            [*argv, f"--key={SECRET}", SECRET, "x"],
            cwd=tmp_path,
            timeout=8,
            log_path=log,
            sensitive=[SECRET],
        )
    assert json.loads(received.read_text(encoding="utf-8")) == [f"--key={SECRET}", SECRET, "x"]
    assert reports == [(*argv, f"--key={REDACTED}", REDACTED, "x")]
    text = log.read_text(encoding="utf-8")
    assert SECRET not in text and REDACTED in text


def test_tool_output_is_redacted_in_callbacks_logs_and_tails(tmp_path: Path) -> None:
    lines: list[str] = []
    log = tmp_path / "tool.log"
    code = "out('said ' + sys.argv[1]); err('oops ' + sys.argv[1]); sys.exit(2)"
    with pytest.raises(ToolFailed) as failed:
        run(
            [*fake(code), SECRET],
            cwd=tmp_path,
            timeout=8,
            log_path=log,
            on_line=lambda _stream, line: lines.append(line),
            sensitive=[SECRET],
        )
    assert sorted(lines) == [f"oops {REDACTED}", f"said {REDACTED}"]
    assert failed.value.stderr_tail == f"oops {REDACTED}"
    text = log.read_text(encoding="utf-8")
    assert f"[out] said {REDACTED}" in text and SECRET not in text


def test_failures_and_timeouts_never_carry_a_sensitive_value(tmp_path: Path) -> None:
    with pytest.raises(ToolFailed) as failed:
        run([*fake("sys.exit(3)"), SECRET], cwd=tmp_path, timeout=8, sensitive=[SECRET])
    with pytest.raises(ToolTimedOut) as slow:
        run([*fake("time.sleep(30)"), SECRET], cwd=tmp_path, timeout=0.5, sensitive=[SECRET])
    for error in (failed.value, slow.value):
        assert error.cmd[-1] == REDACTED
        assert SECRET not in f"{error} {error.details} {error.cmd}"


def test_nothing_is_reported_outside_reporting_or_from_another_thread(tmp_path: Path) -> None:
    reports: list[tuple[str, ...]] = []
    run(fake("pass"), cwd=tmp_path, timeout=8)
    exits: list[int] = []
    with reporting(reports.append):
        worker = threading.Thread(
            target=lambda: exits.append(run(fake("pass"), cwd=tmp_path, timeout=8).exit_code)
        )
        worker.start()
        worker.join(30)
    run(fake("pass"), cwd=tmp_path, timeout=8)
    assert exits == [0], "the other thread's tool must really have run"
    assert reports == []


@pytest.mark.parametrize(
    ("argv", "windows", "posix"),
    [
        (["a", "b c"], 'a "b c"', "a 'b c'"),
        (['q"t'], '"q\\"t"', "'q\"t'"),
        (["x\\"], "x\\", "'x\\'"),
        (["x \\"], '"x \\\\"', "'x \\'"),
        (['a\\"b'], '"a\\\\\\"b"', "'a\\\"b'"),
        ([""], '""', "''"),
        (["it's"], "it's", "'it'\"'\"'s'"),
        (["a\\\n"], '"a\\\n"', "'a\\\n'"),
    ],
)
def test_command_text_quoting_on_each_platform(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], windows: str, posix: str
) -> None:
    monkeypatch.setattr(commands.sys, "platform", "win32")
    assert command_text(argv) == windows
    monkeypatch.setattr(commands.sys, "platform", "linux")
    assert command_text(argv) == posix


def test_redaction_rules() -> None:
    assert redact(["a", "xSy", "S"], ["S"]) == ("a", f"x{REDACTED}y", REDACTED)
    assert redact(["a"], []) == ("a",)
    assert redact(["abcd"], ["ab", "abc"]) == (f"{REDACTED}d",)  # longer wins: no "c" leaks
    assert redact(["xabcx"], ["abc", "bcx"]) == redact(["xabcx"], ["bcx", "abc"])
    assert redact(["S e"], ["e", "S"]) == (f"{REDACTED} {REDACTED}",)  # marker never rescanned
    with pytest.raises(ValueError, match="empty"):
        redact(["a"], [""])


def _of[T](events: list[BuildEvent], kind: type[T]) -> list[T]:
    return [event for event in events if isinstance(event, kind)]


def test_build_steps_turn_started_tools_into_command_events_only(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    looks_like = "C:/Tools/wszst.exe create stage --dest course.szs"
    argv = fake(f"out({looks_like!r})")

    def work(ctx: BuildContext) -> None:
        ctx.log(f"{looks_like} --as-a-step-note")
        run(
            [*argv, f"--key={SECRET}"],
            cwd=ctx.root,
            timeout=8,
            on_line=lambda _stream, line: ctx.log(line),
            sensitive=[SECRET],
            cancel=ctx.cancel,
        )

    summary, recorder = build(root, [step(root, "assemble", work)])
    shown = (*map(str, argv), f"--key={REDACTED}")
    assert _of(recorder.events, CommandRun) == [CommandRun("assemble", shown, command_text(shown))]
    logs = [e.text for e in _of(recorder.events, LogLine)]
    assert logs == [f"{looks_like} --as-a-step-note", looks_like]
    kinds = [kind for kind, _ in recorder.kinds()]
    assert kinds.index("NodeStarted") < kinds.index("CommandRun") < kinds.index("NodeFinished")
    assert summary.log is not None
    disk = summary.log.read_text(encoding="utf-8")
    assert f"[assemble] command: {command_text(shown)}" in disk
    assert disk.count("command: ") == 1
    assert SECRET not in disk and SECRET not in repr(recorder.events)
