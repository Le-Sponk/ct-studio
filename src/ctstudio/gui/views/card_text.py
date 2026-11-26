"""What a part card shows about its file (P5-T10e, owner decision D3).

``shown_summary`` puts the name of a file outside the project before its folder, so a long
folder never pushes the name out of the card's three-line summary (the whole reason stays in
the tooltip). ``same_part`` tells whether a card's note still applies after a re-bind: only
the same project object, mode and path keep it.
"""

from __future__ import annotations

from pathlib import Path

from ctstudio.core.project.project import Project
from ctstudio.gui.views.wrap_text import breakable

USING = "using "
Bound = tuple[Project, str, Path | None]  # the project object, the part's mode and its path


def shown_summary(text: str) -> str:
    """``using <absolute path>`` as ``using <name> in <folder>``; other text unchanged."""
    if not text.startswith(USING):
        return text
    path = Path(text.removeprefix(USING))
    if not path.is_absolute() or not path.name:
        return text
    return breakable(f"{USING}{path.name} in {path.parent}")


def same_part(before: Bound | None, after: Bound) -> bool:
    """True when nothing about this card changed: the very same project, mode and path."""
    return before is not None and before[0] is after[0] and before[1:] == after[1:]
