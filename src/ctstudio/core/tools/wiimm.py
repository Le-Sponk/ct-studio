"""Thin, typed Wiimm CLI facades; no GUI imports or shell invocations.

Only ``check`` is available in P2-T05a; later subtasks add proven operations.
"""

from __future__ import annotations

import re
from pathlib import Path

from ctstudio.core.errors import CTStudioError, ToolNotFound
from ctstudio.core.tools.discovery import discover
from ctstudio.core.tools.process import CancelToken, Stream, run
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.validation.issues import Issue
from ctstudio.core.validation.wszst_check import parse_check

_ERROR = re.compile(r"(?m)^\s*!!\s+wszst: ERROR #(\d+) \[([^\]]+)\]")


class WiimmCheckError(CTStudioError):
    """The CLI rejected the input, including its exit-zero ERROR diagnostic."""

    def __init__(
        self, source: Path, exit_code: int, reason: str, *, error_code: int | None, details: str
    ) -> None:
        self.source = source
        self.exit_code = exit_code
        self.error_code = error_code
        super().__init__(
            f"Wiimm check failed for {source}: {reason}",
            hint="Repair the input and rerun the check; inspect the tool diagnostics.",
            details=details,
        )


def _executable(configured: Path | None) -> Path:
    if configured is not None:
        return configured.resolve()
    location = discover(TOOL_BY_ID["wszst"], include_dev=True)
    if location is None:
        raise ToolNotFound("wszst", hint="Configure Wiimms SZS Tool or bootstrap the pinned tool.")
    return location.path


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
    stdout: list[str] = []
    stderr: list[str] = []

    def collect(stream: Stream, line: str) -> None:
        (stdout if stream == "stdout" else stderr).append(line)

    result = run(
        [_executable(executable), "check", source.name],
        cwd=source.parent,
        timeout=timeout,
        cancel=cancel,
        on_line=collect,
        check=False,
    )
    diagnostic = "\n".join((*stderr, *stdout))
    if match := _ERROR.search(diagnostic):
        raise WiimmCheckError(
            source,
            result.exit_code,
            f"ERROR #{match.group(1)} [{match.group(2)}]",
            error_code=int(match.group(1)),
            details=result.stderr_tail or result.stdout_tail,
        )
    if result.exit_code not in (0, 2):
        raise WiimmCheckError(
            source,
            result.exit_code,
            f"tool exited {result.exit_code}: {result.stderr_tail or result.stdout_tail}",
            error_code=None,
            details=result.stderr_tail or result.stdout_tail,
        )
    return parse_check("\n".join(stdout), source, exit_code=result.exit_code)
