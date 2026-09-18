#!/usr/bin/env python3
"""Spike S3b: compare the two BRRES backends on the fixture DAE (P0-T06b).

    uv run python spikes/s3_backend_bakeoff.py

Standalone dev script, so it may spawn processes directly (AGENTS.md rule 3):
argv list, explicit timeout, explicit exit-code handling, never shell=True.

Writes spikes/out/s3b/s3b_findings.json. Requires the S2 outputs (course DAE +
textures) and, for the rszst half, the Linux build from S3a.
"""

from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WSZST = REPO_ROOT / ".tools" / "wiimms-szs-tools" / "bin" / "wszst"
WIMGT = REPO_ROOT / ".tools" / "wiimms-szs-tools" / "bin" / "wimgt"
ABMATT = REPO_ROOT / ".tools" / "abmatt" / "bin" / "abmatt"
RSZST = REPO_ROOT / ".tools" / "riistudio-build-pinned" / "source" / "cli" / "rszst"
DAE = REPO_ROOT / "spikes" / "out" / "s2" / "course_builtin.dae"
OUT = REPO_ROOT / "spikes" / "out" / "s3b"
TIMEOUT_S = 180


def run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - local pinned tools, argv only
        [str(a) for a in argv],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_S,
        check=False,
    )


def mdl0_name(brres: Path, cwd: Path) -> str | None:
    """The MDL0's name decides which slot file a model may be used as."""
    result = run([WSZST, "list", "--long", brres.name], cwd)
    for line in result.stdout.splitlines():
        if "MDL0" in line:
            return line.split()[2].split("/")[-1]
    return None


def texture_formats(brres: Path, cwd: Path) -> dict[str, dict[str, str]]:
    extract_dir = cwd / f"ex_{brres.stem}"
    shutil.rmtree(extract_dir, ignore_errors=True)
    run([WSZST, "extract", brres.name, "--dest", extract_dir.name, "-o"], cwd)
    textures = sorted((extract_dir / "Textures(NW4R)").glob("*"))
    if not textures:
        return {}
    result = run([WIMGT, "list", *[str(t) for t in textures]], cwd)
    formats: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TEX":
            formats[Path(parts[-1]).name] = {"format": parts[2], "mipmaps": parts[3]}
    return formats


def median_seconds(argv: list[str], cwd: Path, runs: int = 3) -> float:
    timings = []
    for _ in range(runs):
        started = time.monotonic()
        run(argv, cwd)
        timings.append(time.monotonic() - started)
    return round(statistics.median(timings), 3)


def import_both(work: Path) -> list[dict]:
    """Import the same DAE with each backend and describe the results."""
    backends = []

    rszst_out = work / "rszst_course.brres"
    result = run([RSZST, "import-brres", DAE.name, rszst_out.name], work)
    backends.append(
        {
            "backend": "rszst",
            "argv": ["import-brres", DAE.name, rszst_out.name],
            "exit_code": result.returncode,
            "bytes": rszst_out.stat().st_size if rszst_out.exists() else 0,
            "mdl0_name": mdl0_name(rszst_out, work) if rszst_out.exists() else None,
            "textures": texture_formats(rszst_out, work) if rszst_out.exists() else {},
            "median_seconds": median_seconds(
                [RSZST, "import-brres", DAE.name, "bench_r.brres"], work
            ),
        }
    )

    abmatt_out = work / "course_model.brres"
    result = run([ABMATT, "convert", DAE.name, "to", abmatt_out.name, "-o"], work)
    backends.append(
        {
            "backend": "abmatt",
            "argv": ["convert", DAE.name, "to", abmatt_out.name, "-o"],
            "exit_code": result.returncode,
            "bytes": abmatt_out.stat().st_size if abmatt_out.exists() else 0,
            "mdl0_name": mdl0_name(abmatt_out, work) if abmatt_out.exists() else None,
            "textures": texture_formats(abmatt_out, work) if abmatt_out.exists() else {},
            "median_seconds": median_seconds(
                [ABMATT, "convert", DAE.name, "to", "bench_a.brres", "-o"], work
            ),
        }
    )
    return backends


