"""Which track part (dashboard card) a finding is about (P5-T05a).

By its ``component`` id; by the model a ``wszst check`` section names (``vrcorn_model``,
or Wiimm's ``_d`` copy ``course_d_model``); by its file (``map_model.brres`` is the
Minimap; files inside a folder part such as ``posteffect/`` count, judged only inside the
project, so a project kept in a folder called "posteffect" is not mistaken for one); or,
for a finding about the whole SZS, by the part its message names: measured real lines
(wszst 2.42a) say "Optional file: ./posteffect/posteffect.bblm", "File 'vrcorn_model.brres'
has 497 vertices", "Missing bones ... in minimap MDL" and "Track will only run at slot 6.1".
Only a finding about the whole SZS (``archive``) is read this way: CT Studio's own steps say
which part they mean. Anything else (extra files, effects, the build) is the whole track.
"""

from __future__ import annotations

import re
from pathlib import PurePath

from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS
from ctstudio.core.validation.issues import Issue
from ctstudio.core.validation.wszst_check import ARCHIVE

_OWN = {name: spec.id for spec in COMPONENTS for name in spec.outputs if not name.endswith("/")}
# "course_d_model.brres": the model Wiimm's '_d' tracks carry (all 20 retail ones); the same
# rule is applied to every "_model" file, though only the course model is seen so far.
_FILES = _OWN | {n.replace("_model.", "_d_model."): p for n, p in _OWN.items() if "_model." in n}
_FOLDERS = {
    name[:-1]: spec.id for spec in COMPONENTS for name in spec.outputs if name.endswith("/")
}
_MENTIONED_FILE = re.compile(r"\./(\S+)|'([^'\s]+\.brres)'")
_SAID: tuple[tuple[re.Pattern[str], str], ...] = (
    # "will (only|also|not) run", "may run", "most likely run" at slot(s) N (wszst 2.42a)
    (re.compile(r"^Track (?:will|may|most likely)\b.*?\brun at slots? \d"), "track_info"),
    (re.compile(r"\bminimap MDL\b"), "minimap"),
)


def part_of(issue: Issue, root: PurePath | None = None) -> str | None:
    """The component id of the card this finding is about, or None (the whole track)."""
    if issue.component in COMPONENT_BY_ID:
        return issue.component
    named = _FILES.get(f"{issue.component}.brres")
    if named is not None:
        return named
    if issue.file is not None:
        return _part_of_file(_inside(PurePath(issue.file), root))
    return _part_said(issue.message) if issue.component == ARCHIVE else None


def _inside(file: PurePath, root: PurePath | None) -> PurePath:
    """The file relative to the project when inside it; otherwise only its own folder counts
    (the same on every system: "C:/..." is not absolute on Linux)."""
    if root is not None and file.is_relative_to(root):
        return file.relative_to(root)
    return PurePath(*file.parts[-2:])


def _part_of_file(file: PurePath) -> str | None:
    named = _FILES.get(file.name)
    if named is not None:
        return named
    return next((_FOLDERS[p] for p in file.parts if p in _FOLDERS), None)  # or the folder


def _part_said(message: str) -> str | None:
    for pattern, part in _SAID:
        if pattern.search(message):
            return part
    for found in _MENTIONED_FILE.finditer(message):
        file = PurePath(found.group(1) or found.group(2))
        part = _FILES.get(file.name) or _FOLDERS.get(file.parts[0] if len(file.parts) > 1 else "")
        if part is not None:
            return part
    return None
