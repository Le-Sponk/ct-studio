"""Behavioural tests for scripts/check.py (P1-T02): real subprocesses, not mocks.

The copied-tree tests are deliberately independent of the checkout's tool state: the
`check.py` under test discovers the tools in this interpreter's venv, then uses `cwd`
and `PYTHONPATH` to check and import only the scratch tree.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check  # scripts added to sys.path above; E402 disabled project-wide

pytestmark = pytest.mark.timeout(90)


def _sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "scratch é with spaces"
    root.mkdir()
    shutil.copytree(ROOT / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (root / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts" / "check.py", root / "scripts" / "check.py")
    for name in ("pyproject.toml", ".importlinter", "vulture_whitelist.py"):
        shutil.copy2(ROOT / name, root / name)
    (root / "tests").mkdir()
    return root


def _run_copy(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - our own interpreter, argv list, scratch script
        [sys.executable, str(root / "scripts" / "check.py"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def test_steps_match_the_gate_and_fast_only_skips_typecheck_and_coverage() -> None:
    normal = check.build_steps(ROOT, fast=False)
    fast = check.build_steps(ROOT, fast=True)
    assert [s.name for s in normal] == [
        "ruff format",
        "ruff check",
        "pyright",
        "lint-imports",
        "pytest",
        "xenon (core)",
        "vulture",
    ]
    assert [s.name for s in fast] == [s.name for s in normal]
    assert fast[2].skip_reason == "--fast"
    assert normal[2].skip_reason is None
    assert "--cov=ctstudio" in normal[4].argv
    assert "--cov=ctstudio" not in fast[4].argv
    assert normal[4].argv[3] == check.PYTEST_SELECTION
    assert normal[5].skip_reason == "src/ctstudio/core does not exist yet (P1-T04)"
    assert all(s.timeout_s > 0 for s in normal)


def test_fail_fast_and_all_execute_real_steps(tmp_path: Path) -> None:
    bad = check.Step("bad", (sys.executable, "-c", "import sys; sys.exit(7)"), 5)
    good = check.Step("good", (sys.executable, "-c", "print('healthy')"), 5)
    out = io.StringIO()
    assert check.run_all([bad, good], tmp_path, keep_going=False, out=out) == 1
    assert "FAIL  bad" in out.getvalue() and "good" not in out.getvalue()
    assert "exit status 7" in out.getvalue()

    out = io.StringIO()
    assert check.run_all([bad, good], tmp_path, keep_going=True, out=out) == 1
    assert "FAIL  bad" in out.getvalue() and "PASS  good" in out.getvalue()
    assert "healthy" in out.getvalue()


def test_missing_executable_and_timeout_fail_loudly(tmp_path: Path) -> None:
    missing = check.Step("missing", (str(tmp_path / "no-such-program"),), 2)
    timed = check.Step("timed", (sys.executable, "-c", "import time; time.sleep(2)"), 0.1)
    for step, expected in ((missing, "uv sync"), (timed, "timed out")):
        result = check.run_step(step, tmp_path)
        assert result.status == "FAIL"
        assert expected in result.output


def test_broken_sample_fails_the_actual_gate(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    # A real broken source file: ruff must fail before any later step runs.
    (root / "src" / "ctstudio" / "broken.py").write_text("def f(:\n", encoding="utf-8")
    proc = _run_copy(root)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "FAIL  ruff format" in proc.stdout
    assert "pyright" not in proc.stdout
    assert "check.py: FAILED" in proc.stdout


def test_all_runs_past_a_broken_step_and_fast_skips_pyright(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    (root / "src" / "ctstudio" / "broken.py").write_text("import os\n", encoding="utf-8")
    (root / "tests" / "test_local.py").write_text(
        "def test_local():\n    assert True\n", encoding="utf-8"
    )
    proc = _run_copy(root, "--fast", "--all")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "PASS  ruff format" in proc.stdout
    assert "SKIP  pyright" in proc.stdout
    assert "FAIL  ruff check" in proc.stdout
    assert "PASS  lint-imports" in proc.stdout
    assert "PASS  pytest" in proc.stdout  # no selected tests in this sandbox
    assert "check.py: FAILED" in proc.stdout


def test_network_and_integration_tests_are_deselected(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    (root / "tests" / "test_selection.py").write_text(
        "import pytest\n\n"
        "pytestmark = pytest.mark.timeout(10)\n\n\n"
        "def test_local():\n    assert True\n\n\n"
        "@pytest.mark.network\n"
        'def test_external():\n    raise AssertionError("network test was collected")\n\n\n'
        "@pytest.mark.integration\n"
        'def test_tools():\n    raise AssertionError("integration test was collected")\n',
        encoding="utf-8",
    )
    proc = _run_copy(root, "--fast")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 passed, 2 deselected" in proc.stdout
    assert "SKIP  pyright" in proc.stdout
    assert "SKIP  xenon (core)" in proc.stdout
    assert "check.py: OK" in proc.stdout
