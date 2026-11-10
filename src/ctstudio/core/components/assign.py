"""Assign a file the user supplies to a track part (P5-T04a, ARCHITECTURE §6).

``assign_file`` checks everything before it touches anything: an editable project whose
ctstudio.toml is unchanged on disk, a part with a manual mode, and a source that exists, is
not CT Studio's own ``.ctstudio/`` folder (or holds it), does not overlap where it would be
copied, and is the right type (the check status and the build use). By default the file, or
the post-effects folder, is copied into ``files/<game name>``; ``reference=True`` records the
source's path instead (project-relative with ``/`` when inside the project) and copies nothing.

A copy is made beside its target and type-checked again before it is used. A different
existing copy is backed up into ``.ctstudio/backups/<UTC time>/files/…`` and kept aside until
ctstudio.toml is saved (with its own ``.bak``); if that save fails, the old copy is put back.
The caller publishes the returned manifest; this module never changes ``project.manifest``.
Blocking: run it on a worker thread.
"""

from __future__ import annotations

import filecmp
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import tomli_w

from ctstudio.core.build.backups import save_copies
from ctstudio.core.components.registry import COMPONENT_BY_ID, ComponentSpec
from ctstudio.core.components.status import POSTEFFECT_KINDS, type_problem
from ctstudio.core.errors import ProjectError
from ctstudio.core.fsutil import replace_with_backup
from ctstudio.core.project import manifest_io
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project

FILES_DIR = "files"
_MANAGED = ".ctstudio"
_POSTEFFECT_FILES = ", ".join([*POSTEFFECT_KINDS, ".bfg"])


@dataclass(frozen=True)
class Assigned:
    manifest: Manifest  # saved; the caller makes it the project's current manifest
    file: str  # the path written to [components.<part>] file
    backup: Path | None  # backup folder of the replaced copy, if one was replaced
    manifest_backup: Path | None  # the previous ctstudio.toml


def assign_file(project: Project, part: str, source: Path, *, reference: bool = False) -> Assigned:
    """Make ``part`` use ``source`` (manual mode); ProjectError, with nothing changed, if not."""
    spec = _editable(project, part)
    raw = _unchanged_manifest(project)
    root = project.root.resolve()
    chosen = _existing_source(root, source)
    target = root / FILES_DIR / spec.outputs[0].rstrip("/")
    text = target.relative_to(root).as_posix()
    if not reference and chosen != target:
        _refuse_overlap(chosen, target, text)
    if (problem := type_problem(spec, chosen, _shown(source))) is not None:
        raise ProjectError(f"{problem}.", hint=_type_hint(spec))
    if reference:
        text = chosen.relative_to(root).as_posix() if chosen.is_relative_to(root) else str(chosen)
        return _save(project, spec, raw, text, None)
    if chosen == target or (target.exists() and _same(chosen, target, text)):
        return _save(project, spec, raw, text, None)
    return _copy_in(project, spec, raw, chosen, target)


def _shown(path: Path) -> str:
    """A name for messages; a drive or filesystem root has no name, so show it whole."""
    return path.name or str(path)


def _editable(project: Project, part: str) -> ComponentSpec:
    if project.read_only:
        raise ProjectError(
            "The project is read-only, so no file was assigned.",
            hint=f"{project.read_only_reason or 'It is open elsewhere'}. Reopen it for editing.",
        )
    spec = COMPONENT_BY_ID.get(part)
    if spec is None or "manual" not in spec.modes or spec.manifest_table in (None, "project"):
        name = spec.name if spec is not None else repr(part)
        raise ProjectError(
            f"The {name} part cannot use a file you supply.",
            hint="Choose a part whose modes include manual.",
        )
    return spec


def _unchanged_manifest(project: Project) -> bytes:
    """ctstudio.toml's bytes, provided they still say what the open project says."""
    try:
        raw = project.manifest_path.read_bytes()
        same = manifest_io.load(project.manifest_path) == project.manifest
    except (OSError, ProjectError) as exc:
        raise _changed(str(exc)) from exc
    if not same:
        raise _changed(None)
    return raw


