"""Run external tools: the only module in ``src/ctstudio`` that spawns processes.

AGENTS rule 3 / ARCHITECTURE §9. Arguments are argv lists with an absolute executable and
never a shell. Reader threads drain both pipes so large output cannot deadlock; lines are
decoded as UTF-8 with replacement and handed to the caller's thread in arrival order, kept
as bounded tails, and appended to an optional log. Timeouts, cancellation and callback
failures stop the whole process tree (see ``process_tree``).
"""

from __future__ import annotations

import codecs
import math
import os
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from typing import IO, Literal, TextIO

from ctstudio.core.errors import Cancelled, ProjectError, ToolFailed, ToolNotFound, ToolTimedOut
from ctstudio.core.tools.process_tree import ProcessTree

Stream = Literal["stdout", "stderr"]
LineCallback = Callable[[Stream, str], None]

TAIL_LINES = 50
CHUNK_BYTES = 65_536
MAX_LINE_CHARS = 1_000_000  # an endless line is delivered in pieces rather than held forever
POLL_SECONDS = 0.05  # cancellation and timeout latency
PIPE_GRACE_SECONDS = 0.5  # descendants may keep inherited pipes open after the tool exits
_LOG_TAGS: dict[Stream, str] = {"stdout": "out", "stderr": "err"}
_Event = tuple[Stream, list[str] | None]


