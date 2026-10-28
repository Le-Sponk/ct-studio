"""Thin, typed Wiimm CLI facades; no GUI imports or shell invocations.

P2-T05a/b expose ``check``, ``analyze`` and ``create_szs``; later subtasks add proven
operations. Wiimm's exit status is not a verdict: ``check`` exits 2 on valid tracks, and
``check``/``analyze``/``create`` exit 0 on some errors, so every facade reads the output.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from ctstudio.core.errors import CTStudioError, ParseError, ToolNotFound
from ctstudio.core.tools.discovery import discover
from ctstudio.core.tools.process import CancelToken, Stream, run
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.validation.issues import Issue
from ctstudio.core.validation.wszst_check import parse_check

# Any Wiimm tool (wszst, wkmpt, wimgt, ...) reports failures as ``!! <tool>: ERROR #N [NAME]``.
ERROR_LINE = re.compile(r"(?m)^\s*!!\s+\w+: ERROR #(\d+) \[([^\]]+)\]")
Compression = Literal["best", "fast", "none"]
_COMPRESSION_FLAGS: dict[Compression, tuple[str, ...]] = {
    "best": (),  # the recorded default (= --compr=BEST)
    "fast": ("--fast",),
    "none": ("--no-compress",),
}
_ARCHIVE_MAGIC: dict[Compression, bytes] = {
    "best": b"Yaz0",
    "fast": b"Yaz0",
    "none": bytes.fromhex("55aa382d"),
}


class WiimmError(CTStudioError):
    """A Wiimm CLI rejected its input, including its exit-zero ERROR diagnostics."""

    def __init__(
        self, source: Path, exit_code: int, reason: str, *, error_code: int | None, details: str
    ) -> None:
        self.source = source
        self.exit_code = exit_code
        self.error_code = error_code
        super().__init__(
            f"Wiimm failed for {source}: {reason}",
            hint="Repair the input and rerun; inspect the tool diagnostics.",
            details=details,
        )


class WiimmCheckError(WiimmError):
    """``wszst check`` rejected the input (a distinct type for callers)."""


class AutoAddUnavailable(CTStudioError):
    """Auto-add was requested, but no library has been proven usable (P2-T05d)."""

    def __init__(self) -> None:
        super().__init__(
            "Wiimm auto-add is not available: no auto-add library has been verified.",
            hint="Build without auto-add, or set up and verify an auto-add library first.",
        )


@dataclass(frozen=True)
class _Output:
    exit_code: int
    stdout: str
    stderr: str


def executable_for(tool: str, configured: Path | None) -> Path:
    """The configured Wiimm executable, else the discovered (including dev) one."""
    if configured is not None:
        return configured.resolve()
    location = discover(TOOL_BY_ID[tool], include_dev=True)
    if location is None:
        raise ToolNotFound(tool, hint="Configure Wiimms SZS Tools or bootstrap the pinned tools.")
    return location.path


def _invoke(
    executable: Path | None, args: list[str], cwd: Path, timeout: float, cancel: CancelToken | None
) -> _Output:
    """Run wszst collecting complete streams (the runner keeps only bounded tails)."""
    lines: dict[Stream, list[str]] = {"stdout": [], "stderr": []}

    def collect(stream: Stream, line: str) -> None:
        lines[stream].append(line)

    result = run(
        [executable_for("wszst", executable), *args],
        cwd=cwd,
        timeout=timeout,
        cancel=cancel,
        on_line=collect,
        check=False,
    )
    return _Output(result.exit_code, "\n".join(lines["stdout"]), "\n".join(lines["stderr"]))


def _raise_on_error(
    out: _Output, source: Path, ok_exits: tuple[int, ...], kind: type[WiimmError] = WiimmError
) -> None:
    """``ERROR #`` fails at any exit status; so does an exit outside ``ok_exits``."""
    details = out.stderr or out.stdout
    if match := ERROR_LINE.search(f"{out.stderr}\n{out.stdout}"):
        reason = f"ERROR #{match.group(1)} [{match.group(2)}]"
        raise kind(source, out.exit_code, reason, error_code=int(match.group(1)), details=details)
    if out.exit_code not in ok_exits:
        reason = f"tool exited {out.exit_code}: {details}"
        raise kind(source, out.exit_code, reason, error_code=None, details=details)


