"""Development progress for the README: `uv run python scripts/progress.py [--check]`.

Counts the task checklists in ``docs/phases/PHASE_*.md``: every heading or list item that
starts ``[ ]``/``[x]`` followed by a task ID (``P4-T05a``, ``P5-HC1``, ``P8-DEEPCLEAN`` …).
A task split into lettered parts (``P4-T05`` → ``P4-T05a``, ``P4-T05b``) counts as its
parts only. Phase 14 is left out: the plan makes it optional, done only on request.

Writes the result between the progress markers in ``README.md``; ``--check`` changes
nothing and exits 1 when the README is out of date (``tests/unit/test_progress.py`` runs
this check in the quality gate, so a stale figure blocks the commit). Exit 2: bad files.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- progress:start (written by scripts/progress.py; do not edit by hand) -->"
END = "<!-- progress:end -->"
OPTIONAL_PHASES = frozenset({14})
BAR_WIDTH = 20
_TASK = re.compile(
    r"^\s*(?:#{2,6}|[-*])\s*\[([ xX])\]\s*(?:\*\*)?(P(\d+)-[A-Z]+\d*(?:[a-z]\d*)?)\b"
)
_TITLE = re.compile(r"^# Phase (\d+) — (.+)$")


@dataclass(frozen=True)
class Phase:
    number: int
    title: str
    done: int
    total: int


@dataclass(frozen=True)
class Progress:
    phases: tuple[Phase, ...]

    @property
    def done(self) -> int:
        return sum(p.done for p in self.phases)

    @property
    def total(self) -> int:
        return sum(p.total for p in self.phases)

    @property
    def current(self) -> Phase | None:
        """The first phase with unfinished work; None when everything is done."""
        return next((p for p in self.phases if p.done < p.total), None)


def count(phases_dir: Path) -> Progress:
    phases: list[Phase] = []
    for path in sorted(phases_dir.glob("PHASE_*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        title = _TITLE.match(lines[0]) if lines else None
        if title is None:
            raise ValueError(f"{path.name}: the first line must be '# Phase N — Title'")
        number = int(title.group(1))
        if number in OPTIONAL_PHASES:
            continue
        tasks = _tasks(path, lines, number)
        counted = [t for t in tasks if not any(_is_part(o, t) for o in tasks)]
        done = sum(tasks[t] for t in counted)
        phases.append(Phase(number, title.group(2), done, len(counted)))
    return Progress(tuple(sorted(phases, key=lambda p: p.number)))


def _is_part(task: str, parent: str) -> bool:
    """Lettered splits or numbered subparts; e10 is a sibling of e1, not its child."""
    suffix = task[len(parent) :] if task.startswith(parent) else ""
    pattern = r"[a-z]\d*" if parent[-1].isdigit() else r"\d+"
    return re.fullmatch(pattern, suffix) is not None


def _tasks(path: Path, lines: list[str], number: int) -> dict[str, bool]:
    tasks: dict[str, bool] = {}
    for line in lines:
        match = _TASK.match(line)
        if match is None:
            continue
        task, phase = match.group(2), int(match.group(3))
        if phase != number or task in tasks:
            raise ValueError(f"{path.name}: {task} is listed twice or in the wrong phase file")
        tasks[task] = match.group(1) != " "
    return tasks


def render(progress: Progress) -> str:
    percent = 100 * progress.done // progress.total if progress.total else 0
    filled = BAR_WIDTH * progress.done // progress.total if progress.total else 0
    bar = "█" * filled + "░" * (BAR_WIDTH - filled)
    now = progress.current
    where = (
        f"Now working on phase {now.number}, {now.title} ({now.done} of {now.total} done)."
        if now
        else "Every planned task is done."
    )
    return "\n".join(
        [
            START,
            f"**Progress:** `{bar}` {percent}% — {progress.done} of {progress.total} planned tasks"
            " done.",
            f"{where} Counted from the phase plans; see the [roadmap](docs/ROADMAP.md).",
            END,
        ]
    )


def updated(readme: str, block: str) -> str:
    start, end = readme.find(START), readme.find(END)
    if start < 0 or end < start:
        raise ValueError("README.md has no progress markers")
    return readme[:start] + block + readme[end + len(END) :]


def main(argv: Sequence[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="Update the README's progress figure.")
    parser.add_argument("--check", action="store_true", help="only report a stale README")
    args = parser.parse_args(argv)
    readme_path = root / "README.md"
    try:
        readme = readme_path.read_text(encoding="utf-8")
        new = updated(readme, render(count(root / "docs" / "phases")))
    except (OSError, ValueError) as exc:
        print(f"progress: {exc}", file=sys.stderr)
        return 2
    if new == readme:
        return 0
    if args.check:
        print("README.md progress is out of date: run uv run python scripts/progress.py")
        return 1
    readme_path.write_text(new, encoding="utf-8", newline="\n")
    print("README.md progress updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
