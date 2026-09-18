#!/usr/bin/env python3
"""Driver for spike S2: run the headless export probe inside Blender (P0-T05).

    uv run python spikes/s2_blender.py

Standalone dev script, so it may spawn processes directly (AGENTS.md rule 3):
argv list, explicit timeout, explicit exit-code handling, never shell=True.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BLENDER = REPO_ROOT / ".tools" / "blender" / "blender"
TOOLS_BIN = REPO_ROOT / ".tools" / "wiimms-szs-tools" / "bin"
ABMATT_BIN = REPO_ROOT / ".tools" / "abmatt" / "bin"
ADDON_SRC = REPO_ROOT / "vendor" / "blender-mkw-utilities"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "generated" / "fixture_track_good.blend"
PROBE = Path(__file__).with_name("blender_export_spike.py")
OUT = REPO_ROOT / "spikes" / "out" / "s2"

TIMEOUT_S = 600


def main() -> int:
    for path, hint in (
        (BLENDER, "scripts/bootstrap_tools.py"),
        (ADDON_SRC / "__init__.py", "git submodule update --init"),
        (FIXTURE, "scripts/fixtures/make_fixtures.py"),
    ):
        if not path.exists():
            print(f"missing {path}; run {hint}", file=sys.stderr)
            return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # The add-on is imported as a Python package, so the directory name must be a valid
    # module name: "blender-mkw-utilities" has hyphens. Stage it under an importable
    # name, exactly as the P6 bridge will have to.
    staged_parent = OUT / "addon_root"
    staged = staged_parent / "mkw_utilities"
    staged_parent.mkdir()
    shutil.copytree(ADDON_SRC, staged, ignore=shutil.ignore_patterns(".git"))

    argv = [
        str(BLENDER),
        "-b",
        str(FIXTURE),
        "--factory-startup",
        "--python",
        str(PROBE),
        "--",
        "--addon",
        str(staged),
        "--out",
        str(OUT),
        "--tools-bin",
        f"{TOOLS_BIN}{os.pathsep}{ABMATT_BIN}",
    ]
    print(f"$ {' '.join(argv[:6])} ... --addon {staged.name}")
    started = time.monotonic()
    proc = subprocess.run(  # noqa: S603
        argv, capture_output=True, text=True, timeout=TIMEOUT_S, check=False
    )
    elapsed = time.monotonic() - started

    for line in proc.stdout.splitlines():
        if line.startswith("[s2]") or "MKW Utilities" in line or "Error" in line:
            print(line)
    print(f"blender exit={proc.returncode} in {elapsed:.1f}s")

    findings_path = OUT / "s2_findings.json"
    if findings_path.exists():
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        ok = sum(1 for e in findings["exports"] if e["ok"])
        print(f"exports: {ok}/{len(findings['exports'])} succeeded")
    else:
        print("no findings written", file=sys.stderr)
        print(proc.stdout[-3000:])
        print(proc.stderr[-2000:], file=sys.stderr)
        return 1
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