def model_naming(work: Path) -> dict:
    """Who can name an MDL0 `course` / `vrcorn` / `map`, and how."""
    named = work / "rszst_vrcorn.brres"
    rszst_flag = run([RSZST, "import-brres", DAE.name, named.name, "--model-name", "vrcorn"], work)

    # ABMatt takes the name from the SOURCE file stem, with no flag for it.
    shutil.copy(work / DAE.name, work / "vrcorn_xyz.dae")
    from_stem = run([ABMATT, "convert", "vrcorn_xyz.dae", "to", "ab_vrcorn.brres", "-o"], work)

    # It also refuses a `<slot>_model.brres` destination whose stem disagrees.
    mismatch = run([ABMATT, "convert", DAE.name, "to", "map_model.brres", "-o"], work)
    mismatch_text = mismatch.stdout + mismatch.stderr
    reason = next(
        (ln.strip() for ln in mismatch_text.splitlines() if "does not match" in ln),
        mismatch_text.strip().splitlines()[-1] if mismatch_text.strip() else "",
    )
    return {
        "rszst_model_name_flag": {
            "exit_code": rszst_flag.returncode,
            "mdl0_name": mdl0_name(named, work) if named.exists() else None,
        },
        "abmatt_name_from_source_stem": {
            "exit_code": from_stem.returncode,
            "mdl0_name": mdl0_name(work / "ab_vrcorn.brres", work),
        },
        "abmatt_stem_destination_mismatch": {
            "exit_code": mismatch.returncode,
            "message": reason[:120],
            "wrote_file": (work / "map_model.brres").exists(),
        },
    }


def interoperability(work: Path) -> dict:
    """Can each backend read what the other wrote?"""
    abmatt_reads = run([ABMATT, "-b", "rszst_course.brres", "-c", "info"], work)
    rszst_reads = run([RSZST, "brres-to-json", "course_model.brres", "from_abmatt.json"], work)
    rszst_own = run([RSZST, "brres-to-json", "rszst_course.brres", "own.json"], work)
    round_trip = run([RSZST, "json-to-brres", "own.json", "own_rt.brres"], work)
    return {
        "abmatt_reads_rszst": {
            "exit_code": abmatt_reads.returncode,
            "saw_materials": "xlu" in abmatt_reads.stdout,
        },
        "rszst_reads_abmatt": {
            "exit_code": rszst_reads.returncode,
            "error": (rszst_reads.stdout + rszst_reads.stderr).strip().splitlines()[-1][:120],
            "wrote_json": (work / "from_abmatt.json").exists(),
        },
        "rszst_json_round_trip": {
            "to_json_exit": rszst_own.returncode,
            "to_brres_exit": round_trip.returncode,
            "json_bytes": (work / "own.json").stat().st_size if (work / "own.json").exists() else 0,
            "brres_bytes": (work / "own_rt.brres").stat().st_size
            if (work / "own_rt.brres").exists()
            else 0,
        },
    }


