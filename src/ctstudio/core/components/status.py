"""Each track part's status, fast enough to show live (P3-T04, ARCHITECTURE §4 and §8).

``evaluate(project, tools)`` gives every part in dashboard order a ``ComponentStatus``:
a ``State`` plus short plain reasons. Parts CT Studio makes are compared with what
``.ctstudio/state.json`` says was made last (``state.py``):

- never made, or an output deleted → Missing
- an output changed or added outside CT Studio → EditedExternally (never silently rebuilt)
- its settings or an input changed since → Stale
- needs making but a tool or the .blend is missing → Error
- otherwise → Ready

A supplied (manual) file is Manual when it exists and has the right type (``formats.magic``),
Missing when not chosen or not found, and Error when it is the wrong type. Objects and track
info are Ready, or Warning when something is worth a look.

Only size+mtime is read for unchanged files; a touched file is hashed once (cached).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS, ComponentSpec
from ctstudio.core.components.state import (
    GENERATED_DIR,
    ComponentRecord,
    ProjectState,
    input_path,
    load_state,
)
from ctstudio.core.formats.magic import FileKind, identify
from ctstudio.core.project import manifest_io
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.tools.registry import TOOL_BY_ID

POSTEFFECT_KINDS: Mapping[str, FileKind] = {
    ".bblm": FileKind.BBLM,
    ".bdof": FileKind.BDOF,
    ".blight": FileKind.BLIGHT,
    ".blmap": FileKind.BLMAP,
}  # .bfg (fog) has no magic, so any .bfg is accepted
_NOT_FOUND = "which was not found (see the Tools page)"


class State(StrEnum):
    MISSING = "missing"
    STALE = "stale"
    READY = "ready"
    WARNING = "warning"
    ERROR = "error"
    MANUAL = "manual"
    EDITED_EXTERNALLY = "edited_externally"


@dataclass(frozen=True)
class ComponentStatus:
    state: State
    reasons: tuple[str, ...] = ()


class ProjectLike(Protocol):
    @property
    def root(self) -> Path: ...

    @property
    def manifest(self) -> Manifest: ...


def evaluate(
    project: ProjectLike, tools: Collection[str], state: ProjectState | None = None
) -> dict[str, ComponentStatus]:
    """Every part's status. ``tools``: ids of the tools found; ``state``: read if not given."""
    known = load_state(project.root) if state is None else state
    return {spec.id: _one(spec, project, tools, known) for spec in COMPONENTS}


def settings_key(manifest: Manifest, component: str) -> str:
    """A digest of the settings a made part depends on (not which manual file is chosen)."""
    spec = COMPONENT_BY_ID[component]
    if not spec.outputs:
        raise KeyError(component)
    table = manifest_io.as_data(getattr(manifest.components, component))
    table.pop("file", None)
    used: dict[str, object] = {"component": table}
    if "blender" in spec.tools_for(str(table["mode"])):
        used["blend"] = manifest.project.blend
        used["blender"] = manifest_io.as_data(manifest.blender)
    text = json.dumps(used, sort_keys=True, default=str)
    return hashlib.blake2b(text.encode("utf-8"), digest_size=32).hexdigest()


def _one(
    spec: ComponentSpec, project: ProjectLike, tools: Collection[str], state: ProjectState
) -> ComponentStatus:
    if spec.id == "objects":
        return _objects(project.manifest, tools)
    if spec.id == "track_info":
        return _track_info(project.manifest)
    table = getattr(project.manifest.components, spec.id)
    if table.mode == "manual":
        return _manual(spec, project.root, table.file)
    status = _compare(spec, project, state.components.get(spec.id))
    if status.state not in (State.MISSING, State.STALE):
        return status
    blockers = _blockers(spec, project, table.mode, tools)
    return ComponentStatus(State.ERROR, status.reasons + blockers) if blockers else status


def _compare(
    spec: ComponentSpec, project: ProjectLike, made: ComponentRecord | None
) -> ComponentStatus:
    name = spec.outputs[0]
    if made is None:
        return ComponentStatus(State.MISSING, (f"{name} has not been made yet",))
    stage = project.root / GENERATED_DIR
    edited, gone = _output_changes(spec, stage, made)
    stale = _stale(spec, project, made)
    if edited:
        return ComponentStatus(State.EDITED_EXTERNALLY, (*edited, *stale))
    if gone:
        return ComponentStatus(State.MISSING, gone)
    return ComponentStatus(State.STALE, stale) if stale else ComponentStatus(State.READY)


