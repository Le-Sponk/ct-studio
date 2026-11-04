"""Blocking recent-project persistence; callers must run it off the UI thread."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import settings


@dataclass(frozen=True)
class RecentProject:
    """A remembered folder and whether it is currently unavailable."""

    root: Path
    missing: bool


@dataclass(frozen=True)
class RecentResult:
    """An immutable history snapshot, or an actionable settings problem."""

    entries: tuple[RecentProject, ...]
    problem: str | None = None


class RecentProjects:
    """Blocking service: the welcome-page worker owns all calls, including checks."""

    def __init__(self, settings_path: Path | None = None) -> None:
        self._settings_path = (
            settings_path if settings_path is not None else settings.default_path()
        )

    def check(self) -> RecentResult:
        """Read the history without changing settings."""
        return self._run("check")

    def remember(self, root: Path) -> RecentResult:
        """Remember a successfully opened or created project, newest first."""
        return self._run("remember", root)

    def remove(self, root: Path) -> RecentResult:
        """Forget a history entry; never change the project folder itself."""
        return self._run("remove", root)

    def _run(
        self, action: Literal["check", "remember", "remove"], root: Path | None = None
    ) -> RecentResult:
        try:
            return self._update(action, root)
        except settings.SettingsError as exc:
            if isinstance(exc.__cause__, OSError):
                raise
            return RecentResult((), str(exc))
        except (OSError, RuntimeError) as exc:
            raise ProjectError(
                "Could not read or update recent projects.",
                hint="Check folder permissions, available disk space and paths, then try again.",
                details=str(exc),
            ) from exc

    def _update(
        self, action: Literal["check", "remember", "remove"], root: Path | None
    ) -> RecentResult:
        chosen = settings.load(self._settings_path)
        roots = self._history(chosen.other.get("recent_projects", []))
        if root is not None:
            resolved = root.resolve()
            roots = [path for path in roots if path != resolved]
            if action == "remember":
                roots.insert(0, resolved)
        roots = roots[:10]
        result = RecentResult(tuple(RecentProject(path, not path.is_dir()) for path in roots))
        if action != "check":
            other = {**chosen.other, "recent_projects": [str(path) for path in roots]}
            settings.save(settings.UserSettings(chosen.tools, other), self._settings_path)
        return result

    def _history(self, values: object) -> list[Path]:
        if not isinstance(values, list) or any(
            not isinstance(value, str)
            or not value
            or "\x00" in value
            or not Path(value).is_absolute()
            for value in values
        ):
            raise settings.SettingsError(
                self._settings_path, '"recent_projects" must be a list of absolute folder paths'
            )
        return list(dict.fromkeys(Path(value).resolve() for value in cast("list[str]", values)))
