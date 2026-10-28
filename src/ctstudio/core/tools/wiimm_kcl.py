"""Typed Wiimm KCL analysis and minimap patching (P2-T05c2).

``wkclt analyze``/``flags`` print fixed text tables; the parsers refuse output whose
tables are missing or disagree with each other rather than return partial facts.
``wszst minimap --auto`` exits 0 and changes nothing when the model lacks the
``posLD``/``posRU`` bones, so a missing data table is an error here, not a no-op.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from ctstudio.core.errors import ParseError
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.wiimm import WiimmError, invoke, raise_on_error

Vector = tuple[float, float, float]
Corners = tuple[Vector, Vector]  # left-down (posLD), right-up (posRU)

_FLOAT = r"(-?\d+(?:\.\d+)?(?:e[+-]\d+)?)"
_COUNT = re.compile(r"(?m)^\s*(\d+) / (\d+)\s+vertex\s+normal\s*$")
_RANGE = {key: re.compile(rf"(?m)^\s*{key}:\s+{_FLOAT}\s+{_FLOAT}\s*$") for key in ("min", "max")}
_FLAG = re.compile(
    r"(?m)^\s*0x([0-9a-f]{4}) = 0x([0-9a-f]{2}) \| 0x([0-9a-f]{3}) << 5 :"
    r" [-1] [-1] [-1] [-1]\s+\d+ :\s+(\d+) =\s+[\d.]+%\s*$"
)
_TYPE = re.compile(r"(?m)^\s*T 0x([0-9a-f]{2}) :\s+(\d+) =\s+[\d.]+% : (.+?)\s*$")
_TYPE_HEADER = re.compile(r"(?m)^\s*type :  triangle count  : type description\s*$")
_ROW = {
    key: re.compile(rf"(?m)^\s*{key}\s+" + r"\s+".join([_FLOAT] * 6) + r"\s*$")
    for key in ("Translation:", "Recommend\\.:")
}
_PATCH = re.compile(r"(?m)^PATCH MINIMAP ")


@dataclass(frozen=True)
class KclAnalysis:
    path: Path
    triangles: int
    vertices: int
    vertex_min: float
    vertex_max: float
    normal_min: float
    normal_max: float


@dataclass(frozen=True)
class KclFlag:
    flag: int
    type: int
    variant: int
    triangles: int


@dataclass(frozen=True)
class KclType:
    type: int
    triangles: int
    description: str


@dataclass(frozen=True)
class KclFlags:
    path: Path
    flags: tuple[KclFlag, ...]
    types: tuple[KclType, ...]

    @property
    def triangles(self) -> int:
        return sum(entry.triangles for entry in self.types)


@dataclass(frozen=True)
class MinimapPatch:
    path: Path
    patched: bool
    before: Corners
    after: Corners
    recommended: Corners


def parse_kcl_analysis(text: str, source: Path) -> KclAnalysis:
    count = _COUNT.search(text)
    ranges = {key: pattern.search(text) for key, pattern in _RANGE.items()}
    if count is None or ranges["min"] is None or ranges["max"] is None:
        raise ParseError(str(source), "wkclt analyze output lacks its count or min/max rows")
    low, high = ranges["min"], ranges["max"]
    return KclAnalysis(
        source,
        int(count.group(1)),
        int(count.group(2)),
        float(low.group(1)),
        float(high.group(1)),
        float(low.group(2)),
        float(high.group(2)),
    )


def _flag(match: re.Match[str]) -> KclFlag:
    flag, kind, variant = (int(match.group(i), 16) for i in (1, 2, 3))
    return KclFlag(flag, kind, variant, int(match.group(4)))


def _consistent(flags: tuple[KclFlag, ...], types: tuple[KclType, ...]) -> bool:
    by_type: dict[int, int] = {}
    for entry in flags:
        if entry.flag != entry.type | entry.variant << 5:
            return False
        by_type[entry.type] = by_type.get(entry.type, 0) + entry.triangles
    return by_type == {entry.type: entry.triangles for entry in types}


def parse_kcl_flags(text: str, source: Path) -> KclFlags:
    """Both tables are required and must agree: per flag, then per type."""
    header = _TYPE_HEADER.search(text)
    if header is None:
        raise ParseError(str(source), "wkclt flags output lacks the type table")
    flags = tuple(_flag(match) for match in _FLAG.finditer(text, 0, header.start()))
    types = tuple(
        KclType(int(m.group(1), 16), int(m.group(2)), m.group(3))
        for m in _TYPE.finditer(text, header.end())
    )
    if not types or not _consistent(flags, types):
        raise ParseError(str(source), "wkclt flags tables are empty or disagree")
    return KclFlags(source, flags, types)


def _corners(match: re.Match[str]) -> Corners:
    values = [float(value) for value in match.groups()]
    return (values[0], values[1], values[2]), (values[3], values[4], values[5])


def parse_minimap(text: str, source: Path) -> MinimapPatch:
    """Before/after translations; header-only output means no minimap bones."""
    translations = [_corners(m) for m in _ROW["Translation:"].finditer(text)]
    recommended = _ROW["Recommend\\.:"].search(text)
    if not translations or recommended is None:
        raise WiimmError(
            source,
            0,
            "no posLD/posRU minimap bones (Wiimm printed no minimap data)",
            error_code=None,
            details=text,
        )
    patched = _PATCH.search(text) is not None
    if len(translations) != (2 if patched else 1):
        raise ParseError(str(source), "wszst minimap output does not match its PATCH line")
    return MinimapPatch(source, patched, translations[0], translations[-1], _corners(recommended))


def _run_kcl(
    command: str, kcl: Path, executable: Path | None, timeout: float, cancel: CancelToken | None
) -> str:
    kcl = Path(kcl).resolve()
    out = invoke(executable, [command, kcl.name], kcl.parent, timeout, cancel, tool="wkclt")
    raise_on_error(out, kcl, (0,))
    return out.stdout


def kcl_analyze(
    kcl: Path,
    *,
    executable: Path | None = None,
    timeout: float = 120,
    cancel: CancelToken | None = None,
) -> KclAnalysis:
    """Triangle/vertex counts and coordinate ranges of a KCL."""
    return parse_kcl_analysis(_run_kcl("analyze", kcl, executable, timeout, cancel), Path(kcl))


def kcl_flags(
    kcl: Path,
    *,
    executable: Path | None = None,
    timeout: float = 120,
    cancel: CancelToken | None = None,
) -> KclFlags:
    """Per-flag and per-type triangle counts of a KCL."""
    return parse_kcl_flags(_run_kcl("flags", kcl, executable, timeout, cancel), Path(kcl))


def minimap_auto(
    brres: Path,
    *,
    executable: Path | None = None,
    timeout: float = 120,
    cancel: CancelToken | None = None,
) -> MinimapPatch:
    """Patch minimap translations in place; raise if the model has no minimap bones.

    ``patched`` is False when the translations were already the recommended values.
    A reported patch that leaves the file's bytes unchanged is an error.
    """
    brres = Path(brres).resolve()
    before = sha256(brres.read_bytes()).digest() if brres.is_file() else b""
    out = invoke(executable, ["minimap", "--auto", brres.name], brres.parent, timeout, cancel)
    raise_on_error(out, brres, (0,))
    result = parse_minimap(out.stdout, brres)
    if result.patched and sha256(brres.read_bytes()).digest() == before:
        raise WiimmError(
            brres,
            0,
            "minimap patch reported but the file is unchanged",
            error_code=None,
            details=out.stdout,
        )
    return result
