"""Typed, actionable errors shared by the CLI and GUI without importing Qt."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class CTStudioError(Exception):
    """A user-facing failure with a next step and optional private diagnostics."""

    def __init__(
        self, user_message: str, hint: str | None = None, details: str | None = None
    ) -> None:
        self.user_message = user_message
        self.hint = hint
        self.details = details
        super().__init__(user_message)

    def __str__(self) -> str:
        if self.hint:
            return f"{self.user_message}\nNext: {self.hint}"
        return self.user_message


class ToolNotFound(CTStudioError):
    """An external executable is not installed or configured."""

    def __init__(self, tool: str, hint: str | None = None) -> None:
        self.tool = tool
        super().__init__(
            f"{tool} was not found.",
            hint=hint or "Install the tool and configure its executable path in CT Studio.",
        )


class ToolFailed(CTStudioError):
    """A tool returned a non-zero status; raw output stays out of UI copy."""

    def __init__(
        self, cmd: Sequence[str], exit_code: int, stderr_tail: str, log_path: Path | None
    ) -> None:
        self.cmd = tuple(cmd)
        self.exit_code = exit_code
        self.stderr_tail = stderr_tail
        self.log_path = log_path
        details = f"argv: {self.cmd!r}\nstderr tail: {stderr_tail}\nlog: {log_path}"
        hint = (
            "Check the tool log and its inputs, then try again."
            if log_path is not None
            else "Check the tool's inputs and try again."
        )
        super().__init__(
            f"{Path(self.cmd[0]).name} failed (exit code {exit_code}).",
            hint=hint,
            details=details,
        )


class ProjectError(CTStudioError):
    """A project folder or its contents cannot be used."""

    def __init__(
        self,
        user_message: str,
        hint: str = "Check the project folder and try again.",
        details: str | None = None,
    ) -> None:
        super().__init__(user_message, hint=hint, details=details)


class ManifestError(ProjectError):
    """An invalid key or value in ctstudio.toml."""

    def __init__(self, key_path: str, reason: str | None = None) -> None:
        self.key_path = key_path
        message = f"Invalid ctstudio.toml value at '{key_path}'"
        if reason:
            message += f": {reason}"
        super().__init__(message + ".", hint="Correct the value in ctstudio.toml and try again.")


class BuildError(CTStudioError):
    """A build node failed without losing its identifier."""

    def __init__(self, node_id: str, reason: str | None = None) -> None:
        self.node_id = node_id
        message = f"Build step '{node_id}' failed"
        if reason:
            message += f": {reason}"
        super().__init__(message + ".", hint="Review the build log, correct the issue and retry.")


class Cancelled(CTStudioError):
    """An operation stopped at the user's request."""

    def __init__(self, operation: str = "Operation") -> None:
        super().__init__(f"{operation} was cancelled.", hint="Run it again when ready.")


class ParseError(CTStudioError):
    """A file cannot be decoded or interpreted."""

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(
            f"Could not parse {source}: {reason}.",
            hint="Check the file format and try again.",
        )
