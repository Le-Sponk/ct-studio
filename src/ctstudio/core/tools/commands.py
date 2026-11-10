"""Trusted command reporting: what a tool was started with, safe to show and copy (P5-T03e33a).

Only ``process.run`` reports, and only for the argv it actually started, so arbitrary tool
output can never become a command. Values a caller marks sensitive are replaced by
``REDACTED`` in the argv and in the tool's output lines before they reach a report, a line
callback, the tool log or an error; the executable path, working folder and environment are
not covered (they never hold such values). Reports go to the
callback installed by ``reporting`` on the same thread (the build step's worker); a tool run
on another thread, or outside ``reporting``, reports nothing.
"""

from __future__ import annotations

import re
import shlex
import sys
import threading
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager

REDACTED = "<redacted>"
Reporter = Callable[[tuple[str, ...]], None]
Redactor = Callable[[str], str]


class _Local(threading.local):
    reporter: Reporter | None = None


_LOCAL = _Local()


def redactor(sensitive: Sequence[str]) -> Redactor:
    """Replace every occurrence of each sensitive value by ``REDACTED`` in one pass.

    Longer values win where they overlap, ties in a fixed order, and a replacement is never
    scanned again, so the marker itself cannot be garbled.
    """
    if any(not value for value in sensitive):
        raise ValueError("a sensitive value must not be empty")
    if not sensitive:
        return lambda text: text
    values = sorted(set(sensitive), key=lambda value: (-len(value), value))
    pattern = re.compile("|".join(map(re.escape, values)))
    return lambda text: pattern.sub(REDACTED, text)


def redact(argv: Sequence[str], sensitive: Sequence[str]) -> tuple[str, ...]:
    """``argv`` with every occurrence of each sensitive value replaced by ``REDACTED``."""
    hide = redactor(sensitive)
    return tuple(hide(part) for part in argv)


def command_text(argv: Sequence[str]) -> str:
    """One command line that this platform parses back into exactly ``argv``.

    Windows: the Microsoft C runtime / ``CommandLineToArgvW`` argument rules, as used when the
    line is passed to ``CreateProcess`` or typed in PowerShell's call syntax; it is not escaped
    for cmd.exe, where ``%VAR%`` and unquoted ``& ^ | < >`` keep their meaning. Elsewhere:
    POSIX shell quoting (``shlex.join``).
    """
    if sys.platform == "win32":
        return " ".join(_windows_arg(part) for part in argv)
    return shlex.join(argv)


_WINDOWS_PLAIN = re.compile(r'[^\s"]+')
_BACKSLASHES_BEFORE_QUOTE = re.compile(r'(\\*)"')
_TRAILING_BACKSLASHES = re.compile(r"(\\+)\Z")  # \Z: $ also matches before a final \n


def _windows_arg(part: str) -> str:
    """Quote when needed; double backslashes that precede a quote, then escape the quote."""
    if _WINDOWS_PLAIN.fullmatch(part):
        return part
    quoted = _BACKSLASHES_BEFORE_QUOTE.sub(lambda m: m.group(1) * 2 + '\\"', part)
    return '"' + _TRAILING_BACKSLASHES.sub(lambda m: m.group(1) * 2, quoted) + '"'


@contextmanager
def reporting(reporter: Reporter) -> Generator[None]:
    """Send this thread's tool starts to ``reporter`` until the block ends."""
    previous, _LOCAL.reporter = _LOCAL.reporter, reporter
    try:
        yield
    finally:
        _LOCAL.reporter = previous


def report(shown: tuple[str, ...]) -> None:
    """Called by ``process.run`` with the redacted argv of a tool it has started."""
    reporter = _LOCAL.reporter
    if reporter is not None:
        reporter(shown)
