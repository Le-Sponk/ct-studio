"""Services the GUI views get by injection (ARCHITECTURE §10); no Qt in here yet.

``ToolsService`` (P2-T07b) is what the Tools page needs: the user's settings file and the
doctor check. Its methods block (disk, version probes), so views call them from a worker.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ctstudio.core.project import settings
from ctstudio.core.project.settings import SettingsError
from ctstudio.core.tools import doctor
from ctstudio.core.tools.doctor import Report

Diagnose = Callable[..., Report]


@dataclass(frozen=True)
class ToolsResult:
    """One finished check: the report, the paths set in settings, and any settings problem."""

    report: Report
    configured: Mapping[str, Path] = field(default_factory=lambda: {})
    settings_problem: str | None = None  # the settings file cannot be used; never overwrite it


class ToolsService:
    def __init__(
        self, *, settings_path: Path | None = None, diagnose: Diagnose = doctor.diagnose
    ) -> None:
        self._settings_path = settings_path
        self._diagnose = diagnose

    def check(self, *, force: bool) -> ToolsResult:
        """Check every tool with the paths set in settings (blocking)."""
        try:
            configured = settings.load(self._settings_path).configured()
            problem = None
        except SettingsError as exc:
            configured, problem = {}, str(exc)
        report = self._diagnose(force=force, configured=configured)
        return ToolsResult(report, configured, problem)

    def save_path(self, tool_id: str, path: Path | None) -> None:
        """Set (or, with None, clear) the path of one tool; the old file is backed up."""
        current = settings.load(self._settings_path)
        settings.save(current.with_tool(tool_id, path), self._settings_path)

    def set_path(self, tool_id: str, path: Path | None) -> ToolsResult:
        """Save the path, then check again so the page shows what it changed."""
        self.save_path(tool_id, path)
        return self.check(force=False)
