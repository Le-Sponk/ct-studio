"""Typed ABMatt 1.3.2 material edits and copy/paste between archives.

Measured on Windows (P2-T05e3; docs/reference/TOOLS.md):

* Selectors are unanchored regex searches (``for oad`` edits ``road``; ``.`` matches any
  character), so every selector here is ``^<escaped name>$`` qualified by an anchored
  model, and with two archives also by the archive's file name.
* A material that matches nothing fails ("No items found", exit 1), but an edit that
  changes nothing prints a blank line, writes nothing and exits 0. No-op edits are not
  run; any other edit must change the archive.
* Only ``xlu`` and ``cullmode`` are shown by ``-c info``, so only they are offered: after
  every run the whole info table must equal the expected one.
* Paste copies settings and layers and removes target textures nothing uses any more
  ("Unused textures: {...} / (FIXED): Remove textures"); those names are reported. The
  copy source is never rewritten.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ctstudio.core.tools.abmatt import AbmattError, AbmattRunner, MaterialInfo, runner
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.staging import deliver, stage

CULL_MODES = ("none", "outside", "inside", "all")
_NAME = re.compile(r"^[!-~]{1,64}$")  # printable ASCII without spaces
_REMOVED = re.compile(r"^Unused textures: \{(.*)\}$", re.MULTILINE)
_WARN = re.compile(r"^WARN: (.*)$", re.MULTILINE)


@dataclass(frozen=True)
class MaterialEdit:
    material: str
    model: str
    xlu: bool | None = None
    cull: str | None = None


@dataclass(frozen=True)
class MaterialRef:
    archive: Path
    model: str
    material: str


@dataclass(frozen=True)
class EditResult:
    path: Path
    changed: bool
    materials: tuple[MaterialInfo, ...]


@dataclass(frozen=True)
class PasteResult:
    path: Path
    materials: tuple[MaterialInfo, ...]
    removed_textures: tuple[str, ...]
    warnings: tuple[str, ...]


def _selector(material: str, model: str, archive: str = "") -> str:
    where = f"in {archive} model" if archive else "in model"
    return f"for ^{re.escape(material)}$ {where} ^{re.escape(model)}$"


def _check_names(source: Path, *names: str) -> None:
    if (bad := next((name for name in names if not _NAME.match(name)), None)) is not None:
        raise AbmattError(source, f"name {bad!r} must be 1-64 printable ASCII without spaces")


def _check_edits(path: Path, edits: Sequence[MaterialEdit]) -> None:
    if not edits:
        raise AbmattError(path, "no edits were requested")
    seen: set[tuple[str, str]] = set()
    for edit in edits:
        _check_names(path, edit.material, edit.model)
        if edit.xlu is None and edit.cull is None:
            raise AbmattError(path, f"nothing to change on {edit.material!r}")
        if edit.cull is not None and edit.cull not in CULL_MODES:
            raise AbmattError(path, f"cull mode {edit.cull!r} is not one of {CULL_MODES}")
        if (edit.model, edit.material) in seen:
            raise AbmattError(path, f"{edit.material!r} is edited twice")
        seen.add((edit.model, edit.material))


def _find(source: Path, table: tuple[MaterialInfo, ...], model: str, material: str) -> MaterialInfo:
    for row in table:
        if (row.model, row.material) == (model, material):
            return row
    raise AbmattError(source, f"no material {material!r} in model {model!r}")


def _expected(
    path: Path, table: tuple[MaterialInfo, ...], edits: Sequence[MaterialEdit]
) -> tuple[tuple[MaterialInfo, ...], list[str]]:
    """The table after the edits, and the command lines that change something."""
    after = list(table)
    lines: list[str] = []
    for edit in edits:
        row = _find(path, table, edit.model, edit.material)
        new = replace(
            row,
            xlu=row.xlu if edit.xlu is None else edit.xlu,
            cull=row.cull if edit.cull is None else edit.cull,
        )
        after[table.index(row)] = new
        where = _selector(edit.material, edit.model)
        if new.xlu != row.xlu:
            lines.append(f"set material xlu:{str(new.xlu).lower()} {where}\n")
        if new.cull != row.cull:
            lines.append(f"set material cullmode:{new.cull} {where}\n")
    return tuple(after), lines


def _written(work: Path, source: Path, name: str, before: bytes) -> bytes:
    data = (work / name).read_bytes()
    if not data.startswith(b"bres"):
        raise AbmattError(source, f"abmatt exited 0 but wrote no valid {name}", exit_code=0)
    if data == before:
        raise AbmattError(source, "abmatt exited 0 but did not change the archive", exit_code=0)
    return data


def _confirm(
    tool: AbmattRunner, work: Path, source: Path, name: str, expected: tuple[MaterialInfo, ...]
) -> tuple[MaterialInfo, ...]:
    table = tool.info(work, source, name)
    if table != expected:
        raise AbmattError(source, "the archive's info does not show the requested change")
    return table


def _existing(path: Path) -> Path:
    path = Path(path).resolve()
    if not path.is_file():
        raise AbmattError(path, "archive not found")
    return path


def edit_materials(
    archive: Path,
    edits: Sequence[MaterialEdit],
    *,
    executable: Path | None = None,
    wimgt: Path | None = None,
    timeout: float = 300,
    cancel: CancelToken | None = None,
) -> EditResult:
    """Set translucency and/or cull mode on named materials; the original is backed up."""
    _check_edits(archive, edits)
    path = _existing(archive)
    tool = runner(executable, wimgt, timeout, cancel)
    with stage("abmatt") as work:
        before = path.read_bytes()
        (work / "in.brres").write_bytes(before)
        table = tool.info(work, path, "in.brres")
        expected, lines = _expected(path, table, edits)
        if not lines:
            return EditResult(path, changed=False, materials=table)
        (work / "edit.txt").write_text("".join(lines), encoding="ascii", newline="\n")
        tool.run(work, path, ["-b", "in.brres", "-f", "edit.txt", "-o"])
        data = _written(work, path, "in.brres", before)
        materials = _confirm(tool, work, path, "in.brres", expected)
        return EditResult(deliver(path, data), changed=True, materials=materials)


def paste_material(
    copy: MaterialRef,
    onto: MaterialRef,
    *,
    executable: Path | None = None,
    wimgt: Path | None = None,
    timeout: float = 300,
    cancel: CancelToken | None = None,
) -> PasteResult:
    """Copy one material's settings and layers onto another (same or other archive)."""
    source, target = _existing(copy.archive), _existing(onto.archive)
    _check_names(target, copy.model, copy.material, onto.model, onto.material)
    if (source, copy.model, copy.material) == (target, onto.model, onto.material):
        raise AbmattError(target, "a material cannot be pasted onto itself")
    tool = runner(executable, wimgt, timeout, cancel)
    with stage("abmatt") as work:
        shutil.copyfile(source, work / "src.brres")
        before = target.read_bytes()
        (work / "dst.brres").write_bytes(before)
        donor = _find(source, tool.info(work, source, "src.brres"), copy.model, copy.material)
        table = tool.info(work, target, "dst.brres")
        row = _find(target, table, onto.model, onto.material)
        pasted = replace(donor, model=row.model, material=row.material)
        expected = tuple(pasted if item == row else item for item in table)
        commands = (
            f"copy material {_selector(copy.material, copy.model, 'src.brres')}\n"
            f"paste material {_selector(onto.material, onto.model, 'dst.brres')}\n"
        )
        (work / "paste.txt").write_text(commands, encoding="ascii", newline="\n")
        result = tool.run(
            work, target, ["-b", "src.brres", "-b", "dst.brres", "-f", "paste.txt", "-o"]
        )
        data = _written(work, target, "dst.brres", before)
        materials = _confirm(tool, work, target, "dst.brres", expected)
        removed = _REMOVED.search(result.stdout)
        names = re.findall(r"'([^']*)'", removed.group(1)) if removed else []
        return PasteResult(
            deliver(target, data),
            materials,
            tuple(sorted(names)),
            tuple(_WARN.findall(result.stdout)),
        )
