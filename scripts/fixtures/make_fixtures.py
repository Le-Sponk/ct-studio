#!/usr/bin/env python3
"""Regenerate every CT Studio test fixture with one command (P0-T03).

    uv run python scripts/fixtures/make_fixtures.py

Runs the Blender generator for both variants and compiles the fixture KMP with wkmpt.
Output goes to tests/fixtures/generated/ (gitignored, see TESTING_STRATEGY section 3).

Standalone dev script, so it may spawn processes directly (AGENTS.md rule 3):
argv lists, explicit timeouts, explicit exit-code handling, never shell=True.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "generated"
BLENDER = REPO_ROOT / ".tools" / "blender" / "blender"
WKMPT = REPO_ROOT / ".tools" / "wiimms-szs-tools" / "bin" / "wkmpt"
GENERATOR = Path(__file__).with_name("make_fixture_blend.py")
KMP_SOURCE = Path(__file__).with_name("course.kmp.txt")

BLENDER_TIMEOUT_S = 300
WKMPT_TIMEOUT_S = 60

# Compiling the fixture KMP reports exactly these, because it has no opening camera
# (deferred to P10-T05). Any other warning means something actually broke.
EXPECTED_KMP_WARNINGS = 2


class FixtureError(RuntimeError):
    """A fixture could not be generated."""


def require_tool(path: Path, name: str) -> None:
    if not path.exists():
        raise FixtureError(
            f"{name} not found at {path}. Run: uv run python scripts/bootstrap_tools.py"
        )


def run(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603  (argv list, no shell)
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise FixtureError(f"{Path(argv[0]).name} timed out after {exc.timeout}s") from exc


def build_blend(out_dir: Path, variant: str) -> None:
    proc = run(
        [
            str(BLENDER),
            "-b",
            "--factory-startup",
            "--python",
            str(GENERATOR),
            "--",
            "--out",
            str(out_dir),
            "--variant",
            variant,
        ],
        BLENDER_TIMEOUT_S,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-15:])
        raise FixtureError(
            f"Blender failed for variant {variant!r} (exit {proc.returncode}):\n{tail}"
        )
    for line in proc.stdout.splitlines():
        if line.startswith("[fixture]"):
            print(f"  {line}")


def build_kmp(out_dir: Path) -> None:
    dest = out_dir / "course.kmp"
    proc = run(
        [str(WKMPT), "encode", str(KMP_SOURCE), "--dest", str(dest), "--overwrite"],
        WKMPT_TIMEOUT_S,
    )
    output = proc.stdout + proc.stderr
    if proc.returncode != 0 or not dest.exists():
        tail = "\n".join(output.splitlines()[-15:])
        raise FixtureError(f"wkmpt encode failed (exit {proc.returncode}):\n{tail}")

    warnings = [ln.strip() for ln in output.splitlines() if "WARNING:" in ln]
    if len(warnings) != EXPECTED_KMP_WARNINGS:
        detail = "\n".join(f"    {w}" for w in warnings)
        raise FixtureError(
            f"wkmpt reported {len(warnings)} warnings, expected {EXPECTED_KMP_WARNINGS} "
            f"(the missing opening camera, deferred to P10-T05):\n{detail}"
        )
    print(
        f"  [fixture] wrote {dest.name} ({dest.stat().st_size} bytes), "
        f"{len(warnings)} expected warning(s)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args(argv)

    require_tool(BLENDER, "Blender")
    require_tool(WKMPT, "wkmpt")

    started = time.monotonic()
    print(f"Generating fixtures into {args.out}")
    try:
        for variant in ("good", "bad"):
            build_blend(args.out, variant)
        build_kmp(args.out)
    except FixtureError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"Done in {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
