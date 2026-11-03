"""The assemble step: pack ``.ctstudio/stage/`` into ``build/<slot>.szs`` (P4-T05a).

``wszst create`` writes the archive with the profile's compression into a fresh temporary
folder beside the outputs (the same disk, so the final move is a rename). ``wszst list``
must then show every staged file inside: Wiimm leaves out names starting with a dot
(measured on 2.42a), so those are not expected. Only then are ``build/<slot>.szs`` and, when
``make_d_variant`` is on, the identical ``build/<slot>_d.szs`` replaced, so a failed build
keeps the last good track. The temporary folder always goes.

Objects (P4-T05b, ``build/objects.py``): ``--auto-add`` is passed only when the project has
auto-add on and the computer's library passed Wiimm's check this build; every object the
track will lack is one warning, because wszst builds silently without them.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from ctstudio.core.build.node import BuildContext, Node, NodeResult, Profile, StepFailed
from ctstudio.core.build.objects import check_objects
from ctstudio.core.components.state import GENERATED_DIR
from ctstudio.core.project.manifest import Compression, Manifest
from ctstudio.core.tools.wiimm import AutoAddLibrary, WiimmError, create_szs, list_files
from ctstudio.core.validation.issues import Issue

BUILD_DIR = "build"


def assemble_step(
    root: Path, manifest: Manifest, profile: Profile, library: Path | None = None
) -> Node:
    """``library``: the computer's auto-add folder (user settings), used only with auto-add on."""
    stage = root / GENERATED_DIR
    library = library if manifest.build.auto_add else None
    slot = manifest.project.slot
    settings = manifest.build
    compression = settings.test_compression if profile == "test" else settings.release_compression
    szs = root / BUILD_DIR / f"{slot}.szs"
    outputs = (szs, szs.with_name(f"{slot}_d.szs")) if settings.make_d_variant else (szs,)

    def run(ctx: BuildContext) -> NodeResult:
        staged = _staged(stage, szs)
        objects = check_objects(ctx, stage, library)
        szs.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(dir=szs.parent, prefix=f".{slot}."))
        try:
            made = _create(ctx, stage, work / szs.name, (compression, objects.library), staged)
            _publish(made, outputs)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        extra = ", and the _d copy" if len(outputs) > 1 else ""
        added = ", with auto-add" if objects.library else ""
        ctx.log(f"{szs.name}: {len(staged)} files ({compression} compression{added}){extra}")
        return NodeResult(objects.issues)

    params = {
        "slot": slot,
        "compression": compression,
        "d_variant": settings.make_d_variant,
        "library": None if library is None else str(library),
    }
    inputs = (stage,) if library is None else (stage, library)
    tools = ("wszst", "wkmpt")
    return Node("assemble", inputs, outputs, params, tools, frozenset(), 1, run)


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
    ctx: BuildContext,
    stage: Path,
    dest: Path,
    how: tuple[Compression, AutoAddLibrary | None],
    staged: set[str],
) -> Path:
    exe = _executable(ctx)
    compression, library = how
    try:
        create_szs(
            stage,
            dest,
            compression=compression,
            executable=exe,
            cancel=ctx.cancel,
            auto_add=library,
        )
    except WiimmError as exc:
        if exc.error_code is not None:  # Wiimm said what was wrong: its own words are clearer
            raise
        (stage.parent / "wszst.exe.stackdump").unlink(missing_ok=True)  # left by a crash
        raise _crashed(ctx.root / BUILD_DIR / dest.name, exc) from exc
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


def _crashed(szs: Path, exc: WiimmError) -> StepFailed:
    issue = Issue(
        "error",
        "assemble",
        "ASSEMBLE_TOOL_CRASHED",
        "Wiimm's tool stopped unexpectedly while packing the track: "
        "one of the track's files is probably damaged.",
        "Export or choose the BRRES files again, then build again. "
        "The build log has the tool's own output.",
        "wszst create",
        szs,
    )
    return StepFailed(issue, details=exc.details)


def _executable(ctx: BuildContext) -> Path | None:
    location = ctx.tools.get("wszst")
    return location.path if location else None


def _failed(code: str, message: str, hint: str, file: Path | None, source: str) -> StepFailed:
    return StepFailed(Issue("error", "assemble", code, message, hint, source, file))