def _changed(details: str | None) -> ProjectError:
    return ProjectError(
        "ctstudio.toml changed since the project was opened.",
        hint="Reopen the project, then assign the file again.",
        details=details,
    )


def _existing_source(root: Path, source: Path) -> Path:
    try:
        chosen = source.resolve()
        found = chosen.exists()
    except (OSError, ValueError, RuntimeError) as exc:  # NUL in the path, a symlink loop
        raise ProjectError(
            f"{_shown(source)} cannot be used as a file path.",
            hint="Choose the file again with the file chooser.",
            details=str(exc),
        ) from exc
    if not found:
        raise ProjectError(f"{_shown(source)} was not found.", hint="Choose an existing file.")
    managed = (root / _MANAGED).resolve()
    if chosen.is_relative_to(managed) or managed.is_relative_to(chosen):
        where = "is inside" if chosen.is_relative_to(managed) else "contains"
        raise ProjectError(
            f"{_shown(source)} {where} the .ctstudio folder, which CT Studio manages.",
            hint="Choose a file or folder outside .ctstudio.",
        )
    return chosen


def _type_hint(spec: ComponentSpec) -> str:
    if spec.kind is None:
        return f"Choose a folder of post-effect files ({_POSTEFFECT_FILES})."
    return f"Choose a {spec.kind.label} for the {spec.name}."


def _refuse_overlap(chosen: Path, target: Path, text: str) -> None:
    if chosen.is_relative_to(target) or target.is_relative_to(chosen):
        raise ProjectError(
            f"{_shown(chosen)} overlaps {text}, where it would be copied.",
            hint=f"Choose a folder outside {text}, or use Reference in place.",
        )


def _same(a: Path, b: Path, text: str) -> bool:
    """Byte-identical file, or folders with the same names, kinds and file bytes throughout."""
    try:
        return _same_entry(a, b) and (not a.is_dir() or _same_folder(a, b))
    except OSError as exc:
        raise ProjectError(
            f"Could not read {_shown(a)} or {text}: {exc.strerror or exc}.",
            hint="Close programs using the files, then try again.",
            details=str(exc),
        ) from exc


def _same_entry(a: Path, b: Path) -> bool:
    if a.is_dir() or b.is_dir():
        return a.is_dir() and b.is_dir()
    return filecmp.cmp(a, b, shallow=False)


def _same_folder(a: Path, b: Path) -> bool:
    names = sorted(p.relative_to(a) for p in a.rglob("*"))
    if names != sorted(p.relative_to(b) for p in b.rglob("*")):
        return False
    return all(_same_entry(a / n, b / n) for n in names)


def _copy_in(
    project: Project, spec: ComponentSpec, raw: bytes, chosen: Path, target: Path
) -> Assigned:
    """Stage and re-check the copy, back up and set aside the old one, save, then commit."""
    root = project.root.resolve()
    text = target.relative_to(root).as_posix()
    staged = _staged_copy(chosen, target)
    holder = staged.parent  # a hidden temporary folder beside the target
    aside = holder / f"{target.name}.old"  # where the previous copy waits until the save
    done = False
    try:
        if (problem := type_problem(spec, staged, _shown(chosen))) is not None:
            raise ProjectError(f"{problem}.", hint=_type_hint(spec))
        backup = _backup(root, target, text) if target.exists() else None
        _swap_in(staged, target, aside)
        try:
            assigned = _save(project, spec, raw, text, backup)
        except BaseException as exc:  # also Ctrl+C: never leave a copy ctstudio.toml does not name
            undone = _undo(target, aside, text)
            if not isinstance(exc, ProjectError):
                raise
            raise ProjectError(exc.user_message, f"{undone} {exc.hint}", exc.details) from exc
        done = True
        return assigned
    finally:
        # Never delete a previous copy that could not be put back (it is named in the error).
        if done or not aside.exists():
            shutil.rmtree(holder, ignore_errors=True)


