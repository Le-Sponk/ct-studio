"""Typed adapter for RiiStudio's ``rszst`` CLI (pinned 5.11.5): DAE import, JSON, presets.

Measured on Windows (P2-T05e, docs/reference/TOOLS.md):

* The Windows build reads argv through the ANSI code page, so every non-ASCII path,
  relative ones too, fails or is silently ignored. Each call therefore copies its inputs
  into a private staging folder under fixed ASCII names, runs there with bare names and
  copies the outputs to their destination. The staging folder's own path may be non-ASCII
  (the working directory is passed as a wide string).
* A texture the DAE names but which is absent still gives exit 0 and a BRRES holding a
  32x32 placeholder. Texture references are therefore resolved before running, from the
  DAE's folder or its ``textures/`` subfolder (the two places rszst looks).
* clap errors exit -1 (0xFFFFFFFF on Windows, 255 on Linux): any nonzero exit fails, and
  so does exit 0 without the expected output file and magic.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path, PurePosixPath

from ctstudio.core.errors import CTStudioError
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.staging import (
    collada_images,
    deliver,
    executable_for,
    occupied,
    run_collecting,
    stage,
)

BRRES_MAGIC = b"bres"
BIN_MAGIC = b"RBUF"
MODEL_NAME = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_HINT = "Configure RiiStudio or bootstrap the pinned tools."


class RiiStudioError(CTStudioError):
    """rszst refused, failed or produced nothing usable; nothing was delivered."""

    def __init__(
        self, source: Path, reason: str, *, exit_code: int | None = None, details: str = ""
    ) -> None:
        self.source = source
        self.exit_code = exit_code
        super().__init__(
            f"RiiStudio could not process {source.name}: {reason}",
            hint="Fix the file named above, or open it in RiiStudio to see the problem.",
            details=details or None,
        )


def _run(
    source: Path,
    args: list[str],
    work: Path,
    executable: Path | None,
    timeout: float,
    cancel: CancelToken | None,
) -> None:
    exe = executable_for("rszst", executable, _HINT)
    result = run_collecting([exe, *args], work, timeout=timeout, cancel=cancel)
    if result.exit_code != 0:
        raise RiiStudioError(
            source,
            f"rszst exited {result.exit_code}",
            exit_code=result.exit_code,
            details=result.details,
        )


def _output(source: Path, path: Path, magic: bytes) -> bytes:
    data = path.read_bytes() if path.is_file() else b""
    if not data.startswith(magic):
        raise RiiStudioError(source, f"rszst exited 0 but wrote no valid {path.name}", exit_code=0)
    return data


def _free(source: Path, *destinations: Path, overwrite: bool) -> None:
    if (taken := occupied(destinations, overwrite=overwrite)) is not None:
        raise RiiStudioError(source, f"{taken} already exists (choose overwrite to replace it)")


def _texture(dae: Path, reference: str) -> tuple[str, Path]:
    """The staging-relative path and source file rszst would read for one reference."""
    if not reference.isascii():
        raise RiiStudioError(dae, f"texture name {reference!r} is non-ASCII; rszst cannot read it")
    relative = PurePosixPath(reference.replace("\\", "/"))
    if relative.is_absolute() or ":" in reference or ".." in relative.parts or not relative.parts:
        raise RiiStudioError(dae, f"texture {reference!r} is outside the model's folder")
    for candidate in (relative, PurePosixPath("textures") / relative):
        if (dae.parent / candidate).is_file():
            return candidate.as_posix(), dae.parent / candidate
    raise RiiStudioError(dae, f"texture file missing: {reference} (rszst would substitute a blank)")


def _dae_textures(dae: Path) -> dict[str, Path]:
    references = collada_images(dae.read_bytes() if dae.is_file() else b"")
    if references is None:
        raise RiiStudioError(dae, "not a COLLADA (.dae) model file")
    return dict(_texture(dae, reference) for reference in references)


def _copy_into(work: Path, relative: str, source: Path) -> None:
    target = work / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def import_brres(
    dae: Path,
    destination: Path,
    *,
    model_name: str,
    min_mip: int | None = None,
    presets: Path | None = None,
    overwrite: bool = False,
    executable: Path | None = None,
    timeout: float = 300,
    cancel: CancelToken | None = None,
) -> Path:
    """Convert a COLLADA model and its textures to a BRRES at ``destination``."""
    dae, destination = Path(dae).resolve(), Path(destination).resolve()
    if not MODEL_NAME.match(model_name):
        raise RiiStudioError(
            dae, f"model name {model_name!r} must be 1-64 ASCII letters, digits or _"
        )
    textures = _dae_textures(dae)
    if presets is not None and not any(Path(presets).glob("*.rspreset")):
        # rszst only warns and builds without them (exit 0, measured)
        raise RiiStudioError(dae, f"no .rspreset files in {presets}")
    _free(dae, destination, overwrite=overwrite)
    args = ["import-brres", "model.dae", "out.brres", "--model-name", model_name]
    if min_mip is not None:
        args += ["--mipmaps", "--min-mip", str(min_mip)]
    with stage("rszst") as work:
        shutil.copyfile(dae, work / "model.dae")
        for relative, source in textures.items():
            _copy_into(work, relative, source)
        if presets is not None:
            shutil.copytree(presets, work / "presets")
            args += ["--preset-path", "presets"]
        _run(dae, args, work, executable, timeout, cancel)
        return deliver(destination, _output(dae, work / "out.brres", BRRES_MAGIC))


def brres_to_json(
    brres: Path,
    destination: Path,
    *,
    overwrite: bool = False,
    executable: Path | None = None,
    timeout: float = 300,
    cancel: CancelToken | None = None,
) -> tuple[Path, Path]:
    """Write ``destination`` (.json) and its ``.bin`` sidecar, found by the JSON's stem."""
    brres, destination = Path(brres).resolve(), Path(destination).resolve()
    if destination.suffix.lower() != ".json":
        raise RiiStudioError(brres, f"{destination.name} must end in .json")
    sidecar = destination.with_suffix(".bin")
    _free(brres, destination, sidecar, overwrite=overwrite)
    with stage("rszst") as work:
        shutil.copyfile(brres, work / "in.brres")
        _run(brres, ["brres-to-json", "in.brres", "out.json"], work, executable, timeout, cancel)
        json_data = _output(brres, work / "out.json", b"{")
        bin_data = _output(brres, work / "out.bin", BIN_MAGIC)
        return deliver(destination, json_data), deliver(sidecar, bin_data)


