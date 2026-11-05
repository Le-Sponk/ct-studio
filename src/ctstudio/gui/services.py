"""Services the GUI views get by injection (ARCHITECTURE §10).

``AppServices`` (P5-T01a/b) holds what the whole app shares: the current project (opened,
so locked, by this app), the tools, the build controller, the part statuses and the editor /
folder launch owner (P5-T03i).
``ToolsService`` (P2-T07b) is what the Tools page needs: the user's settings file and the
doctor check. Its methods block (disk, version probes), so views call them from a worker.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import settings
from ctstudio.core.project.project import Project
from ctstudio.core.project.settings import SettingsError
from ctstudio.core.tools import doctor
from ctstudio.core.tools.doctor import Report
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.launch_controller import LaunchController
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
    project being built, edited or launched is neither switched nor closed. The statuses are
    asked for when a project opens and after every build (one that failed may have changed
    files too). ``shutdown`` stops the build, status and launch work, then closes the project.
    """

    def __init__(
        self,
        *,
        tools: ToolsService | None = None,
        build: BuildController | None = None,
        status: StatusService | None = None,
        launch: LaunchController | None = None,
    ) -> None:
        self.tools = tools if tools is not None else ToolsService()
        self.build = build if build is not None else BuildController()
        self.status = status if status is not None else StatusService()
        self.launch = launch if launch is not None else LaunchController()
        self.project: Project | None = None
        self.editing = False  # modal project-details owner; prevents switching/releasing its lock
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
        if self.build.running or self.editing or self.launch.busy:
            if project is not self.project:
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
        """Stop the build, the status work and the launch (each waited for up to ``timeout``
        s), then close the project.

        False when any did not stop in time; the project then stays open (and locked).
        """
        if self.editing:
            return False  # the modal editor owns a worker and the project lock until it closes
        if (
            not self.build.shutdown(timeout)
            or not self.status.shutdown(timeout)
            or not self.launch.shutdown(timeout)
        ):
            return False
        self.close_project()
        return True

    def start_launch(self, component_id: str | None = None) -> bool:
        """Open the current project in Blender (None) or reveal one component's folder.

        Checks only in-memory state (no disk); refusals raise an actionable ``ProjectError``.
        Read-only projects may reveal folders but not launch Blender.
        """
        project = self.project
        if project is None:
            raise ProjectError("No project is open.", hint="Open or create a project first.")
        self._refuse_while_building()
        if self.status.busy:
            raise ProjectError(
                "Component statuses are still being checked.",
                hint="Wait for the check to finish, then try again.",
            )
        if component_id is None:
            _check_blender(project)
        elif component_id not in COMPONENT_BY_ID:
            raise ProjectError(
                f"Cannot reveal unknown component '{component_id}'.",
                hint="Choose a component card from the current project.",
            )
        return self.launch.start(project, component_id)

    def _refresh(self, _result: object) -> None:
        if self.project is not None:
            self.status.request(self.project)

    def _refuse_while_building(self) -> None:
        if self.editing:
            raise ProjectError(
                "Project details are open, so this project stays open.",
                hint="Save or cancel project details, then try again.",
            )
        if self.build.running:
            raise ProjectError(
                "The project is being built, so it stays open.",
                hint="Wait for the build to finish, or cancel it, then try again.",
            )
        if self.launch.busy:
            raise ProjectError(
                "A Blender launch or folder request is still finishing; the project stays open.",
                hint="Wait a moment for it to finish, then try again.",
            )


def _check_blender(project: Project) -> None:
    if project.read_only:
        raise ProjectError(
            "Cannot launch Blender for a read-only project.",
            hint="Close it in the other CT Studio, then reopen it here for editing.",
        )
    if not project.manifest.project.blend:
        raise ProjectError(
            "This project has no Blender source.",
            hint="Choose a .blend source in Project details first.",
        )
