"""Typed Wiimm auto-add library management (P2-T05d).

Measured on wszst 2.42a (``docs/reference/TOOLS.md``): ``autoadd`` without a source is
path discovery only (exit 0 for absent, empty or filled folders); ``autoadd SRC`` prints
one ``ANALYZE`` line per standard-named track/arena archive and one ``ADD`` line per new
library file, with no summary; ``autoadd --dest LIB -vv`` lists found, missed and invalid
files, checked against Wiimm's own list of the originals. Only that last report is
evidence that a library is usable; ``create_szs(auto_add=...)`` requires it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ctstudio.core.errors import ParseError
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.wiimm import AutoAddLibrary, WiimmError, invoke, raise_on_error

_CURRENT = re.compile(r"^CURRENT AUTO-ADD PATH: (.+)$")
_SEARCH = re.compile(r"^\s*SEARCH PATH\[(\d+)\]: (.+)$")
_ANALYZE = re.compile(r"^ANALYZE (\S+?):(.*)$")  # "ANALYZE ?:" = unreadable source
_ADD = re.compile(r"^  ADD\s+\d+, \S+?:(.+)$")
_SECTION = re.compile(r"^LIST OF (|MISSED |INVALID )FILES IN .+$")
_ENTRY = re.compile(r"^  (\S+)\s+(\S.*)$")
_DUMP = re.compile(r"^\s+\d+:\s+(?:[0-9a-f]{2}\s+)+:.*:$")
_COUNT = re.compile(r"^  => (\d+) of (\d+) files (found|missed|invalid)\.$")
_SECTION_NAMES = {"": "found", "MISSED ": "missed", "INVALID ": "invalid"}


@dataclass(frozen=True)
class AutoAddStatus:
    current: str
    search_paths: tuple[str, ...]


@dataclass(frozen=True)
class AutoAddBuild:
    library: str
    analyzed: tuple[str, ...]  # archives Wiimm read, as it printed them
    added: tuple[str, ...]  # library files written by this run (none when up to date)


def _lines(text: str) -> list[str]:
    return [line.rstrip("\r") for line in text.splitlines() if line.strip()]


def _current(lines: list[str]) -> str:
    found = [match.group(1) for line in lines if (match := _CURRENT.match(line))]
    if len(found) != 1:
        raise ParseError("wszst autoadd", "expected one CURRENT AUTO-ADD PATH line")
    return found[0]


def parse_autoadd_status(text: str) -> AutoAddStatus:
    lines = _lines(text)
    current = _current(lines)
    indexed = [match.groups() for line in lines if (match := _SEARCH.match(line))]
    if [int(index) for index, _ in indexed] != list(range(len(indexed))):
        raise ParseError("wszst autoadd", "SEARCH PATH indices are not 0..N-1 in order")
    if len(indexed) + 1 != len(lines):
        raise ParseError("wszst autoadd", "unexpected lines in the auto-add status")
    return AutoAddStatus(current, tuple(path for _, path in indexed))


def parse_autoadd_build(text: str) -> AutoAddBuild:
    lines = _lines(text)
    library = _current(lines)
    analyzed: list[str] = []
    added: list[str] = []
    for line in lines:
        if match := _ANALYZE.match(line):
            if match.group(1) != "?":
                analyzed.append(match.group(2))
        elif match := _ADD.match(line):
            added.append(match.group(1))
        elif not _CURRENT.match(line):
            raise ParseError("wszst autoadd", f"unexpected auto-add line: {line!r}")
    return AutoAddBuild(library, tuple(analyzed), tuple(added))


def _close(name: str, entries: list[str], count: tuple[int, int] | None, total: set[int]) -> None:
    """A listed section needs a matching count line; an empty one may omit it."""
    if count is None:
        if entries:
            raise ParseError("wszst autoadd", f"{name} files are listed without a count")
        return
    if count[0] != len(entries):
        raise ParseError("wszst autoadd", f"{name} count {count[0]} != {len(entries)} listed")
    total.add(count[1])


def _preamble(line: str) -> None:
    if not (_CURRENT.match(line) or _SEARCH.match(line)):
        raise ParseError("wszst autoadd", f"unexpected line: {line!r}")


def _in_section(line: str, current: str, entries: list[str], counts: dict[str, Any]) -> None:
    if _DUMP.match(line):
        return  # -vv hex dumps of found files' checksums
    if (match := _COUNT.match(line)) and match.group(3) == current:
        counts[current] = (int(match.group(1)), int(match.group(2)))
    elif match := _ENTRY.match(line):
        entries.append(f"{match.group(1)} {match.group(2)}")
    else:
        raise ParseError("wszst autoadd", f"unexpected line: {line!r}")


def _sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    counts: dict[str, tuple[int, int]] = {}
    current: str | None = None
    for line in lines:
        if match := _SECTION.match(line):
            current = _SECTION_NAMES[match.group(1)]
            sections[current] = []
        elif current is None:
            _preamble(line)
        else:
            _in_section(line, current, sections[current], counts)
    totals: set[int] = set()
    for name, entries in sections.items():
        _close(name, entries, counts.get(name), totals)
    if len(totals) > 1 or not {"found", "missed"} <= sections.keys():
        raise ParseError("wszst autoadd", "the -vv report lacks a section or totals disagree")
    return sections


def parse_autoadd_verify(text: str, library: Path) -> AutoAddLibrary:
    lines = _lines(text)
    _current(lines)
    sections = _sections(lines)
    return AutoAddLibrary(
        library,
        found=tuple(sections["found"]),
        missed=tuple(sections["missed"]),
        invalid=tuple(sections.get("invalid", ())),
    )


def autoadd_status(
    library: Path | None = None,
    *,
    executable: Path | None = None,
    timeout: float = 60,
    cancel: CancelToken | None = None,
) -> AutoAddStatus:
    """Paths Wiimm would search (``library`` overrides the default). Not a health check."""
    if library is None:
        out = invoke(executable, ["autoadd"], Path.cwd(), timeout, cancel)
        raise_on_error(out, Path.cwd(), (0,))
        return parse_autoadd_status(out.stdout)
    library = Path(library).resolve()
    out = invoke(executable, ["autoadd", "--dest", library.name], library.parent, timeout, cancel)
    raise_on_error(out, library, (0,))
    return parse_autoadd_status(out.stdout)


def autoadd_verify(
    library: Path,
    *,
    executable: Path | None = None,
    timeout: float = 120,
    cancel: CancelToken | None = None,
) -> AutoAddLibrary:
    """Check a library's files against Wiimm's list of originals (``-vv``)."""
    library = Path(library).resolve()
    args = ["autoadd", "--dest", library.name, "-vv"]
    out = invoke(executable, args, library.parent, timeout, cancel)
    raise_on_error(out, library, (0,))
    return parse_autoadd_verify(out.stdout, library)


def autoadd_create(
    race_course_dir: Path,
    dest: Path,
    *,
    executable: Path | None = None,
    timeout: float = 600,
    cancel: CancelToken | None = None,
) -> AutoAddBuild:
    """Add the files of a ``Race/Course`` folder's archives to the library ``dest``.

    Wiimm prints no summary; a run that analysed no archive is a failure here, because
    only standard track/arena file names are read and anything else is silently skipped.
    Re-running reports no ``added`` files. Verify the result with ``autoadd_verify``.
    """
    source, dest = Path(race_course_dir).resolve(), Path(dest).resolve()
    args = ["autoadd", source.name, "--DEST", str(dest)]
    out = invoke(executable, args, source.parent, timeout, cancel)
    raise_on_error(out, source, (0,))
    build = parse_autoadd_build(out.stdout)
    if not build.analyzed:
        reason = f"no track archives with standard track/arena names in {source}"
        raise WiimmError(source, out.exit_code, reason, error_code=None, details=out.stdout)
    return build
