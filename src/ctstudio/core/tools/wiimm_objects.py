"""Which objects a KMP places and which files each needs, from Wiimm's own tables (P4-T05b).

Measured on wkmpt 2.42a (``docs/reference/TOOLS.md``): ``wkmpt cat KMP`` ends its GOBJ
section with an "Object statistics" table, one ``##  count  0x<id>  name`` row per object
type (no name when Wiimm does not know the id) closed by ``## GOBJ total: N objects, M
types``. ``wkmpt objects --long ID...`` prints Wiimm's object database entry for each id,
including a ``Files:`` list continued on indented lines. Its keys match loosely (``0xd2``
also prints ``0xd5``), so only the asked-for ids are kept.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ctstudio.core.errors import ParseError
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.wiimm import invoke, raise_on_error

_STATS = "# Object statistics:"
_ROW = re.compile(r"^##\s+(\d+)\s+0x([0-9a-f]+)(?:\s+(\S+).*)?$")
_TOTAL = re.compile(r"^## GOBJ total: (\d+) objects?, (\d+) types?$")
_ENTRY = re.compile(r"^\s*([0-9a-f]+) (\S+)")
_LABEL = re.compile(r"^   ([A-Za-z#0-9]+):\s+(.*)$")
_MORE = re.compile(r"^ {10}(\S.*)$")
WIDTH = "4000"  # one line per database line, so a long file name is never wrapped


@dataclass(frozen=True)
class KmpObject:
    id: int
    name: str  # "" when Wiimm does not know the id
    count: int  # how many the course places


def parse_kmp_objects(text: str, source: Path) -> tuple[KmpObject, ...]:
    """The object statistics of ``wkmpt cat``; refused when its rows disagree with the total."""
    lines = text.splitlines()
    if _STATS not in lines:
        raise ParseError(str(source), "wkmpt printed no object statistics")
    objects: list[KmpObject] = []
    for line in lines[lines.index(_STATS) + 1 :]:
        if total := _TOTAL.match(line):
            if (sum(o.count for o in objects), len(objects)) != (
                int(total.group(1)),
                int(total.group(2)),
            ):
                raise ParseError(str(source), "the object rows disagree with the GOBJ total")
            return tuple(objects)
        if row := _ROW.match(line):
            objects.append(KmpObject(int(row.group(2), 16), row.group(3) or "", int(row.group(1))))
    raise ParseError(str(source), "the object statistics have no GOBJ total")


def parse_object_files(text: str) -> dict[int, tuple[str, ...]]:
    """Object id -> the files Wiimm's database lists for it (none for some objects)."""
    found: dict[int, list[str]] = {}
    current: list[str] | None = None
    label = ""
    for line in text.splitlines():
        if entry := _ENTRY.match(line):  # the "  ID Object name" header is not hex
            current, label = found.setdefault(int(entry.group(1), 16), []), ""
        elif current is not None and (labelled := _LABEL.match(line)):
            label = labelled.group(1)
            if label == "Files":
                current.append(labelled.group(2).strip())
        elif current is not None and label == "Files" and (more := _MORE.match(line)):
            current.append(more.group(1).strip())
    return {key: tuple(files) for key, files in found.items()}


def kmp_objects(
    kmp: Path,
    *,
    executable: Path | None = None,
    timeout: float = 60,
    cancel: CancelToken | None = None,
) -> tuple[KmpObject, ...]:
    """The objects ``kmp`` places (binary or text KMP)."""
    out = invoke(executable, ["cat", kmp.name], kmp.parent, timeout, cancel, tool="wkmpt")
    raise_on_error(out, kmp, (0,))
    return parse_kmp_objects(out.stdout, kmp)


def object_files(
    ids: Iterable[int],
    *,
    executable: Path | None = None,
    timeout: float = 60,
    cancel: CancelToken | None = None,
) -> dict[int, tuple[str, ...]]:
    """The files each of ``ids`` needs; an id Wiimm does not know is left out."""
    wanted = sorted(set(ids))
    if not wanted:
        return {}
    args = ["objects", "--long", "--width", WIDTH, *(hex(i) for i in wanted)]
    out = invoke(executable, args, Path.cwd(), timeout, cancel, tool="wkmpt")
    raise_on_error(out, Path("wkmpt objects"), (0,))
    listed = parse_object_files(out.stdout)
    return {i: listed[i] for i in wanted if i in listed}
