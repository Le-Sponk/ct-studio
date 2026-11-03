"""Manual mode: copy the file the user supplies into ``.ctstudio/stage/`` (P4-T04).

``stage_part`` gives one step, ``stage:<part>``, that checks the chosen file with the same
type check the dashboard uses (``components.status.type_problem``) and copies it under the
name the game expects: ``course.kcl``, or post-effects as a whole folder. The copy is made
under a temporary name and then swapped in, so a failed copy leaves the old one whole and
nothing half-written. The cache skips the step while the file is unchanged.

Every problem the user can fix fails the step with one ``Issue``: no file chosen, not
found, the wrong type, inside ``.ctstudio/`` (CT Studio's own files, which a build may
replace), or a copy that failed.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from ctstudio.core.build.graph import MakePart
from ctstudio.core.build.node import BuildContext, Node, NodeResult, StepFailed
from ctstudio.core.components.registry import ComponentSpec
from ctstudio.core.components.state import GENERATED_DIR, input_path
from ctstudio.core.components.status import POSTEFFECT_KINDS, type_problem
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.validation.issues import Issue

_MANAGED = ".ctstudio"
_POSTEFFECT_FILES = ", ".join([*POSTEFFECT_KINDS, ".bfg"])


def manual_parts(root: Path, manifest: Manifest) -> MakePart:
    """For ``graph.from_manifest``: a stage step for each part in manual mode."""

    def make(spec: ComponentSpec, mode: str) -> list[Node] | None:
        return [stage_part(root, manifest, spec)] if mode == "manual" else None

    return make


def stage_part(root: Path, manifest: Manifest, spec: ComponentSpec) -> Node:
    file: str | None = getattr(manifest.components, spec.id).file
    source = None if file is None else input_path(root, file)
    target = root / GENERATED_DIR / spec.outputs[0]  # pathlib drops a folder's trailing /
    managed = source is not None and _overlaps(source.resolve(), (root / _MANAGED).resolve())

    def run(_ctx: BuildContext) -> NodeResult:
        chosen, path = _check(spec, file, source, managed=managed)
        _copy(spec, chosen, path, target)
        return NodeResult()

    # No params: the key already holds the file's content, and another file with the same
    # content stages the same bytes. A failed step is never cached, so no-file is not either.
    inputs = () if source is None or managed else (source,)
    return Node(
        f"stage:{spec.id}", inputs, (target,), {}, (), frozenset(), 1, run, component=spec.id
    )


def _check(
    spec: ComponentSpec, file: str | None, source: Path | None, *, managed: bool
) -> tuple[str, Path]:
    """The chosen file and its path when it can be staged; else raises ``StepFailed``."""
    if file is None or source is None:
        raise _failed(
            spec,
            "STAGE_NO_FILE",
            f"No file is chosen for the {spec.name}.",
            f'Choose one in ctstudio.toml: [components.{spec.id}] file = "...".',
            None,
        )
    if managed:
        raise _failed(
            spec,
            "STAGE_INSIDE_CTSTUDIO",
            f"{file} is inside the .ctstudio folder, which CT Studio manages.",
            "Copy it somewhere else in the project, choose that copy, then build again.",
            source,
        )
    if not source.exists():
        hint = "Put the file back, or choose another in ctstudio.toml."
        raise _failed(spec, "STAGE_NOT_FOUND", f"{file} was not found.", hint, source)
    problem = type_problem(spec, source, file)
    if problem:
        raise _failed(spec, "STAGE_WRONG_TYPE", problem, _type_hint(spec), source)
    return file, source


def _type_hint(spec: ComponentSpec) -> str:
    if spec.kind is None:
        return f"Choose a folder of post-effect files ({_POSTEFFECT_FILES})."
    return f"Choose a {spec.kind.label} for the {spec.name}."


def _copy(spec: ComponentSpec, file: str, source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if source.is_dir():
            _copy_folder(source, target)
        else:
            _copy_file(source, target)
    except OSError as exc:
        raise _failed(
            spec,
            "STAGE_COPY_FAILED",
            f"Could not copy {file}: {exc.strerror or exc}.",
            "Close programs using the file and free some disk space, then build again.",
            source,
        ) from exc


def _copy_file(source: Path, target: Path) -> None:
    with tempfile.NamedTemporaryFile(
        dir=target.parent, prefix=f".{target.name}.", delete=False
    ) as temp:
        staged = Path(temp.name)
        try:
            with source.open("rb") as data:
                shutil.copyfileobj(data, temp)
        except OSError:
            temp.close()
            staged.unlink(missing_ok=True)
            raise
    try:
        os.replace(staged, target)
    except OSError:
        staged.unlink(missing_ok=True)
        raise


def _copy_folder(source: Path, target: Path) -> None:
    """Copy the whole folder beside ``target``, then swap it in (no leftover old files)."""
    staged = Path(tempfile.mkdtemp(dir=target.parent, prefix=f".{target.name}."))
    old = staged.with_name(staged.name + ".old")
    try:
        for path in sorted(source.rglob("*")):
            copy = staged / path.relative_to(source)
            if path.is_dir():
                copy.mkdir(exist_ok=True)
            else:
                shutil.copy2(path, copy)
        if target.exists():
            target.rename(old)
        staged.rename(target)
    except OSError:
        if old.exists() and not target.exists():
            old.rename(target)
        shutil.rmtree(staged, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)


def _overlaps(a: Path, b: Path) -> bool:
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def _failed(
    spec: ComponentSpec, code: str, message: str, hint: str, file: Path | None
) -> StepFailed:
    return StepFailed(Issue("error", spec.id, code, message, hint, "stage", file, spec.wiki))
