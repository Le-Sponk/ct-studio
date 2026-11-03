"""Objects for the assemble step: auto-add only from a usable library, and name what is missing.

``wkmpt`` reads the staged KMP's object table and Wiimm's own object -> file database
(P4-T05b, measured on 2.42a). An object's files must be in the stage or in the auto-add
library; wszst adds nothing and says nothing when they are missing, so each such object
becomes one warning naming it and its files. An id Wiimm does not know is a warning too.
The library is checked with ``wszst autoadd -vv`` on every assemble (a snapshot): an
unusable one is a warning and the track is built without it, never with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ctstudio.core.build.node import BuildContext
from ctstudio.core.tools.wiimm import AutoAddLibrary
from ctstudio.core.tools.wiimm_autoadd import autoadd_verify
from ctstudio.core.tools.wiimm_objects import KmpObject, kmp_objects, object_files
from ctstudio.core.validation.issues import Issue

KMP = "course.kmp"


@dataclass(frozen=True)
class ObjectCheck:
    library: AutoAddLibrary | None  # pass to wszst create only when not None
    issues: tuple[Issue, ...]


def check_objects(ctx: BuildContext, stage: Path, library: Path | None) -> ObjectCheck:
    """The usable library (or None) and a warning per object the track will lack."""
    issues: list[Issue] = []
    usable = _usable(ctx, library, issues) if library is not None else None
    if not (stage / KMP).is_file():
        return ObjectCheck(usable, tuple(issues))
    there = usable.names if usable else frozenset[str]()
    issues.extend(_lacking(ctx, stage, there, _where(ctx, library, usable)))
    return ObjectCheck(usable, tuple(issues))


def _lacking(
    ctx: BuildContext, stage: Path, there: frozenset[str], where: tuple[str, str]
) -> list[Issue]:
    """A warning per placed object whose files are in neither the stage nor ``there``."""
    wkmpt = _exe(ctx, "wkmpt")
    placed = kmp_objects(stage / KMP, executable=wkmpt, cancel=ctx.cancel)
    needs = object_files((o.id for o in placed), executable=wkmpt, cancel=ctx.cancel)
    issues: list[Issue] = []
    for obj in placed:
        files = needs.get(obj.id)
        if files is None:
            issues.append(_unknown(obj))
            continue
        missing = [f for f in files if f not in there and not (stage / f).is_file()]
        if missing:
            issues.append(_missing(obj, missing, where))
    return issues


def _usable(ctx: BuildContext, library: Path, issues: list[Issue]) -> AutoAddLibrary | None:
    checked = autoadd_verify(library, executable=_exe(ctx, "wszst"), cancel=ctx.cancel)
    reason = checked.unusable_reason()
    if reason is None:
        return checked
    issues.append(
        _warning(
            "OBJECTS_LIBRARY_UNUSABLE",
            f"The auto-add library is not used, so no objects are added from it: {reason}.",
            "Build the library again from your own game disc, then build the track again.",
            library,
        )
    )
    return None


def _where(
    ctx: BuildContext, library: Path | None, usable: AutoAddLibrary | None
) -> tuple[str, str]:
    """Where the files were looked for, and what the user can do about it."""
    if usable is not None:
        return (
            "the track or the auto-add library",
            "Add the files to the track: your auto-add library does not have them.",
        )
    if not ctx.manifest.build.auto_add:
        return (
            "the track (auto-add is off)",
            "Turn auto-add on in the project's build settings, or add the files to the track.",
        )
    if library is None:
        return (
            "the track, and no auto-add library is set up",
            "Set up the auto-add library from your own game disc, or add the files to the track.",
        )
    return (
        "the track, and the auto-add library cannot be used",
        "Fix the auto-add library (see the other warning), then build again.",
    )


def _unknown(obj: KmpObject) -> Issue:
    return _warning(
        "OBJECTS_UNKNOWN",
        f"The course places object {obj.id:#x}, which is not in Wiimm's object list.",
        "Check that object's id in your KMP editor: the game can freeze on an unknown object.",
        None,
    )


def _missing(obj: KmpObject, missing: list[str], where: tuple[str, str]) -> Issue:
    times = f", placed {obj.count} times" if obj.count > 1 else ""
    verb = "is" if len(missing) == 1 else "are"
    return _warning(
        "OBJECTS_FILES_MISSING",
        f"{obj.name} (object {obj.id:#x}{times}) needs {', '.join(missing)}, which {verb} not"
        f" in {where[0]}.",
        where[1],
        None,
    )


def _warning(code: str, message: str, hint: str, file: Path | None) -> Issue:
    return Issue("warning", "objects", code, message, hint, "wkmpt", file)


def _exe(ctx: BuildContext, tool: str) -> Path | None:
    location = ctx.tools.get(tool)
    return location.path if location else None