class CancelToken:
    """A thread-safe request to stop a running tool, honoured within ``POLL_SECONDS``."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    duration: float
    stdout_tail: str
    stderr_tail: str
    log_path: Path | None


def _empty_tails() -> dict[Stream, deque[str]]:
    return {"stdout": deque(maxlen=TAIL_LINES), "stderr": deque(maxlen=TAIL_LINES)}


@dataclass
class _Session:
    proc: subprocess.Popen[bytes]
    tree: ProcessTree
    events: Queue[_Event]
    log: TextIO | None
    on_line: LineCallback | None
    tails: dict[Stream, deque[str]] = field(default_factory=_empty_tails)
    open_streams: int = 2

    def deliver(self, wait: float) -> None:
        """Pass at most one batch of lines to the tails, the log and the callback."""
        try:
            stream, lines = self.events.get(timeout=wait)
        except Empty:
            return
        if lines is None:
            self.open_streams -= 1
            return
        self.tails[stream].extend(lines)
        if self.log is not None:
            tag = _LOG_TAGS[stream]
            self.log.write("".join(f"[{tag}] {line}\n" for line in lines))
        if self.on_line is not None:
            for line in lines:
                self.on_line(stream, line)

    def tail(self, stream: Stream) -> str:
        return "\n".join(self.tails[stream])


def run(
    cmd: Sequence[str | Path],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    on_line: LineCallback | None = None,
    cancel: CancelToken | None = None,
    log_path: Path | None = None,
    check: bool = True,
) -> RunResult:
    """Run a CLI tool to completion without a console window.

    ``env`` adds to (never replaces) the inherited environment. ``on_line`` runs on the
    calling thread; if it raises, the tool is stopped and the exception propagates.
    Raises ``ToolNotFound``, ``ToolTimedOut``, ``Cancelled``, and with ``check`` a non-zero
    exit raises ``ToolFailed`` carrying the stderr tail (stdout's when stderr is empty).
    """
    argv = _argv(cmd)
    _require_folder(cwd)
    if cancel is not None and cancel.cancelled:
        raise Cancelled(Path(argv[0]).name)
    limit = math.inf if timeout is None else timeout
    with ExitStack() as stack:
        log = _open_log(stack, log_path, argv, cwd)
        started = time.monotonic()
        session = _start(argv, cwd, env, log, on_line)
        stack.callback(session.tree.close)
        try:
            stopped = _pump(session, started + limit, cancel)
        except BaseException as exc:
            _stop(session, f"# stopped: {type(exc).__name__}")
            raise
        duration = time.monotonic() - started
        if stopped is not None:
            _stop(session, f"# stopped: {stopped} after {duration:.2f} s")
            if stopped == "cancelled":
                raise Cancelled(Path(argv[0]).name)
            raise ToolTimedOut(argv, limit, log_path)
        _note(log, f"# exit {session.proc.returncode} after {duration:.2f} s")
        result = RunResult(
            session.proc.returncode,
            duration,
            session.tail("stdout"),
            session.tail("stderr"),
            log_path,
        )
    if check and result.exit_code != 0:
        tail = result.stderr_tail or result.stdout_tail
        raise ToolFailed(argv, result.exit_code, tail, log_path)
    return result


def launch_detached(
    cmd: Sequence[str | Path], *, cwd: Path, env: Mapping[str, str] | None = None
) -> int:
    """Start a GUI editor that outlives this call and CT Studio; return its process id.

    Its output is discarded and it is not part of any killable tree. A daemon thread reaps
    it on exit so no zombie remains on POSIX.
    """
    argv = _argv(cmd)
    _require_folder(cwd)
    proc = _popen(argv, cwd, _environment(env), detached=True)
    threading.Thread(target=proc.wait, name=f"reap-{proc.pid}", daemon=True).start()
    return proc.pid


def _argv(cmd: Sequence[str | Path]) -> list[str]:
    argv = [os.fspath(part) for part in cmd]
    # Windows CreateProcess searches the parent's PATH, not env["PATH"]; require a resolved path.
    if not argv or not Path(argv[0]).is_absolute():
        raise ValueError("cmd[0] must be an absolute executable path from tool discovery")
    return argv


def _require_folder(cwd: Path) -> None:
    if not cwd.is_dir():
        raise ProjectError(
            f"The working folder does not exist: {cwd}",
            hint="Choose an existing folder and try again.",
        )


def _environment(extra: Mapping[str, str] | None) -> dict[str, str] | None:
    if extra is None:
        return None
    merged = dict(os.environ)
    for key, value in extra.items():
        # Windows names are case-insensitive and os.environ stores them upper-cased.
        merged[key.upper() if sys.platform == "win32" else key] = value
    return merged


def _popen(
    argv: list[str], cwd: Path, env: dict[str, str] | None, *, detached: bool
) -> subprocess.Popen[bytes]:
    pipe = subprocess.DEVNULL if detached else subprocess.PIPE
    try:
        if sys.platform == "win32":
            if detached:
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            else:  # suspended until ProcessTree has put it in a job
                create_suspended = 0x00000004
                flags = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | subprocess.CREATE_NO_WINDOW
                    | create_suspended
                )
            return subprocess.Popen(  # noqa: S603 - argv list, absolute executable, no shell
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=pipe,
                stderr=pipe,
                bufsize=0,
                creationflags=flags,
            )
        return subprocess.Popen(  # noqa: S603 - argv list, absolute executable, no shell
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=pipe,
            stderr=pipe,
            bufsize=0,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise ToolNotFound(Path(argv[0]).name) from exc
    except PermissionError as exc:
        hint = "Check that the file is a program you are allowed to run, or choose another."
        raise ToolNotFound(Path(argv[0]).name, hint=hint) from exc


def _start(
    argv: list[str],
    cwd: Path,
    env: Mapping[str, str] | None,
    log: TextIO | None,
    on_line: LineCallback | None,
) -> _Session:
    proc = _popen(argv, cwd, _environment(env), detached=False)
    try:
        tree = ProcessTree(proc.pid)
    except OSError:
        proc.kill()
        proc.wait()
        raise
    if proc.stdout is None or proc.stderr is None:  # narrowing: PIPE always creates both
        raise RuntimeError("subprocess did not create the requested pipes")
    events: Queue[_Event] = Queue()
    pipes: tuple[tuple[Stream, IO[bytes]], ...] = (("stdout", proc.stdout), ("stderr", proc.stderr))
    for stream, pipe in pipes:
        reader = threading.Thread(
            target=_read, args=(pipe, stream, events), name=f"{stream}-{proc.pid}", daemon=True
        )
        reader.start()
    return _Session(proc, tree, events, log, on_line)


def _read(pipe: IO[bytes], stream: Stream, events: Queue[_Event]) -> None:
    """Reader thread: decode incrementally so a split UTF-8 sequence is not replaced."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    try:
        while chunk := os.read(pipe.fileno(), CHUNK_BYTES):
            pending, lines = _split(pending + decoder.decode(chunk))
            if lines:
                events.put((stream, lines))
        rest = pending + decoder.decode(b"", final=True)
        if rest:
            events.put((stream, [rest.removesuffix("\r")]))
    finally:
        pipe.close()
        events.put((stream, None))


def _split(text: str) -> tuple[str, list[str]]:
    *complete, pending = text.split("\n")
    lines = [line.removesuffix("\r") for line in complete]
    if len(pending) > MAX_LINE_CHARS:
        lines.append(pending)
        pending = ""
    return pending, lines


def _stop_reason(cancel: CancelToken | None, deadline: float) -> str | None:
    if cancel is not None and cancel.cancelled:
        return "cancelled"
    if time.monotonic() >= deadline:
        return "timeout"
    return None


def _pump(session: _Session, deadline: float, cancel: CancelToken | None) -> str | None:
    """Deliver output until the tool exits and both pipes close; else name why it stopped."""
    exited_at = math.inf
    while session.open_streams or session.proc.poll() is None:
        reason = _stop_reason(cancel, deadline)
        if reason is not None:
            return reason
        now = time.monotonic()
        if exited_at == math.inf and session.proc.poll() is not None:
            exited_at = now
        if now - exited_at > PIPE_GRACE_SECONDS:
            return None  # descendants still hold the pipes; ProcessTree.close() stops them
        session.deliver(POLL_SECONDS)
    return None


def _drain(session: _Session) -> None:
    end = time.monotonic() + PIPE_GRACE_SECONDS
    while session.open_streams and time.monotonic() < end:
        session.deliver(POLL_SECONDS)


def _stop(session: _Session, note: str) -> None:
    session.tree.kill()
    session.proc.kill()
    session.proc.wait()
    _drain(session)
    _note(session.log, note)


def _open_log(stack: ExitStack, log_path: Path | None, argv: list[str], cwd: Path) -> TextIO | None:
    if log_path is None:
        return None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = stack.enter_context(log_path.open("a", encoding="utf-8", newline="\n"))
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    log.write(f"# run {stamp} cwd={cwd} argv={argv!r}\n")
    return log


def _note(log: TextIO | None, text: str) -> None:
    if log is not None:
        log.write(text + "\n")
