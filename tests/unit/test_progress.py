"""The README's progress figure is counted from the phase plans and kept current."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import progress  # type: ignore[reportMissingImports] - scripts path inserted above

README = f"# CT Studio\n\nIntro.\n\n{progress.START}\nold\n{progress.END}\n\n## More\n"


def write_phase(folder: Path, number: int, title: str, *lines: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    body = "\n".join([f"# Phase {number} — {title}", "", *lines, ""])
    (folder / f"PHASE_{number:02d}_x.md").write_text(body, encoding="utf-8")


def project(tmp_path: Path) -> Path:
    phases = tmp_path / "docs" / "phases"
    write_phase(
        phases,
        3,
        "Project model",
        "### [x] P3-T01 — Manifest",
        "### [X] P3-GATE — Phase review (commit abc)",
        "Text mentioning [ ] P3-T09 is not a task.",
    )
    write_phase(
        phases,
        4,
        "Build engine",
        "### [x] P4-T01 — Node & graph",
        "### [ ] P4-T05 — Assemble node",
        "- [x] **P4-T05a — Assemble without auto-add** (commit 267b996)**:** text",
        "- [ ] **P4-T05b — Auto-add:** text",
        "#### [ ] P4-HC1 — Human check",
        "### [ ] P4-DEEPCLEAN — Deep Clean #1",
    )
    write_phase(phases, 14, "Optional extras", "### [ ] P14-T01 — Only on request")
    (tmp_path / "README.md").write_text(README, encoding="utf-8")
    return tmp_path


def test_counts_tasks_split_parts_and_leaves_out_the_optional_phase(tmp_path: Path) -> None:
    counted = progress.count(project(tmp_path) / "docs" / "phases")
    assert counted.phases == (
        progress.Phase(3, "Project model", 2, 2),
        progress.Phase(4, "Build engine", 2, 5),  # P4-T05 counts as its parts a and b
    )
    assert (counted.done, counted.total) == (4, 7)
    assert counted.current == progress.Phase(4, "Build engine", 2, 5)


def test_render_rounds_down_so_100_means_finished() -> None:
    almost = progress.Progress((progress.Phase(1, "A", 199, 200),))
    text = progress.render(almost)
    assert "`███████████████████░` 99% — 199 of 200 planned tasks done." in text
    assert "Now working on phase 1, A (199 of 200 done)." in text
    finished = progress.render(progress.Progress((progress.Phase(1, "A", 3, 3),)))
    assert "`████████████████████` 100% — 3 of 3" in finished
    assert "Every planned task is done." in finished
    assert text.startswith(progress.START) and text.endswith(progress.END)


def test_main_writes_the_readme_and_check_reports_staleness(tmp_path: Path) -> None:
    root = project(tmp_path)
    assert progress.main(["--check"], root) == 1
    assert (root / "README.md").read_text(encoding="utf-8") == README, "--check changes nothing"
    assert progress.main([], root) == 0
    text = (root / "README.md").read_text(encoding="utf-8")
    assert text.startswith("# CT Studio\n\nIntro.\n\n" + progress.START)
    assert "`███████████░░░░░░░░░` 57% — 4 of 7 planned tasks done." in text
    assert text.endswith(progress.END + "\n\n## More\n")
    assert progress.main(["--check"], root) == 0


@pytest.mark.parametrize(
    ("phase_lines", "readme", "problem"),
    [
        (["### [x] P4-T01 — A", "### [ ] P4-T01 — again"], README, "listed twice"),
        (["### [x] P5-T01 — in the phase 4 file"], README, "wrong phase file"),
        (["### [x] P4-T01 — A"], "# CT Studio\n", "no progress markers"),
        (["### [x] P4-T01 — A"], f"{progress.END}\n{progress.START}\n", "no progress markers"),
    ],
)
def test_bad_files_are_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    phase_lines: list[str],
    readme: str,
    problem: str,
) -> None:
    write_phase(tmp_path / "docs" / "phases", 4, "Build", *phase_lines)
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    assert progress.main([], tmp_path) == 2
    assert problem in capsys.readouterr().err


def test_phases_are_in_number_order_whatever_the_file_names(tmp_path: Path) -> None:
    phases = tmp_path / "docs" / "phases"
    phases.mkdir(parents=True)
    (phases / "PHASE_a.md").write_text("# Phase 10 — Late\n### [ ] P10-T01 — x\n", "utf-8")
    (phases / "PHASE_b.md").write_text("# Phase 9 — Early\n### [ ] P9-T01 — x\n", "utf-8")
    assert [p.number for p in progress.count(phases).phases] == [9, 10]


def test_a_phase_file_needs_its_title(tmp_path: Path) -> None:
    (tmp_path / "docs" / "phases").mkdir(parents=True)
    (tmp_path / "docs" / "phases" / "PHASE_04_x.md").write_text("no title\n", encoding="utf-8")
    with pytest.raises(ValueError, match="first line must be"):
        progress.count(tmp_path / "docs" / "phases")


def test_the_readme_progress_is_current() -> None:
    """Fails the gate (and so blocks the commit) until scripts/progress.py has been run."""
    assert progress.main(["--check"]) == 0, "run: uv run python scripts/progress.py"
