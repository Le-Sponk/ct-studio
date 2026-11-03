"""The assemble step: pack ``.ctstudio/stage/`` into ``build/<slot>.szs`` (P4-T05a).

``wszst create`` writes the archive with the profile's compression into a fresh temporary
folder beside the outputs (the same disk, so the final move is a rename). ``wszst list``
must then show every staged file inside: Wiimm leaves out names starting with a dot
(measured on 2.42a), so those are not expected. Only then are ``build/<slot>.szs`` and, when
``make_d_variant`` is on, the identical ``build/<slot>_d.szs`` replaced, so a failed build
keeps the last good track. The temporary folder always goes.

Auto-add is not passed here; P4-T05b adds it with the library check and the missing-object
warning, because wszst builds silently without objects it cannot find.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from ctstudio.core.build.node import BuildContext, Node, NodeResult, Profile, StepFailed
from ctstudio.core.components.state import GENERATED_DIR
from ctstudio.core.project.manifest import Compression, Manifest
from ctstudio.core.tools.wiimm import create_szs, list_files
from ctstudio.core.validation.issues import Issue

BUILD_DIR = "build"


def assemble_step(root: Path, manifest: Manifest, profile: Profile) -> Node:
    stage = root / GENERATED_DIR
    slot = manifest.project.slot
    settings = manifest.build
    compression = settings.test_compression if profile == "test" else settings.release_compression
    szs = root / BUILD_DIR / f"{slot}.szs"
    outputs = (szs, szs.with_name(f"{slot}_d.szs")) if settings.make_d_variant else (szs,)

    def run(ctx: BuildContext) -> NodeResult:
        staged = _staged(stage, szs)
        szs.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(dir=szs.parent, prefix=f".{slot}."))
        try:
            made = _create(ctx, stage, work / szs.name, compression, staged)
            _publish(made, outputs)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        extra = ", and the _d copy" if len(outputs) > 1 else ""
        ctx.log(f"{szs.name}: {len(staged)} files ({compression} compression){extra}")
        return NodeResult()

    params = {"slot": slot, "compression": compression, "d_variant": settings.make_d_variant}
    return Node("assemble", (stage,), outputs, params, ("wszst",), frozenset(), 1, run)


def _staged(stage: Path, szs: Path) -> set[str]:
    """Every file wszst will pack, as ``a/b.ext``; it skips names starting with a dot."""
    files = (
        (p.relative_to(stage) for p in stage.rglob("*") if p.is_file()) if stage.is_dir() else ()
    )
    staged = {f.as_posix() for f in files if not any(part.startswith(".") for part in f.parts)}
    if not staged:
        raise _failed(
            "ASSEMBLE_NOTHING_STAGED",
            f"There is nothing to put into {szs.name} yet.",
            "Choose the track's files on the dashboard, then build again.",
            None,
            "assemble",
        )
    return staged


def _create(
    ctx: BuildContext, stage: Path, dest: Path, compression: Compression, staged: set[str]
) -> Path:
    exe = _executable(ctx)
    create_szs(stage, dest, compression=compression, executable=exe, cancel=ctx.cancel)
    missing = sorted(staged - set(list_files(dest, executable=exe, cancel=ctx.cancel)))
    if missing:
        count = f"{len(missing)} staged file{'s' if len(missing) > 1 else ''}"
        raise _failed(
            "ASSEMBLE_FILES_MISSING",
            f"{dest.name} was made without {count}: {', '.join(missing)}.",
            "Report this with the build log: Wiimm's tool left out a file it was given.",
            ctx.root / BUILD_DIR / dest.name,
            "wszst list",
        )
    return dest


def _publish(made: Path, outputs: tuple[Path, ...]) -> None:
    """Copy ``made`` beside each output, then rename over it (both on the build folder's disk)."""
    for output in outputs:
        try:
            ready = made.with_name(f"{made.name}.{output.name}")
            shutil.copyfile(made, ready)
            os.replace(ready, output)
        except OSError as exc:
            shown = f"{BUILD_DIR}/{output.name}"
            raise _failed(
                "ASSEMBLE_REPLACE_FAILED",
                f"Could not replace {shown}: {exc.strerror or exc}.",
                "Close Dolphin or any program using the track file, then build again.",
                output,
                "assemble",
            ) from exc


def _executable(ctx: BuildContext) -> Path | None:
    location = ctx.tools.get("wszst")
    return location.path if location else None


def _failed(code: str, message: str, hint: str, file: Path | None, source: str) -> StepFailed:
    return StepFailed(Issue("error", "assemble", code, message, hint, source, file))
