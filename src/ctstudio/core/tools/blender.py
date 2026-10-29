"""Typed adapter for running a Python script in headless Blender 5.2.2.

Measured on Windows (P2-T04e, P2-T05f; docs/reference/TOOLS.md):

* A script exception prints a traceback and exits **0** unless ``--python-exit-code N``
  (N in 1..255) comes *before* ``--python``; placed after it, it is ignored. The adapter
  always passes ``FAILURE_EXIT`` there and recognises Blender's own
  ``Error: script failed`` line, so a script's own ``sys.exit(113)`` is not misread.
* ``sys.exit(N)`` exits N without any error text; an unreadable ``.blend`` exits 1 with
  only a stdout ``ERROR …`` report and the script never runs.
* Arguments after ``--`` reach ``sys.argv`` verbatim, including later ``--``/``-b``.
* Absolute script and ``.blend`` paths with spaces, ``é`` and ``日本`` work.

Only a directly executable Blender is run: Flatpak's sandbox paths are not verified yet.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from ctstudio.core.errors import CTStudioError, ToolNotFound
from ctstudio.core.tools.discovery import discover
from ctstudio.core.tools.process import CancelToken, LineCallback, RunResult, run
from ctstudio.core.tools.registry import TOOL_BY_ID

FAILURE_EXIT = 113  # not a code Blender or Python use for their own failures
_SCRIPT_FAILED = "Error: script failed"
_REPORT = re.compile(r"\|\s*ERROR (.+?)(?: in file \"[^\"]*\"|: \"[^\"]*\")?(?::\s*(.+))?$", re.M)
_EXCEPTION = re.compile(r"^(?:[A-Za-z_][\w.]*(?:Error|Exception|Interrupt|Exit)\b.*)$", re.M)
_HINT = "Install Blender 5.2 or configure its executable in CT Studio."


class BlenderError(CTStudioError):
    """Blender or the script failed; ``details`` holds both output tails."""

    def __init__(
        self, script: Path, reason: str, *, exit_code: int | None = None, details: str = ""
    ) -> None:
        self.script = script
        self.exit_code = exit_code
        super().__init__(
            f"Blender could not run {script.name}: {reason}",
            hint="Read the script's error below, fix the script or the .blend, and run it again.",
            details=details or None,
        )


def _executable(configured: Path | None) -> Path:
    if configured is not None:
        return configured.resolve()
    location = discover(TOOL_BY_ID["blender"], include_dev=True)
    if location is None:
        raise ToolNotFound("blender", hint=_HINT)
    if location.launcher != "direct":
        raise ToolNotFound(
            "blender",
            hint="Flatpak Blender cannot run CT Studio scripts yet; configure a directly "
            "installed Blender executable.",
        )
    return location.path


def _check_blend(blend: Path, script: Path) -> None:
    if blend.suffix.lower() != ".blend":
        raise BlenderError(script, f"{blend.name} is not a .blend file")
    if not blend.is_file():
        raise BlenderError(script, f"{blend.name} not found")


def _check_inputs(blend: Path | None, script: Path, args: Sequence[str]) -> None:
    if not script.is_file():
        raise BlenderError(script, "script not found")
    if script.suffix.lower() != ".py":
        raise BlenderError(script, "a Blender script must be a Python (.py) file")
    if blend is not None:
        _check_blend(blend, script)
    if bad := [arg for arg in args if not isinstance(cast(object, arg), str) or "\x00" in arg]:
        raise BlenderError(script, f"script argument {bad[0]!r} must be text without NUL")


def _environment(tool_dirs: Sequence[Path]) -> dict[str, str] | None:
    """Folders put first on PATH (factory startup ignores add-on tool preferences)."""
    if not tool_dirs:
        return None
    return {"PATH": os.pathsep.join([*(str(d) for d in tool_dirs), os.environ.get("PATH", "")])}


def _script_exception(stderr: str) -> str:
    exceptions = _EXCEPTION.findall(stderr.split(_SCRIPT_FAILED)[0])
    return exceptions[-1].strip() if exceptions else "the script raised an error"


def _blend_report(report: re.Match[str]) -> str:
    message, cause = report.group(1).strip(), report.group(2)
    blend = re.search(r"\"([^\"]+\.blend)\"", report.group(0))
    name = Path(blend.group(1).replace("\\", "/")).name if blend else "the .blend"
    return f"could not open {name}: {message}" + (f" ({cause.strip()})" if cause else "")


def _reason(result: RunResult) -> str:
    code = result.exit_code
    if code == FAILURE_EXIT and _SCRIPT_FAILED in result.stderr_tail:
        return _script_exception(result.stderr_tail)
    if code == 1 and (report := _REPORT.search(result.stdout_tail)):
        return _blend_report(report)
    return f"blender exited {code}"


def _argv(
    executable: Path, blend: Path | None, script: Path, args: Sequence[str]
) -> list[str | Path]:
    opened: list[str | Path] = [] if blend is None else [blend]
    tail: list[str | Path] = ["--", *args] if args else []
    return [
        executable,
        "-b",
        *opened,
        "--factory-startup",
        "--python-exit-code",
        str(FAILURE_EXIT),
        "--python",
        script,
        *tail,
    ]


def run_script(
    blend: Path | None,
    script: Path,
    args: Sequence[str] = (),
    *,
    timeout: float = 600,
    executable: Path | None = None,
    tool_dirs: Sequence[Path] = (),
    cancel: CancelToken | None = None,
    log_path: Path | None = None,
    on_line: LineCallback | None = None,
) -> RunResult:
    """Run ``script`` (optionally on ``blend``) in background Blender, in the script's folder.

    Returns the run on exit 0; raises ``BlenderError`` for any other exit, plus the
    runner's ``ToolNotFound``, ``ToolTimedOut`` and ``Cancelled``.
    """
    script = Path(script).resolve()
    blend = None if blend is None else Path(blend).resolve()
    _check_inputs(blend, script, args)
    argv = _argv(_executable(executable), blend, script, args)
    result = run(
        argv,
        cwd=script.parent,
        env=_environment(tool_dirs),
        timeout=timeout,
        cancel=cancel,
        log_path=log_path,
        on_line=on_line,
        check=False,
    )
    if result.exit_code != 0:
        details = "\n".join(part for part in (result.stderr_tail, result.stdout_tail) if part)
        raise BlenderError(script, _reason(result), exit_code=result.exit_code, details=details)
    return result
