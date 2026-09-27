"""The quality gate: `uv run python scripts/check.py [--all] [--fast]`.

Runs, in order: ruff format --check, ruff check, pyright, lint-imports, the fast pytest
selection (with coverage), xenon on `src/ctstudio/core`, vulture. Stops at the first failure
unless `--all`. `--fast` skips pyright and coverage. Prints one line per step with its
duration; a failing step's captured output is printed after its line.

Tools are the ones installed in the running interpreter's environment (`uv sync`), found
next to `sys.executable`, so the gate never depends on PATH. Children get
`PYTHONPATH=<root>/src` so the tree being checked is the one imported, even when a
different checkout is installed editable.

Exit status: 0 all steps passed or were skipped for a stated reason, 1 a step failed,
2 bad arguments.
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import sysconfig
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TextIO

ROOT = Path(__file__).resolve().parents[1]

# The local gate excludes anything needing real tools, minutes of runtime, the human's
# files, or an external endpoint (TESTING_STRATEGY §1; `network` is nightly-only, TD-001).
PYTEST_SELECTION = "not integration and not slow and not realdata and not network"

# Thresholds from P1-T02; REVIEW_CHECKLIST §6 is where they may change (via DECISIONS.md).
XENON_THRESHOLDS = ("--max-absolute", "B", "--max-modules", "A", "--max-average", "A")
VULTURE_MIN_CONFIDENCE = "80"

Status = Literal["PASS", "FAIL", "SKIP"]


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]
    timeout_s: float
    skip_reason: str | None = None


@dataclass(frozen=True)
class Result:
    step: Step
    status: Status
    seconds: float
    output: str


def tool(name: str) -> str:
    """Absolute path of a console script installed alongside the running interpreter."""
    suffix = ".exe" if sys.platform == "win32" else ""
    return str(Path(sysconfig.get_path("scripts")) / f"{name}{suffix}")


def build_steps(root: Path, *, fast: bool) -> list[Step]:
    """The gate's steps for the tree at ``root``, in execution order."""
    pytest_argv = [tool("pytest"), "-q", "-m", PYTEST_SELECTION]
    if not fast:
        pytest_argv += ["--cov=ctstudio", "--cov-report=term"]
    core = root / "src" / "ctstudio" / "core"
    return [
        Step("ruff format", (tool("ruff"), "format", "--check"), 120),
        Step("ruff check", (tool("ruff"), "check"), 120),
        Step("pyright", (tool("pyright"),), 600, "--fast" if fast else None),
        Step("lint-imports", (tool("lint-imports"), "--no-logo"), 300),
        Step("pytest", tuple(pytest_argv), 1200),
        Step(
            "xenon (core)",
            (tool("xenon"), *XENON_THRESHOLDS, str(core)),
            120,
            # xenon exits 0 on a missing path, which would be a silent pass.
            None if core.is_dir() else "src/ctstudio/core does not exist yet (P1-T04)",
        ),
        Step(
            "vulture",
            (
                tool("vulture"),
                str(root / "src"),
                str(root / "vulture_whitelist.py"),
                "--min-confidence",
                VULTURE_MIN_CONFIDENCE,
            ),
            120,
        ),
    ]


def child_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    src = str(root / "src")
    env["PYTHONPATH"] = os.pathsep.join(p for p in (src, env.get("PYTHONPATH")) if p)
    env["PYTHONIOENCODING"] = "utf-8"
    # pyright[nodejs] ships Node in the dev group. Use that wheel, not a random
    # globally installed Node or a network bootstrap on a fresh CI runner.
    env["PYRIGHT_PYTHON_GLOBAL_NODE"] = "false"
    return env


def run_step(step: Step, root: Path) -> Result:
    if step.skip_reason is not None:
        return Result(step, "SKIP", 0.0, step.skip_reason)
    started = time.perf_counter()
    try:
        proc = subprocess.run(  # noqa: S603 - argv list of our own venv's tools, no shell
            step.argv,
            cwd=root,
            env=child_env(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=step.timeout_s,
            check=False,
        )
    except FileNotFoundError:
        output = f"{step.argv[0]} is not installed. Run `uv sync` and try again."
        return Result(step, "FAIL", time.perf_counter() - started, output)
    except subprocess.TimeoutExpired:
        output = f"timed out after {step.timeout_s:.0f} s: {' '.join(step.argv)}"
        return Result(step, "FAIL", time.perf_counter() - started, output)
    status: Status = "PASS" if proc.returncode == 0 else "FAIL"
    output = (proc.stdout + proc.stderr).strip()
    if status == "FAIL":
        output += f"\n[exit status {proc.returncode}]"
    return Result(step, status, time.perf_counter() - started, output)


def summary_line(result: Result) -> str:
    lines = [line.strip() for line in result.output.splitlines() if line.strip()]
    detail = lines[-1] if lines and result.status != "FAIL" else ""
    if result.status == "SKIP":
        detail = f"skipped: {result.output}"
    text = f"{result.status}  {result.step.name:<14} {result.seconds:6.1f} s  {detail}"
    return text.rstrip()


def run_all(steps: Sequence[Step], root: Path, *, keep_going: bool, out: TextIO) -> int:
    """Run ``steps`` in order, print a line each, and return the process exit status."""
    failed: list[str] = []
    for step in steps:
        result = run_step(step, root)
        print(summary_line(result), file=out, flush=True)
        if result.status != "FAIL":
            continue
        print(result.output, file=out, flush=True)
        failed.append(step.name)
        if not keep_going:
            break
    ran = "all steps" if keep_going or not failed else "stopped at first failure"
    verdict = f"FAILED: {', '.join(failed)}" if failed else "OK"
    print(f"check.py: {verdict} ({ran})", file=out, flush=True)
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the CT Studio quality gate.")
    parser.add_argument("--all", action="store_true", help="run every step even after a failure")
    parser.add_argument("--fast", action="store_true", help="skip pyright and coverage")
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        # Tool output may hold characters the console code page cannot encode (cp850).
        sys.stdout.reconfigure(errors="replace")
    steps = build_steps(ROOT, fast=args.fast)
    return run_all(steps, ROOT, keep_going=args.all, out=sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