def check(
    source: Path,
    *,
    executable: Path | None = None,
    timeout: float = 120,
    cancel: CancelToken | None = None,
) -> list[Issue]:
    """Validate an SZS or stage directory, collecting the complete tool report.

    Exit 2 can contain valid findings, while exit 0 can contain an ERROR. A prefix
    without a findings summary is incomplete, never evidence of a clean track.
    """
    source = Path(source).resolve()
    out = _invoke(executable, ["check", source.name], source.parent, timeout, cancel)
    _raise_on_error(out, source, (0, 2), WiimmCheckError)
    return parse_check(out.stdout, source, exit_code=out.exit_code)


def analyze(
    source: Path,
    *,
    executable: Path | None = None,
    timeout: float = 120,
    cancel: CancelToken | None = None,
) -> dict[str, object]:
    """Return ``wszst analyze --json`` for an SZS or stage directory.

    ``valid == 1`` means Wiimm could analyse the input; it is **not** a complete-track
    verdict (an empty archive is ``valid``). Use ``valid_track``, ``warn`` and the
    empty ``sha1_*`` hashes of missing components for track status. An unsupported
    file exits 0 with ``valid: 0`` and is raised as a ``WiimmError``.
    """
    source = Path(source).resolve()
    out = _invoke(executable, ["analyze", "--json", source.name], source.parent, timeout, cancel)
    _raise_on_error(out, source, (0,))
    try:
        parsed: object = json.loads(out.stdout)
    except json.JSONDecodeError as exc:
        raise ParseError(str(source), "wszst analyze output is not JSON") from exc
    if not isinstance(parsed, dict):
        raise ParseError(str(source), "wszst analyze JSON is not an object")
    report = cast(dict[str, object], parsed)
    if report.get("valid") != 1:
        reason = str(report.get("warning") or "input could not be analysed")
        raise WiimmError(source, out.exit_code, reason, error_code=None, details=out.stdout)
    return report


def create_szs(
    stage: Path,
    dest: Path,
    *,
    compression: Compression = "best",
    auto_add: bool = False,
    overwrite: bool = False,
    executable: Path | None = None,
    timeout: float = 300,
    cancel: CancelToken | None = None,
) -> Path:
    """Build ``dest`` from the ``stage`` directory; return it only if it was written.

    Wiimm exits 0 when the destination exists or its folder is missing (``ERROR #64``/
    ``#82`` on stderr), and ``create`` does not validate: run ``check`` afterwards.
    ``auto_add`` is refused until an auto-add library can be verified (P2-T05d), because
    wszst silently ignores ``--auto-add`` without one.
    """
    if auto_add:
        raise AutoAddUnavailable
    stage, dest = Path(stage).resolve(), Path(dest).resolve()
    args = ["create", stage.name, "--dest", str(dest), *_COMPRESSION_FLAGS[compression]]
    if overwrite:
        args.append("--overwrite")
    before = dest.stat().st_mtime_ns if dest.exists() else None
    out = _invoke(executable, args, stage.parent, timeout, cancel)
    _raise_on_error(out, stage, (0,))
    _require_archive(dest, before, compression, out)
    return dest


def _require_archive(
    dest: Path, before: int | None, compression: Compression, out: _Output
) -> None:
    """Exit 0 and no ERROR still do not prove a write: require a new file of the format."""
    written = dest.is_file() and dest.stat().st_mtime_ns != before
    if not written or dest.read_bytes()[:4] != _ARCHIVE_MAGIC[compression]:
        reason = f"no SZS of the requested format was written to {dest}"
        raise WiimmError(dest, out.exit_code, reason, error_code=None, details=out.stdout)
