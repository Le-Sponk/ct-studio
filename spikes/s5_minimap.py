"""Spike S5: producing a minimap (`map_model.brres`) headlessly (P0-T08).

Throwaway evidence-gathering. Findings go to docs/dev/SPIKES.md §S5; the real
minimap pipeline is written fresh in P9 (AGENTS.md rule 3).

Three candidate paths, all measured against the same fixture:
  1  KCL -> OBJ filtered to drivable triangles (wkclt --kcl-script) -> ABMatt
  2  Blender DAE -> rszst --model-name map
  3  the add-on's own minimap export (baseline from S2)

Then `wszst minimap --auto` on each, checking for MDL0 `map` and the
`posLD`/`posRU` bones the game needs.

Run:  uv run python spikes/s5_minimap.py
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / ".tools"
RSZST = TOOLS / "riistudio-build-pinned" / "source" / "cli" / "rszst"
ABMATT = TOOLS / "abmatt" / "bin" / "abmatt"
WIIMMS_BIN = TOOLS / "wiimms-szs-tools" / "bin"
S2_OUT = REPO / "spikes" / "out" / "s2"
FIXTURES = REPO / "tests" / "fixtures" / "generated"
OUT = REPO / "spikes" / "out" / "s5"

# Wall-ish and boundary KCL types: they make the minimap outline wrong.
KCL_FILTER = """\
# Minimap filter (spike S5): keep only drivable surfaces.
@def removed = 0

@function isNotDrivable # flag
    @pdef t = $1 & 0x1f
    @return t == 0x0c || t == 0x0d || t == 0x0f || t == 0x10 \\
         || t == 0x14 || t == 0x1e || t == 0x1f
@endfunction

@for t=0;tri$n()-1
    @if isNotDrivable(tri$flag(t))
        @def status = tri$remove(t)
        @def removed = removed+1
    @endif
@endfor

@echo "  - removed " removed " of " tri$n() " triangles (non-drivable)"
"""
TIMEOUT = 180


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{WIIMMS_BIN}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(  # noqa: S603 - local pinned tools, argv only
        args, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT, check=False, env=env
    )


def face_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("f "))


def mdl0_name(work: Path, brres: str) -> str | None:
    """The MDL0 the game looks for. Must be `map` for a minimap."""
    result = run(["wszst", "list", brres], work)
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("3DModels(NW4R)/") and not line.endswith("/"):
            return line.split("/", 1)[1]
    return None


def minimap_report(work: Path, brres: str) -> dict[str, object]:
    """`wszst minimap` prints nothing at all when posLD/posRU are absent."""
    result = run(["wszst", "minimap", brres], work)
    translations = [line for line in result.stdout.splitlines() if "Translation:" in line]
    recommended = [line for line in result.stdout.splitlines() if "Recommend." in line]
    return {
        "exit_code": result.returncode,
        "has_position_bones": bool(translations),
        "translation": translations[0].split(":", 1)[1].split() if translations else [],
        "recommended": recommended[0].split(":", 1)[1].split() if recommended else [],
    }


def bone_names(work: Path, brres: str) -> list[str] | str:
    """Bones via rszst JSON; rszst cannot read every BRRES (S3b wall)."""
    result = run([str(RSZST), "brres-to-json", brres, brres + ".json"], work)
    if result.returncode != 0 or not (work / (brres + ".json")).is_file():
        tail = (result.stdout + result.stderr).strip().splitlines()
        return "unreadable: " + (tail[-1] if tail else "unknown error")
    model = json.loads((work / (brres + ".json")).read_text(encoding="utf-8"))["models"][0]
    return [bone.get("name") for bone in model.get("bones", [])]


def describe(work: Path, brres: str) -> dict[str, object]:
    return {
        "bytes": (work / brres).stat().st_size if (work / brres).is_file() else 0,
        "mdl0": mdl0_name(work, brres),
        "bones": bone_names(work, brres),
        "minimap": minimap_report(work, brres),
    }


def median_seconds(args: list[str], cwd: Path, runs: int = 3) -> float:
    times = []
    for _ in range(runs):
        started = time.monotonic()
        run(args, cwd)
        times.append(time.monotonic() - started)
    return round(statistics.median(times), 3)


def setup(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "course.kcl", work / "course.kcl")
    shutil.copy(S2_OUT / "course_builtin.dae", work / "course_builtin.dae")
    for png in S2_OUT.glob("*.png"):
        shutil.copy(png, work / png.name)
    if (S2_OUT / "map_model.brres").is_file():
        shutil.copy(S2_OUT / "map_model.brres", work / "addon_map.brres")
    (work / "drivable.txt").write_text(KCL_FILTER, encoding="utf-8")


def path_1_kcl_filtered(work: Path) -> dict[str, object]:
    """KCL -> filtered OBJ -> ABMatt, the path that needs no Blender."""
    decoded = run(
        ["wkclt", "decode", "course.kcl", "--dest", "drivable.obj", "--kcl-script", "drivable.txt"],
        work,
    )
    kept = face_count(work / "drivable.obj")
    unfiltered = run(["wkclt", "decode", "course.kcl", "--dest", "full.obj"], work)
    total = face_count(work / "full.obj")

    converted = run([str(ABMATT), "convert", "drivable.obj", "to", "map_model.brres", "-o"], work)
    result = describe(work, "map_model.brres")
    patched = run(["wszst", "minimap", "--auto", "map_model.brres"], work)
    return {
        "decode_exit_code": decoded.returncode,
        "unfiltered_exit_code": unfiltered.returncode,
        "triangles_total": total,
        "triangles_kept": kept,
        "convert_exit_code": converted.returncode,
        "before_auto": result,
        "auto_exit_code": patched.returncode,
        "after_auto": minimap_report(work, "map_model.brres"),
        "seconds_decode": median_seconds(
            [
                "wkclt",
                "decode",
                "course.kcl",
                "--dest",
                "t.obj",
                "--kcl-script",
                "drivable.txt",
                "-o",
            ],
            work,
        ),
        "seconds_convert": median_seconds(
            [str(ABMATT), "convert", "drivable.obj", "to", "t.brres", "-o"], work
        ),
    }


def path_2_rszst(work: Path) -> dict[str, object]:
    """Blender DAE -> rszst with --model-name map."""
    imported = run(
        [
            str(RSZST),
            "import-brres",
            "course_builtin.dae",
            "rszst_map.brres",
            "--model-name",
            "map",
        ],
        work,
    )
    result = describe(work, "rszst_map.brres")
    patched = run(["wszst", "minimap", "--auto", "rszst_map.brres"], work)
    return {
        "import_exit_code": imported.returncode,
        "result": result,
        "auto_exit_code": patched.returncode,
        "after_auto": minimap_report(work, "rszst_map.brres"),
        "seconds_import": median_seconds(
            [str(RSZST), "import-brres", "course_builtin.dae", "t2.brres", "--model-name", "map"],
            work,
        ),
    }


def path_3_addon(work: Path) -> dict[str, object]:
    """The add-on's own minimap export, produced by S2."""
    if not (work / "addon_map.brres").is_file():
        return {"skipped": "spikes/out/s2/map_model.brres missing; run spikes/s2_blender.py"}
    result = describe(work, "addon_map.brres")
    patched = run(["wszst", "minimap", "--auto", "addon_map.brres"], work)
    return {
        "result": result,
        "auto_exit_code": patched.returncode,
        "after_auto": minimap_report(work, "addon_map.brres"),
    }


