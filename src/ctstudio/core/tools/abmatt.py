"""Typed adapter for ABMatt 1.3.2 conversions: DAE → model BRRES, OBJ → minimap BRRES.

Measured on Windows (P0-T08, P2-T04d, P2-T05e2; docs/reference/TOOLS.md):

* The MDL0 is named after the source stem up to the first ``_``, and minimap bones
  (``map``/``posLD``/``posRU``) are added only when the *destination* name contains a
  lowercase ``map``. The adapter therefore stages ``<model>.dae`` → ``out.brres`` and
  ``map.obj`` → ``map_model.brres`` in a private folder, then copies the result.
* Lost textures (absent, or only in ``textures/``) and a missing ``wimgt`` are reported
  only as text at exit 0, with a grey solid colour in place of the texture. Texture
  references are checked beforehand and those texts make the run fail.
* In a CJK folder ABMatt writes its output and then crashes printing the path, exit 0:
  only the output file and a ``-c info`` report on it count, never the log.
* Any nonzero exit fails: 1 for a missing input, -1 (0xFFFFFFFF) for frozen-Python crashes.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from ctstudio.core.errors import CTStudioError
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.staging import (
    ToolRun,
    collada_images,
    deliver,
    executable_for,
    occupied,
    run_collecting,
    stage,
)

MODEL_NAME = re.compile(r"^[A-Za-z0-9]{1,64}$")  # ABMatt cuts the name at the first "_"
_INFO_ROW = re.compile(r"^>([^\s>-]+)->(\S+)\txlu:([01]) cull:(inside|outside|none|all)$")
_INFO_LAYER = re.compile(r"^  (\S+):\tScale:\(.*\) Rot:.* Trans:\(.*\)$")
_FAILURE_TEXT = re.compile(
    r"^(?:ERROR:.*|WARN: Failed to find image .*|No texture matching .*)$", re.MULTILINE
)
_HINT = "Configure ABMatt or bootstrap the pinned tools."


class AbmattError(CTStudioError):
    """ABMatt refused, failed or produced nothing usable; nothing was delivered."""

    def __init__(
        self, source: Path, reason: str, *, exit_code: int | None = None, details: str = ""
    ) -> None:
        self.source = source
        self.exit_code = exit_code
        super().__init__(
            f"ABMatt could not convert {source.name}: {reason}",
            hint="Fix the file named above; the details hold ABMatt's own report.",
            details=details or None,
        )


@dataclass(frozen=True)
class MaterialInfo:
    model: str
    material: str
    xlu: bool
    cull: str
    layers: tuple[str, ...] = ()  # texture layer names, in order


@dataclass(frozen=True)
class Conversion:
    path: Path
    materials: tuple[MaterialInfo, ...]


def parse_info(text: str, source: Path = Path("archive.brres")) -> tuple[MaterialInfo, ...]:
    """``abmatt -b FILE -c info``: one ``>model->material`` row per material, then layers."""
    rows: list[tuple[MaterialInfo, list[str]]] = []
    for line in filter(None, (raw.rstrip("\r") for raw in text.splitlines())):
        if match := _INFO_ROW.match(line):
            model, material, xlu, cull = match.groups()
            rows.append((MaterialInfo(model, material, xlu == "1", cull), []))
        elif rows and (layer := _INFO_LAYER.match(line)):
            rows[-1][1].append(layer.group(1))
        else:
            raise AbmattError(source, f"unexpected line in the info report: {line!r}")
    if not rows:
        raise AbmattError(source, "the info report lists no materials")
    return tuple(replace(row, layers=tuple(layers)) for row, layers in rows)


def tool_env(wimgt: Path | None) -> dict[str, str]:
    """ABMatt shells out to ``wimgt`` from PATH; put the pinned one first."""
    folder = wimgt.parent if wimgt is not None else executable_for("wimgt", None, _HINT).parent
    return {**os.environ, "PATH": os.pathsep.join([str(folder), os.environ.get("PATH", "")])}


def check_run(source: Path, result: ToolRun) -> None:
    if result.exit_code != 0:
        raise AbmattError(
            source,
            f"abmatt exited {result.exit_code}",
            exit_code=result.exit_code,
            details=result.details,
        )
    if match := _FAILURE_TEXT.search(result.stdout):
        reason = "wimgt was not found" if "wimgt" in match.group(0) else match.group(0)
        if "texture" in reason or "image" in reason:
            reason = f"a texture was lost ({reason})"
        raise AbmattError(source, reason, exit_code=0, details=result.details)


@dataclass(frozen=True)
class AbmattRunner:
    """One configured ABMatt: its executable, a PATH with wimgt, and run limits."""

    executable: Path
    env: Mapping[str, str]
    timeout: float
    cancel: CancelToken | None

    def run(self, work: Path, source: Path, args: list[str]) -> ToolRun:
        """Run in ``work``; nonzero exits and ABMatt's exit-0 failure texts raise."""
        result = run_collecting(
            [self.executable, *args], work, env=self.env, timeout=self.timeout, cancel=self.cancel
        )
        check_run(source, result)
        return result

    def info(self, work: Path, source: Path, archive: str) -> tuple[MaterialInfo, ...]:
        return parse_info(self.run(work, source, ["-b", archive, "-c", "info"]).stdout, source)


