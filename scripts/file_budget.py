"""File-length budget: `uv run python scripts/file_budget.py [root]` (AGENTS rule 8).

Every Python file under ``src/``, ``scripts/`` and ``tests/`` stays within 400 lines; a longer
file is split rather than excused. Prints one line per file over the limit. Exit status: 0
within budget, 1 a file is over. ``scripts/check.py`` runs it as its last step (P2-GATE).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

LIMIT = 400
FOLDERS = ("src", "scripts", "tests")


def over_budget(root: Path) -> list[tuple[Path, int]]:
    """Each Python file under ``FOLDERS`` longer than ``LIMIT`` lines, with its length."""
    found: list[tuple[Path, int]] = []
    for folder in FOLDERS:
        for path in sorted((root / folder).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            with path.open(encoding="utf-8") as handle:
                count = sum(1 for _ in handle)
            if count > LIMIT:
                found.append((path, count))
    return found


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    over = over_budget(root)
    for path, count in over:
        print(f"{path.relative_to(root)}: {count} lines (limit {LIMIT}); split it")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