def naming_rules(work: Path) -> dict[str, object]:
    """Which names make ABMatt emit an MDL0 called `map`, and where the bones come from."""
    observations: dict[str, object] = {}
    for dest in ("map_model2.brres", "vrcorn_model.brres", "MAP.brres", "track.brres"):
        run([str(ABMATT), "convert", "drivable.obj", "to", dest, "-o"], work)
        observations[f"drivable.obj -> {dest}"] = {
            "mdl0": mdl0_name(work, dest),
            "has_position_bones": minimap_report(work, dest)["has_position_bones"],
        }
    # Source stem carrying "map" while the destination does not.
    shutil.copy(work / "drivable.obj", work / "mapsource.obj")
    if (work / "drivable.mtl").is_file():
        shutil.copy(work / "drivable.mtl", work / "mapsource.mtl")
    run([str(ABMATT), "convert", "mapsource.obj", "to", "out1.brres", "-o"], work)
    observations["mapsource.obj -> out1.brres"] = {
        "mdl0": mdl0_name(work, "out1.brres"),
        "has_position_bones": minimap_report(work, "out1.brres")["has_position_bones"],
    }
    # A DAE whose stem does not match a *_model destination crashes ABMatt.
    mismatch = run(
        [str(ABMATT), "convert", "course_builtin.dae", "to", "dae_map_model.brres", "-o"], work
    )
    tail = [line for line in (mismatch.stdout + mismatch.stderr).splitlines() if line.strip()]
    observations["course_builtin.dae -> map_model.brres"] = {
        "exit_code": mismatch.returncode,
        "last_line": tail[-1] if tail else "",
    }
    shutil.copy(work / "course_builtin.dae", work / "map.dae")
    run([str(ABMATT), "convert", "map.dae", "to", "map_from_dae.brres", "-o"], work)
    observations["map.dae -> map_from_dae.brres"] = {
        "mdl0": mdl0_name(work, "map_from_dae.brres"),
        "has_position_bones": minimap_report(work, "map_from_dae.brres")["has_position_bones"],
    }
    return observations


def main() -> int:
    missing = [str(p) for p in (RSZST, ABMATT) if not p.is_file()]
    if missing:
        print("missing tools: " + ", ".join(missing))
        return 1
    if not (FIXTURES / "course.kcl").is_file():
        print("fixture KCL missing; run scripts/fixtures/make_fixtures.py")
        return 1

    work = OUT / "work"
    shutil.rmtree(work, ignore_errors=True)
    setup(work)

    findings = {
        "path_1_kcl_filtered": path_1_kcl_filtered(work),
        "path_2_rszst_dae": path_2_rszst(work),
        "path_3_addon_export": path_3_addon(work),
        "naming_rules": naming_rules(work),
    }

    destination = OUT / "s5_findings.json"
    destination.write_text(json.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(findings, indent=2, sort_keys=True))
    print(f"\nwrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