def json_to_brres(
    json_path: Path,
    destination: Path,
    *,
    overwrite: bool = False,
    executable: Path | None = None,
    timeout: float = 300,
    cancel: CancelToken | None = None,
) -> Path:
    """Rebuild a BRRES from a JSON and the ``.bin`` sidecar next to it."""
    json_path, destination = Path(json_path).resolve(), Path(destination).resolve()
    sidecar = json_path.with_suffix(".bin")
    if not sidecar.is_file():
        raise RiiStudioError(json_path, f"its data file {sidecar.name} is missing")
    _free(json_path, destination, overwrite=overwrite)
    with stage("rszst") as work:
        shutil.copyfile(json_path, work / "in.json")
        shutil.copyfile(sidecar, work / "in.bin")
        _run(
            json_path,
            ["json-to-brres", "in.json", "out.brres"],
            work,
            executable,
            timeout,
            cancel,
        )
        return deliver(destination, _output(json_path, work / "out.brres", BRRES_MAGIC))


def dump_presets(
    brres: Path,
    folder: Path,
    *,
    overwrite: bool = False,
    executable: Path | None = None,
    timeout: float = 300,
    cancel: CancelToken | None = None,
) -> list[Path]:
    """Write one ``.rspreset`` per material into ``folder``; other files are left alone."""
    brres, folder = Path(brres).resolve(), Path(folder).resolve()
    with stage("rszst") as work:
        shutil.copyfile(brres, work / "in.brres")
        _run(brres, ["dump-presets", "in.brres", "presets"], work, executable, timeout, cancel)
        produced = sorted((work / "presets").glob("*.rspreset"))
        if not produced:
            raise RiiStudioError(brres, "rszst exited 0 but wrote no presets", exit_code=0)
        data = {path.name: _output(brres, path, BRRES_MAGIC) for path in produced}
        _free(brres, *(folder / name for name in data), overwrite=overwrite)
        return [deliver(folder / name, payload) for name, payload in data.items()]
