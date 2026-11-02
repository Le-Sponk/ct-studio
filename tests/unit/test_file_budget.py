"""P2-GATE: ``scripts/file_budget.py`` keeps every Python file within 400 lines (AGENTS 8)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check  # scripts added to sys.path above
import file_budget


def _lines(path: Path, count: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * count, encoding="utf-8")
    return path


def test_files_at_the_limit_pass_and_one_line_over_fails(tmp_path: Path) -> None:
    _lines(tmp_path / "src" / "ok é.py", 400)
    over = _lines(tmp_path / "tests" / "unit" / "big.py", 401)
    assert file_budget.over_budget(tmp_path) == [(over, 401)]


def test_only_source_scripts_and_tests_are_counted(tmp_path: Path) -> None:
    for folder in (".venv", ".tools", "local_fixtures", "src/pkg/__pycache__", "build", "docs"):
        _lines(tmp_path / folder / "big.py", 900)
    assert file_budget.over_budget(tmp_path) == []
    nested = _lines(tmp_path / "scripts" / "fixtures" / "big.py", 401)
    assert file_budget.over_budget(tmp_path) == [(nested, 401)]


def test_main_names_each_file_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _lines(tmp_path / "src" / "ok.py", 10)
    assert file_budget.main([str(tmp_path)]) == 0
    _lines(tmp_path / "src" / "big.py", 450)
    assert file_budget.main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "big.py: 450 lines (limit 400)" in out and "ok.py" not in out


def test_the_real_tree_is_within_budget() -> None:
    assert file_budget.over_budget(ROOT) == []


def test_the_gate_runs_it_last_in_both_modes() -> None:
    for fast in (False, True):
        step = check.build_steps(ROOT, fast=fast)[-1]
        assert step.name == "file length"
        assert step.argv[-2:] == (str((ROOT / "scripts" / "file_budget.py").resolve()), str(ROOT))
        assert step.skip_reason is None
