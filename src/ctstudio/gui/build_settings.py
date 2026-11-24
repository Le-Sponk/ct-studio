"""The Build page's settings on disk; blocking, call from a worker.

``BuildSettingsService`` (P5-T08b) reads and saves the open project's build settings;
``BuildJobsService`` (P5-T08c) the machine setting for how many build steps may run at once.

The four choices the page shows (test and release compression, the ``_d`` copy, auto-add)
are saved into the project file's ``[build]`` table through Project details' stale-input
checks (``persist_snapshot``): the open project must be writable, and its live manifest and
the file's bytes must still be what was loaded. Everything else in the file is kept,
including keys this version does not know; comments are not (ADR-020). The service never
publishes the manifest: the page does that on the GUI thread after joining the worker.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import settings
from ctstudio.core.project.manifest import COMPRESSIONS, BuildSettings, Compression
from ctstudio.core.project.project import Project
from ctstudio.gui.project_details import DetailsSnapshot, ProjectDetailsService, persist_snapshot


@dataclass(frozen=True)
class BuildChoices:
    """What the Build page edits; the rest of ``[build]`` is left as it is."""

    test_compression: Compression
    release_compression: Compression
    make_d_variant: bool
    auto_add: bool

    @classmethod
    def of(cls, settings: BuildSettings) -> BuildChoices:
        return cls(
            settings.test_compression,
            settings.release_compression,
            settings.make_d_variant,
            settings.auto_add,
        )


class BuildSettingsService:
    """Blocking reads and saves; the caller owns the worker and the project's lifetime."""

    def load(self, project: Project) -> DetailsSnapshot:
        """The project file as Project details reads it: exact bytes, nothing written."""
        return ProjectDetailsService().load(project)

    def save(
        self, project: Project, snapshot: DetailsSnapshot, choices: BuildChoices
    ) -> DetailsSnapshot:
        """Save ``choices`` over ``snapshot``; the same choices write nothing."""
        for compression in (choices.test_compression, choices.release_compression):
            if compression not in COMPRESSIONS:
                raise ProjectError(
                    f"{compression!r} is not a compression CT Studio knows.",
                    hint=f"Choose one of: {', '.join(COMPRESSIONS)}.",
                )
        build = replace(
            snapshot.manifest.build,
            test_compression=choices.test_compression,
            release_compression=choices.release_compression,
            make_d_variant=choices.make_d_variant,
            auto_add=choices.auto_add,
        )
        try:
            manifest = replace(snapshot.manifest, build=build)
            return persist_snapshot(project, snapshot, manifest, what="build settings")
        except (OSError, ValueError, RuntimeError) as exc:
            raise ProjectError(
                "Could not save the build settings.",
                hint="Check the project folder's permissions and free disk space, then try again.",
                details=str(exc),
            ) from exc


class BuildJobsService:
    """How many build steps may run at once on this computer, in ``settings.json``.

    Each call reads the file fresh; a damaged or newer file raises ``SettingsError`` and is
    never written. Saving what the file already says writes nothing (no backup).
    """

    def __init__(self, *, settings_path: Path | None = None) -> None:
        self._settings_path = settings_path

    def load(self) -> int | None:
        """The saved number; None for automatic."""
        return settings.load(self._settings_path).build_jobs()

    def save(self, jobs: int | None) -> int | None:
        """Save ``jobs`` (None: automatic) and return it."""
        current = settings.load(self._settings_path)
        if current.build_jobs() != jobs:
            settings.save(current.with_build_jobs(jobs), self._settings_path)
        return jobs
