"""Lock as manual or Discard a part's output that was edited outside CT Studio (P5-T06b).

ARCHITECTURE §8: when a file CT Studio made under ``.ctstudio/stage/`` was changed by another
program (status EditedExternally), the user chooses what happens to it:

- ``lock_as_manual`` copies the edited output into ``files/<game name>`` and switches the part
  to manual mode, so every later build uses it as it is (the copy and ctstudio.toml save are
  ``assign.copy_into_files``: a different copy already in ``files/`` is backed up first).
- ``discard_edit`` moves the edited output, in one rename, into a new
  ``.ctstudio/backups/<UTC time>/`` folder under its project-relative path, so the part
  reports Missing and the next build makes it again. Nothing is deleted.

Both refuse with a ``ProjectError``, changing nothing, unless the project is editable, the
part is one CT Studio makes and is set to be made, ctstudio.toml is unchanged on disk, and the
output really was changed or added to since it was made. Blocking: run on a worker thread,
never while a build runs.
"""

from __future__ import annotations

from pathlib import Path

from ctstudio.core.build.backups import BACKUP_DIR, new_backup_folder
from ctstudio.core.components.assign import Assigned, copy_into_files, unchanged_manifest
from ctstudio.core.components.registry import COMPONENT_BY_ID, ComponentSpec
from ctstudio.core.components.state import GENERATED_DIR, load_state
from ctstudio.core.components.status import output_changes, type_problem
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.project import Project

LOCKED = "locked as manual"
DISCARDED = "discarded"
_REFRESH = "Press Refresh statuses to see each part's current state."


def edited_files(project: Project, part: str) -> tuple[str, ...]:
    """The part's outputs changed or added outside CT Studio, by path inside the stage folder."""
    spec = COMPONENT_BY_ID.get(part)
    made = load_state(project.root).components.get(part)
    if spec is None or made is None:
        return ()
    changes = output_changes(spec, project.root / GENERATED_DIR, made)
    return tuple(sorted(rel for rel, change in changes.items() if change != "missing"))


def lock_as_manual(project: Project, part: str) -> Assigned:
    """Keep the edited output as the part's own file in ``files/`` (manual mode).

    The caller publishes the returned manifest.
    """
    spec, raw = _checked(project, part, LOCKED)
    name = spec.outputs[0].rstrip("/")
    output = (project.root / GENERATED_DIR / name).resolve()
    not_done = f"the {spec.name} was not {LOCKED}"
    try:
        problem = type_problem(spec, output, name)
    except ProjectError as exc:  # the editing program may still hold the file
        raise ProjectError(
            f"{exc.user_message.removesuffix('.')}, so {not_done}.",
            hint="Close programs using the file, then try again.",
            details=exc.details,
        ) from exc
    if problem is not None:
        raise ProjectError(
            f"{problem}, so {not_done}.",
            hint="Discard the edit, or fix the file in the program that changed it.",
        )
    return copy_into_files(project, spec, raw, output, not_done)


def discard_edit(project: Project, part: str) -> Path:
    """Move the edited output into a new backup folder, which is returned."""
    spec, _raw = _checked(project, part, DISCARDED)
    root = project.root
    name = spec.outputs[0].rstrip("/")
    backups = root / BACKUP_DIR
    backups_existed = backups.exists()
    folder: Path | None = None
    try:
        folder = new_backup_folder(root)
        kept = folder / GENERATED_DIR / name
        kept.parent.mkdir(parents=True)
        move(root / GENERATED_DIR / name, kept)
    except OSError as exc:
        # The move is one rename, so a failed one left the edit where it was. Remove the
        # folders this discard made, but only while they are empty: never anything else.
        if folder is not None:
            _remove_empty(_made_folders(folder))
        if not backups_existed:
            _remove_empty([backups])
        raise ProjectError(
            f"Could not move {name} into the backups: {exc.strerror or exc}. "
            f"The {spec.name} was not {DISCARDED}.",
            hint="Close programs using the file, then try again. Your edit was not touched.",
            details=str(exc),
        ) from exc
    return folder


def move(source: Path, target: Path) -> None:
    """One rename on the same drive: the whole file or folder moves, or nothing does."""
    source.rename(target)


def _made_folders(folder: Path) -> list[Path]:
    """The folders a discard makes inside its backup folder, deepest first, then the folder."""
    return [folder / GENERATED_DIR, (folder / GENERATED_DIR).parent, folder]


def _remove_empty(folders: list[Path]) -> None:
    for each in folders:
        try:
            each.rmdir()  # only an empty folder can be removed: nothing else is ever deleted
        except OSError:
            continue  # not empty, or never made because the failure came first


def _checked(project: Project, part: str, done: str) -> tuple[ComponentSpec, bytes]:
    """The part, and ctstudio.toml's bytes, when the action may go ahead; else ProjectError."""
    spec = _made_part(part, done)
    if project.read_only:
        reason = project.read_only_reason or "it is open elsewhere"
        raise ProjectError(
            f"The project is read-only, so the {spec.name} was not {done}.",
            hint=f"{reason[:1].upper()}{reason[1:]}. Reopen it for editing.",
        )
    if getattr(project.manifest.components, spec.id).mode == "manual":
        raise ProjectError(f"The {spec.name} uses your own file, so it was not {done}.", _REFRESH)
    raw = unchanged_manifest(project, "try again")
    try:
        edited = edited_files(project, spec.id)
    except ProjectError as exc:  # state.json could not be read
        raise ProjectError(
            f"{exc.user_message.removesuffix('.')}, so the {spec.name} was not {done}.",
            hint=exc.hint or _REFRESH,
            details=exc.details,
        ) from exc
    if not edited:
        raise ProjectError(
            f"The {spec.name} was not changed outside CT Studio, so it was not {done}.",
            hint=_REFRESH,
        )
    return spec, raw


def _made_part(part: str, done: str) -> ComponentSpec:
    spec = COMPONENT_BY_ID.get(part)
    if spec is None or not spec.outputs or set(spec.modes) == {"manual"}:
        name = f"The {spec.name}" if spec is not None else repr(part)
        raise ProjectError(
            f"{name} has no file made by CT Studio, so it was not {done}.",
            hint="Only a part CT Studio makes can be edited outside it.",
        )
    return spec
