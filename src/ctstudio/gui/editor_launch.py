"""Blocking, read-only editor preparation; readiness is advisory, never launch authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from ctstudio.core import platform
from ctstudio.core.errors import ProjectError, ToolNotFound
from ctstudio.core.project import settings
from ctstudio.core.project.project import Project
from ctstudio.core.tools import custom_editors, discovery, editors, wine
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.saved_editors import EditorChoice, open_saved
from ctstudio.core.tools.spec import CustomTool, ToolSpec


class DiscoverTool(Protocol):
    def __call__(
        self, spec: ToolSpec, *, configured: Path | None = None, include_dev: bool = False
    ) -> discovery.ToolLocation | None: ...


@dataclass(frozen=True)
class EditorOption:
    """Exact saved namespace/id plus immutable presentation-only readiness."""

    choice: EditorChoice
    label: str
    state: Literal["available", "missing", "ineligible"]
    explanation: str
    hint: str


@dataclass(frozen=True)
class PreparedEditors:
    """A snapshot of choices; dispatch must call open_saved with fresh settings."""

    document: Path
    kind: str
    options: tuple[EditorOption, ...]


class EditorLaunchService:
    """Caller owns execution context; no worker, launch or application guards here."""

    def __init__(
        self,
        settings_path: Path | None = None,
        *,
        discover_tool: DiscoverTool = discovery.discover,
        current_platform: Callable[[], str] = platform.current_os,
    ) -> None:
        self._settings_path = settings_path
        self._discover = discover_tool
        self._platform = current_platform

    def prepare(self, project: Project, document: Path) -> PreparedEditors:
        """Inspect fresh settings and tool locations without starting a process."""
        root, manifest = project.root, project.manifest
        try:
            prepared = self._prepare(document)
            if project.root != root or project.manifest is not manifest:
                raise ProjectError(
                    "The project changed while preparing editor choices.",
                    hint="Select the current project and prepare editor choices again.",
                )
            return prepared
        except (OSError, ValueError, RuntimeError) as error:
            raise ProjectError(
                "Could not inspect editor choices.",
                hint="Check document, tool and settings paths and permissions, then retry.",
                details=str(error),
            ) from error

    def dispatch(self, project: Project, choice: EditorChoice, document: Path) -> editors.Launched:
        """Start exactly ``choice`` with settings read now (preparation is not authority)."""
        return open_saved(choice, document, project=project.root, settings_path=self._settings_path)

    def _prepare(self, document: Path) -> PreparedEditors:
        document = custom_editors.checked_path("editor", document, document, "document")
        loaded = settings.load(self._settings_path)
        kind = document.suffix.lower()
        options = tuple(
            self._builtin(tool_id, document, loaded)
            for tool_id in loaded.editor_order(kind)
            if kind in editors.EDITOR_DOCUMENTS.get(tool_id, ())
        )
        options += tuple(
            self._custom(tool_id, tool, document, loaded)
            for tool_id, tool in loaded.custom_tools().items()
        )
        return PreparedEditors(document, kind, options)

    def _custom(
        self, tool_id: str, tool: CustomTool, document: Path, loaded: settings.UserSettings
    ) -> EditorOption:
        choice = EditorChoice("custom", tool_id)
        try:
            executable = custom_editors.checked_path(tool_id, document, tool.exe, "executable")
            if self._platform() == "linux" and executable.suffix.lower() == ".exe":
                self._wine_ready(tool_id, executable, loaded, custom=True)
        except (ToolNotFound, wine.WineError) as error:
            return _missing(choice, tool.name, error)
        return EditorOption(
            choice, tool.name, "available", "Executable found; loading is unverified.", ""
        )

    def _wine_ready(
        self, tool_id: str, executable: Path, loaded: settings.UserSettings, *, custom: bool
    ) -> None:
        launcher = loaded.configured().get("wine")
        prefix = loaded.wine_prefixes().get(tool_id)
        if custom and (launcher is None or prefix is None):
            raise ToolNotFound(
                "Custom Wine editor",
                hint="Choose both a Wine executable and prefix, or a native program.",
            )
        if prefix is None:
            recipe = editors.PREFIX_RECIPES.get(tool_id, "Create a prefix with wineboot.")
            raise wine.WineError(
                "This editor needs a Wine prefix on Linux.",
                hint=f"Choose a Wine prefix folder. {recipe}",
            )
        if launcher is None:
            location = self._discover(TOOL_BY_ID["wine"])
            if location is None:
                raise ToolNotFound(
                    "Wine", hint="Install Wine or choose its executable in settings."
                )
            launcher = location.path
        wine.validate_runtime(executable, wine=launcher, prefix=prefix)

    def _builtin(self, tool_id: str, document: Path, loaded: settings.UserSettings) -> EditorOption:
        spec = TOOL_BY_ID[tool_id]
        choice = EditorChoice("builtin", tool_id)
        try:
            editors.check_document(tool_id, document)
        except editors.EditorError as error:
            if error.__cause__ is not None:
                raise
            return EditorOption(
                choice, spec.name, "ineligible", error.user_message, error.hint or ""
            )
        try:
            self._builtin_ready(tool_id, loaded)
        except (ToolNotFound, wine.WineError) as error:
            return _missing(choice, spec.name, error)
        return EditorOption(
            choice, spec.name, "available", "Executable found; loading is unverified.", ""
        )

    def _builtin_ready(self, tool_id: str, loaded: settings.UserSettings) -> None:
        spec = TOOL_BY_ID[tool_id]
        configured = loaded.configured().get(tool_id)
        if configured is not None:
            custom_editors.checked_path(tool_id, configured, configured, "executable")
        location = self._discover(spec, configured=configured, include_dev=True)
        if location is None:
            raise ToolNotFound(spec.name, hint=f"Install {spec.name} from {spec.download_page}.")
        if location.launcher == "flatpak":
            raise ToolNotFound(
                spec.name,
                hint="Flatpak editors cannot be launched yet; choose a directly installed one.",
            )
        if location.launcher == "wine":
            if tool_id == "blender":
                raise ToolNotFound(
                    spec.name,
                    hint="Use the Linux build of Blender; Blender in Wine is unsupported.",
                )
            self._wine_ready(tool_id, location.path, loaded, custom=False)


def _missing(
    choice: EditorChoice, label: str, error: ToolNotFound | wine.WineError
) -> EditorOption:
    if error.__cause__ is not None and not isinstance(error.__cause__, FileNotFoundError):
        raise error
    return EditorOption(choice, label, "missing", error.user_message, error.hint or "")