def runner(
    executable: Path | None, wimgt: Path | None, timeout: float, cancel: CancelToken | None
) -> AbmattRunner:
    return AbmattRunner(
        executable_for("abmatt", executable, _HINT), tool_env(wimgt), timeout, cancel
    )


@dataclass(frozen=True)
class _Job:
    source: Path
    staged: str
    output: str
    model: str


def _convert(
    tool: AbmattRunner, job: _Job, work: Path, extra: dict[str, Path]
) -> tuple[bytes, tuple[MaterialInfo, ...]]:
    shutil.copyfile(job.source, work / job.staged)
    for relative, path in extra.items():
        shutil.copyfile(path, work / relative)
    converted = tool.run(work, job.source, ["convert", job.staged, "to", job.output, "-o"])
    data = (work / job.output).read_bytes() if (work / job.output).is_file() else b""
    if not data.startswith(b"bres"):
        reason = f"abmatt exited 0 but wrote no valid {job.output}"
        raise AbmattError(job.source, reason, exit_code=0, details=converted.details)
    materials = tool.info(work, job.source, job.output)
    if names := {m.model for m in materials} - {job.model}:
        raise AbmattError(
            job.source, f"the model came out named {sorted(names)[0]!r}, not {job.model!r}"
        )
    return data, materials


def _textures(dae: Path) -> dict[str, Path]:
    references = collada_images(dae.read_bytes() if dae.is_file() else b"")
    if references is None:
        raise AbmattError(dae, "not a COLLADA (.dae) model file")
    found: dict[str, Path] = {}
    for reference in references:
        relative = PurePosixPath(reference.replace("\\", "/"))
        if len(relative.parts) != 1 or ":" in reference or not reference.isascii():
            raise AbmattError(dae, f"texture {reference!r} must be a plain name beside the model")
        if not (dae.parent / reference).is_file():
            raise AbmattError(dae, f"texture file missing beside the model: {reference}")
        found[reference] = dae.parent / reference
    return found


def _free(source: Path, destination: Path, overwrite: bool) -> None:
    if occupied([destination], overwrite=overwrite) is not None:
        raise AbmattError(source, f"{destination} already exists (choose overwrite to replace it)")


def convert_model(
    dae: Path,
    destination: Path,
    *,
    model_name: str,
    overwrite: bool = False,
    executable: Path | None = None,
    wimgt: Path | None = None,
    timeout: float = 300,
    cancel: CancelToken | None = None,
) -> Conversion:
    """Convert a COLLADA model with its textures; the MDL0 is named ``model_name``."""
    dae, destination = Path(dae).resolve(), Path(destination).resolve()
    if not MODEL_NAME.match(model_name) or model_name == "map":
        raise AbmattError(
            dae, f"model name {model_name!r} must be 1-64 ASCII letters or digits, not 'map'"
        )
    if "map" in destination.name:
        raise AbmattError(
            dae, f"{destination.name} contains 'map', which makes ABMatt add minimap bones"
        )
    textures = _textures(dae)
    _free(dae, destination, overwrite)
    tool = runner(executable, wimgt, timeout, cancel)
    job = _Job(dae, f"{model_name}.dae", "out.brres", model_name)
    with stage("abmatt") as work:
        data, materials = _convert(tool, job, work, textures)
        return Conversion(deliver(destination, data), materials)


def convert_minimap(
    obj: Path,
    destination: Path,
    *,
    overwrite: bool = False,
    executable: Path | None = None,
    wimgt: Path | None = None,
    timeout: float = 300,
    cancel: CancelToken | None = None,
) -> Conversion:
    """Convert a drivable-surface OBJ into a minimap BRRES (MDL0 ``map`` with its bones).

    The bone positions are not checked here: ``wiimm_kcl.patch_minimap`` verifies them.
    """
    obj, destination = Path(obj).resolve(), Path(destination).resolve()
    if obj.suffix.lower() != ".obj":
        raise AbmattError(obj, "a minimap must be converted from an OBJ file")
    _free(obj, destination, overwrite)
    tool = runner(executable, wimgt, timeout, cancel)
    job = _Job(obj, "map.obj", "map_model.brres", "map")
    with stage("abmatt") as work:
        data, materials = _convert(tool, job, work, {})
        return Conversion(deliver(destination, data), materials)
