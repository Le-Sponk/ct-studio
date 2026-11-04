"""Services the GUI views get by injection (ARCHITECTURE §10).

``AppServices`` (P5-T01a/b) holds what the whole app shares: the current project (opened,
so locked, by this app), the tools, the build controller and the part statuses.
``ToolsService`` (P2-T07b) is what the Tools page needs: the user's settings file and the
doctor check. Its methods block (disk, version probes), so views call them from a worker.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import settings
from ctstudio.core.project.project import Project
from ctstudio.core.project.settings import SettingsError
from ctstudio.core.tools import doctor
from ctstudio.core.tools.doctor import Report
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.status_service import StatusService

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

    def configured(self) -> Mapping[str, Path] | None:
        """The paths set in settings now, or None when the settings file cannot be used."""
        try:
            return settings.load(self._settings_path).configured()
        except SettingsError:
            return None

    def save_path(self, tool_id: str, path: Path | None) -> None:
        """Set (or, with None, clear) the path of one tool; the old file is backed up."""
        current = settings.load(self._settings_path)
        settings.save(current.with_tool(tool_id, path), self._settings_path)

    def set_path(self, tool_id: str, path: Path | None) -> ToolsResult:
        """Save the path, then check again so the page shows what it changed."""
        self.save_path(tool_id, path)
        return self.check(force=False)


class AppServices:
    """The current project, the tools and the build, for every view (injected, not global).

    Opening a project takes its lock (``Project.open``) and closes the one open before; a
    project being built is neither switched nor closed. The statuses are asked for when a
    project opens and after every build (one that failed may have changed files too).
    ``shutdown`` stops the build and the status work, then closes the project.
    """

    def __init__(
        self,
        *,
        tools: ToolsService | None = None,
        build: BuildController | None = None,
        status: StatusService | None = None,
    ) -> None:
        self.tools = tools if tools is not None else ToolsService()
        self.build = build if build is not None else BuildController()
        self.status = status if status is not None else StatusService()
        self.project: Project | None = None
        self.build.finished.connect(self._refresh)
        self.build.failed.connect(self._refresh)

    def open_project(self, root: Path) -> Project:
        """Open ``root`` (read-only when another CT Studio has it) and make it current."""
        self._refuse_while_building()
        if self.project is not None and self.project.root == root:
            return self.project  # this app already holds it; opening again would be read-only
        opened = Project.open(root)  # first, so a failure leaves the current project open
        self.close_project()
        self.project = opened
        self.status.request(opened)
        return opened

    def adopt(self, project: Project) -> None:
        """Make ``project`` (already opened, e.g. just created) current, closing the one before.

        Refused while a build runs; ``project`` is then closed, so its lock is not left behind.
        """
        if self.build.running:
            project.close()
            self._refuse_while_building()
        self.close_project()
        self.project = project
        self.status.request(project)

    def close_project(self) -> None:
        self._refuse_while_building()
        self.status.clear()
        if self.project is not None:
            self.project.close()
            self.project = None

    def shutdown(self, timeout: float) -> bool:
        """Stop the build and the status work (each waited for up to ``timeout`` s), then
        close the project.

        False when either did not stop in time; the project then stays open (and locked).
        """
        if not self.build.shutdown(timeout) or not self.status.shutdown(timeout):
            return False
        self.close_project()
        return True

    def _refresh(self, _result: object) -> None:
        if self.project is not None:
            self.status.request(self.project)

    def _refuse_while_building(self) -> None:
        if self.build.running:
            raise ProjectError(
                "The project is being built, so it stays open.",
                hint="Wait for the build to finish, or cancel it, then try again.",
            )