def material_control(work: Path) -> dict:
    """ABMatt's command language vs the options rszst exposes on import."""
    # `-c` mangles multi-word commands; a command FILE is the usable path.
    inline = run(
        [ABMATT, "-b", "rszst_course.brres", "-o", "-c", "set material xlu:true for *"], work
    )

    commands = work / "xlu.txt"
    commands.write_text("set material xlu:true for *\n", encoding="utf-8")
    shutil.copy(work / "rszst_course.brres", work / "xlu.brres")
    from_file = run([ABMATT, "-b", "xlu.brres", "-o", "-f", commands.name], work)
    check = run([ABMATT, "-b", "xlu.brres", "-c", "info"], work)

    # A tex0 format change is accepted but does not change the stored format.
    fmt_cmds = work / "fmt.txt"
    fmt_cmds.write_text("set tex0 format:IA8 for fence\n", encoding="utf-8")
    shutil.copy(work / "rszst_course.brres", work / "fmt.brres")
    fmt = run([ABMATT, "-b", "fmt.brres", "-o", "-f", fmt_cmds.name], work)

    mips = {}
    for label, extra in (
        ("default", []),
        ("--mipmaps", ["--mipmaps"]),
        ("--mipmaps --min-mip 8", ["--mipmaps", "--min-mip", "8"]),
    ):
        run([RSZST, "import-brres", DAE.name, "mip.brres", *extra], work)
        mips[label] = texture_formats(work / "mip.brres", work).get("road", {}).get("mipmaps")

    return {
        "abmatt_inline_command_exit": inline.returncode,
        "abmatt_command_file_exit": from_file.returncode,
        "abmatt_xlu_applied": "xlu:1" in check.stdout,
        "abmatt_tex0_format_exit": fmt.returncode,
        "abmatt_tex0_format_changed": (
            texture_formats(work / "fmt.brres", work).get("fence", {}).get("format")
            != texture_formats(work / "rszst_course.brres", work).get("fence", {}).get("format")
        ),
        "rszst_mipmap_counts": mips,
    }


def packs_into_a_track(work: Path) -> dict:
    """Both backends' models must survive `wszst create` + `check`."""
    results = {}
    fixtures = REPO_ROOT / "tests" / "fixtures" / "generated"
    for label, course_model in (("rszst", "rszst_course.brres"), ("abmatt", "course_model.brres")):
        stage = work / f"stage_{label}"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir()
        for name in ("course.kcl", "course.kmp"):
            shutil.copy(fixtures / name, stage / name)
        shutil.copy(work / course_model, stage / "course_model.brres")
        shutil.copy(
            REPO_ROOT / "spikes" / "out" / "s2" / "map_model.brres", stage / "map_model.brres"
        )
        shutil.copy(work / "rszst_vrcorn.brres", stage / "vrcorn_model.brres")
        szs = f"track_{label}.szs"
        create = run([WSZST, "create", stage.name, "--dest", szs, "-o"], work)
        check = run([WSZST, "check", szs], work)
        text = check.stdout + check.stderr
        results[label] = {
            "create_exit": create.returncode,
            "szs_bytes": (work / szs).stat().st_size if (work / szs).exists() else 0,
            "warnings": [ln.strip() for ln in text.splitlines() if "WARNING:" in ln],
            "has_error_marker": "ERROR #" in text,
        }
    return results


def main() -> int:
    for path, hint in (
        (DAE, "spikes/s2_blender.py"),
        (ABMATT, "scripts/bootstrap_tools.py"),
        (RSZST, "the S3a build recipe in docs/dev/SPIKES.md"),
        (WSZST, "scripts/bootstrap_tools.py"),
    ):
        if not path.exists():
            print(f"missing {path}; run {hint}", file=sys.stderr)
            return 1

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    work = OUT / "work"
    work.mkdir()
    shutil.copy(DAE, work / DAE.name)
    for png in DAE.parent.glob("*.png"):
        shutil.copy(png, work / png.name)

    findings = {
        "dae": DAE.name,
        "backends": import_both(work),
        "model_naming": model_naming(work),
        "interoperability": interoperability(work),
        "material_control": material_control(work),
        "packs_into_a_track": packs_into_a_track(work),
    }
    path = OUT / "s3b_findings.json"
    path.write_text(json.dumps(findings, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for backend in findings["backends"]:
        print(
            f"{backend['backend']:7} exit={backend['exit_code']} "
            f"{backend['bytes']:6} B  mdl0={backend['mdl0_name']}  "
            f"{backend['median_seconds']}s"
        )
    print(f"[s3b] findings: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
