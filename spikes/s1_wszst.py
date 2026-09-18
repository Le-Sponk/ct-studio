#!/usr/bin/env python3
"""Spike S1: what `wszst` actually does when assembling and checking a track (P0-T04).

Throwaway: this is evidence-gathering, not app code. Findings go to docs/dev/SPIKES.md
and the adapter-ready command table in docs/reference/TOOLS.md. Nothing here is copied
into src/ (AGENTS.md rule 3) - the adapter gets written fresh in P2.

    uv run python spikes/s1_wszst.py

Uses the P0-T03 fixtures, so run scripts/fixtures/make_fixtures.py first.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WSZST = REPO_ROOT / ".tools" / "wiimms-szs-tools" / "bin" / "wszst"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "generated"
WORK = REPO_ROOT / "spikes" / "out" / "s1"

TIMEOUT_S = 120


def run(*argv: str, cwd: Path | None = None) -> dict[str, object]:
    """Run a command, returning everything the adapter will eventually care about."""
    started = time.monotonic()
    proc = subprocess.run(  # noqa: S603  (argv list, no shell)
        [str(a) for a in argv],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        cwd=str(cwd) if cwd else None,
        check=False,
    )
    return {
        "argv": [str(a) for a in argv],
        "exit_code": proc.returncode,
        "seconds": round(time.monotonic() - started, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def show(title: str, result: dict[str, object], *, lines: int = 12) -> None:
    print(f"\n=== {title} ===")
    print(f"$ {' '.join(result['argv'][1:])}")
    print(f"exit={result['exit_code']}  {result['seconds']}s")
    text = (str(result["stdout"]) + str(result["stderr"])).strip()
    for line in text.splitlines()[:lines]:
        print(f"  {line}")
    remaining = len(text.splitlines()) - lines
    if remaining > 0:
        print(f"  ... {remaining} more line(s)")


def build_stage(name: str, files: dict[str, Path]) -> Path:
    """Create a staging directory: the exact shape `wszst create` consumes."""
    stage = WORK / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for target, source in files.items():
        dest = stage / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    return stage


def main() -> int:
    if not WSZST.exists():
        print(f"wszst missing at {WSZST}; run scripts/bootstrap_tools.py", file=sys.stderr)
        return 1
    if not (FIXTURES / "course.kcl").exists():
        print("fixtures missing; run scripts/fixtures/make_fixtures.py", file=sys.stderr)
        return 1

    WORK.mkdir(parents=True, exist_ok=True)
    findings: dict[str, object] = {}

    # A track with only the two files we can currently generate. The BRRES files come
    # from S2/S3, so this deliberately shows how an incomplete track is reported.
    stage = build_stage(
        "minimal",
        {"course.kcl": FIXTURES / "course.kcl", "course.kmp": FIXTURES / "course.kmp"},
    )

    # --- compression levels ------------------------------------------------------
    print("\n########## wszst CREATE: compression levels ##########")
    levels: list[dict[str, object]] = []
    for label, flags in (
        ("default", []),
        ("--fast", ["--fast"]),
        ("--compr=FAST", ["--compr=FAST"]),
        ("--compr=BEST", ["--compr=BEST"]),
        ("--compr=ULTRA", ["--compr=ULTRA"]),
        ("--no-compress", ["--no-compress"]),
    ):
        dest = WORK / f"track_{label.strip('-').replace('=', '_')}.szs"
        result = run(WSZST, "create", stage, "--dest", dest, "--overwrite", *flags)
        size = dest.stat().st_size if dest.exists() else None
        levels.append(
            {
                "label": label,
                "flags": flags,
                "exit": result["exit_code"],
                "seconds": result["seconds"],
                "bytes": size,
            }
        )
        print(f"  {label:16} exit={result['exit_code']}  {result['seconds']:>6}s  {size} bytes")
    findings["compression"] = levels

    szs = WORK / "track_default.szs"

    # --- the other commands ------------------------------------------------------
    print("\n########## the commands an adapter will call ##########")
    for title, argv in (
        ("LIST", (WSZST, "list", szs)),
        ("LIST --long", (WSZST, "list", "--long", szs)),
        ("CHECK", (WSZST, "check", szs)),
        ("SLOTS", (WSZST, "slots", szs)),
    ):
        result = run(*argv)
        findings[title] = result
        show(title, result)

    # --- machine-readable modes: the key open question ---------------------------
    print("\n########## machine-readable output? ##########")
    for title, argv in (
        ("CHECK --sections", (WSZST, "check", "--sections", szs)),
        ("ANALYZE --sections", (WSZST, "analyze", "--sections", szs)),
        ("ANALYZE --json", (WSZST, "analyze", "--json", szs)),
        ("SLOTS --sections", (WSZST, "slots", "--sections", szs)),
    ):
        result = run(*argv)
        findings[title] = result
        show(title, result, lines=16)

    # --- how are missing components reported? ------------------------------------
    print("\n########## an empty stage (nothing but a directory) ##########")
    empty = build_stage("empty", {})
    dest = WORK / "empty.szs"
    findings["create empty"] = run(WSZST, "create", empty, "--dest", dest, "--overwrite")
    show("CREATE (empty dir)", findings["create empty"])
    if dest.exists():
        findings["check empty"] = run(WSZST, "check", dest)
        show("CHECK (empty archive)", findings["check empty"])

    # --- exit codes: the part an adapter must not get wrong -----------------------
    # Placeholder BRRES files: enough for `check` to stop reporting them as missing,
    # not real models (those need S2/S3).
    print("\n########## exit codes ##########")
    placeholder = b"bres\x00\x00\x00\x00"
    full_stage = build_stage(
        "full",
        {"course.kcl": FIXTURES / "course.kcl", "course.kmp": FIXTURES / "course.kmp"},
    )
    for name in ("course_model", "map_model", "vrcorn_model"):
        (full_stage / f"{name}.brres").write_bytes(placeholder)
    full_szs = WORK / "full.szs"
    run(WSZST, "create", full_stage, "--dest", full_szs, "--overwrite")

    corrupt = WORK / "corrupt.szs"
    corrupt.write_bytes(b"not an archive" * 8)

    exit_codes = {}
    for label, target in (
        ("incomplete track (no BRRES)", szs),
        ("track with placeholder BRRES", full_szs),
        ("empty archive", WORK / "empty.szs"),
        ("corrupt file", corrupt),
        ("missing file", WORK / "does-not-exist.szs"),
    ):
        result = run(WSZST, "check", target)
        text = str(result["stdout"]) + str(result["stderr"])
        exit_codes[label] = {
            "exit_code": result["exit_code"],
            "prints_error": "ERROR #" in text,
            "summary": next(
                (ln.strip() for ln in text.splitlines() if ln.strip().startswith("=>")), ""
            ),
        }
        print(
            f"  {label:30} exit={result['exit_code']:<4} "
            f"error_in_output={exit_codes[label]['prints_error']}"
        )
    findings["exit_codes"] = exit_codes

    (WORK / "findings.json").write_text(
        json.dumps(findings, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"\nRaw output saved to {WORK / 'findings.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