def _undo(target: Path, aside: Path, text: str) -> str:
    """Take the new copy out again and put the previous one back; say what happened."""
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        if aside.exists():
            aside.rename(target)
            return f"The previous {text} was put back."
    except OSError:
        kept = f" The previous copy is kept as {aside}." if aside.exists() else ""
        return f"The new copy at {text} could not be taken out again.{kept}"
    return "The copy was removed."


def _staged_copy(chosen: Path, target: Path) -> Path:
    try:  # e.g. files/ is a plain file, or the project folder cannot be written to
        target.parent.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(dir=target.parent, prefix=f".{target.name}."))
    except OSError as exc:
        raise _copy_error(chosen, exc) from exc
    copy = staged / target.name
    try:
        if chosen.is_dir():
            copy.mkdir()
            for path in sorted(chosen.rglob("*")):
                _copy_one(path, copy / path.relative_to(chosen))
        else:
            _copy_one(chosen, copy)
    except BaseException as exc:  # also Ctrl+C: no temporary folder is left in files/
        shutil.rmtree(staged, ignore_errors=True)
        if not isinstance(exc, OSError):
            raise
        raise _copy_error(chosen, exc) from exc
    return copy


def _copy_error(chosen: Path, exc: OSError) -> ProjectError:
    return ProjectError(
        f"Could not copy {_shown(chosen)} into the project: {exc.strerror or exc}.",
        hint="Close programs using the file and free some disk space, then try again.",
        details=str(exc),
    )


def _copy_one(path: Path, copy: Path) -> None:
    if path.is_dir():
        copy.mkdir(exist_ok=True)
        return
    with path.open("rb") as data, copy.open("wb") as out:
        shutil.copyfileobj(data, out)
    shutil.copystat(path, copy)


def _backup(root: Path, target: Path, text: str) -> Path:
    try:
        return save_copies(root, [target])
    except OSError as exc:
        raise ProjectError(
            f"Could not back up {text} before replacing it: {exc.strerror or exc}.",
            hint="Check that the project folder can be written to, then try again.",
            details=str(exc),
        ) from exc


def _swap_in(copy: Path, target: Path, aside: Path) -> None:
    """Move ``copy`` to ``target``, keeping any previous target at ``aside`` until the save."""
    try:
        if target.exists():
            target.rename(aside)
        copy.rename(target)
    except BaseException as exc:  # also Ctrl+C between the two moves
        hint = "Close programs using the file, then try again."
        try:
            if aside.exists() and not target.exists():
                aside.rename(target)
        except OSError:
            hint = f"The previous copy is kept as {aside}. {hint}"
        if not isinstance(exc, OSError):
            raise
        raise ProjectError(
            f"Could not put the copy in place of {target.name}: {exc.strerror or exc}.",
            hint=hint,
            details=str(exc),
        ) from exc


def _save(
    project: Project, spec: ComponentSpec, raw: bytes, text: str, backup: Path | None
) -> Assigned:
    table = cast(str, spec.manifest_table)  # _editable allows only parts with their own table
    parts = project.manifest.components
    chosen = replace(getattr(parts, table), mode="manual", file=text)
    manifest = replace(project.manifest, components=replace(parts, **{table: chosen}))
    data = tomli_w.dumps(manifest_io.as_data(manifest)).encode("utf-8")
    try:
        manifest_backup = replace_with_backup(project.manifest_path, data, expected=raw)
    except ProjectError as exc:
        raise ProjectError(
            "Could not save ctstudio.toml, so no file was assigned.",
            hint=exc.hint or "Check the project folder and try again.",
            details=f"{exc.user_message} {exc.details or ''}".strip(),
        ) from exc
    return Assigned(manifest, text, backup, manifest_backup)