def _output_changes(
    spec: ComponentSpec, stage: Path, made: ComponentRecord
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    edited: list[str] = []
    gone: list[str] = []
    for rel, file in made.outputs.items():
        change = file.compare(stage / rel)
        if change == "changed":
            edited.append(f"{rel} was changed outside CT Studio")
        elif change == "missing":
            gone.append(f"{rel} is gone; it will be made again")
    for folder in (out for out in spec.outputs if out.endswith("/")):
        for path in sorted((stage / folder).rglob("*")):
            rel = path.relative_to(stage).as_posix()
            if path.is_file() and rel not in made.outputs:
                edited.append(f"{rel} was added outside CT Studio")
    return tuple(edited), tuple(gone)


def _stale(spec: ComponentSpec, project: ProjectLike, made: ComponentRecord) -> tuple[str, ...]:
    name = spec.outputs[0]
    reasons: list[str] = []
    if made.settings != settings_key(project.manifest, spec.id):
        reasons.append(f"settings changed since {name} was made")
    for key, file in made.inputs.items():
        change = file.compare(input_path(project.root, key))
        if change == "changed":
            reasons.append(f"{Path(key).name} changed since {name} was made")
        elif change == "missing":
            reasons.append(f"{Path(key).name}, used to make {name}, is gone")
    return tuple(reasons)


def _blockers(
    spec: ComponentSpec, project: ProjectLike, mode: str, tools: Collection[str]
) -> tuple[str, ...]:
    """Why the part cannot be made right now."""
    needed = spec.tools_for(mode)
    missing = [f"needs {TOOL_BY_ID[t].name}, {_NOT_FOUND}" for t in needed if t not in tools]
    if "blender" in needed:
        blend = project.manifest.project.blend
        if blend is None:
            missing.append("no .blend file chosen for this project")
        elif not input_path(project.root, blend).is_file():
            missing.append(f"{blend} was not found")
    return tuple(missing)


def _manual(spec: ComponentSpec, root: Path, file: str | None) -> ComponentStatus:
    if file is None:
        return ComponentStatus(State.MISSING, ("no file chosen",))
    path = input_path(root, file)
    if not path.exists():
        return ComponentStatus(State.MISSING, (f"{file} was not found",))
    problem = (
        _folder_problem(path, file) if spec.kind is None else _file_problem(path, file, spec.kind)
    )
    if problem:
        return ComponentStatus(State.ERROR, (problem,))
    return ComponentStatus(State.MANUAL, (f"using {file}",))


def _wrong(shown: str, expected: str, found: str) -> str:
    return f"{shown} is the wrong type: expected {expected}, found {found}"


def _file_problem(path: Path, shown: str, kind: FileKind) -> str | None:
    if path.is_dir():
        return _wrong(shown, kind.label, "a folder")
    found = identify(path)
    if found is kind:
        return None
    return _wrong(shown, kind.label, found.label if found else "an unrecognised file")


def _folder_problem(path: Path, shown: str) -> str | None:
    """Post-effects: a folder whose files with a known magic must be what their name says."""
    if not path.is_dir():
        return _wrong(shown, "a folder", "a file")
    files = sorted(p for p in path.iterdir() if p.is_file())
    if not files:
        return f"{shown} is empty"
    for child in files:
        want = POSTEFFECT_KINDS.get(child.suffix.lower())
        if want is not None:
            problem = _file_problem(child, f"{shown.rstrip('/')}/{child.name}", want)
            if problem:
                return problem
    return None


def _objects(manifest: Manifest, tools: Collection[str]) -> ComponentStatus:
    if not manifest.build.auto_add:
        reason = "auto-add is off: objects the course data places must already be in the track"
        return ComponentStatus(State.WARNING, (reason,))
    if "wszst" not in tools:
        reason = f"needs {TOOL_BY_ID['wszst'].name} to add objects automatically, {_NOT_FOUND}"
        return ComponentStatus(State.WARNING, (reason,))
    return ComponentStatus(State.READY, ("added automatically while the track is assembled",))


def _track_info(manifest: Manifest) -> ComponentStatus:
    if not manifest.project.author.strip():
        return ComponentStatus(State.WARNING, ("no author set",))
    return ComponentStatus(State.READY, (f"replaces {manifest.project.slot}",))
