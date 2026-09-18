"""Spike S4: preserving external material edits across a regenerate (P0-T07).

Throwaway evidence-gathering. Findings go to docs/dev/SPIKES.md §S4; the real
capture/reapply code is written fresh in P7 (AGENTS.md rule 3).

The question ADR-012 needs answered: when a user edits a generated BRRES in
BrawlCrate/RiiStudio and we then regenerate the model from the DAE, which
mechanism restores their material edits?

Three candidate routes, each measured on the same fixture:
  A  rszst dump-presets -> import-brres --preset-path
  B  ABMatt copy/paste material between two BRRES files
  C  rszst brres-to-json -> merge materials in Python -> json-to-brres

Run:  uv run python spikes/s4_material_edits.py
"""

from __future__ import annotations

import json
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
OUT = REPO / "spikes" / "out" / "s4"

# The edit a user might make in BrawlCrate: make water translucent, unculled.
EDIT_COMMANDS = "set xlu:true for water\nset cullmode:none for water\nset blend:true for water\n"
TIMEOUT = 120


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a tool with ABMatt's wimgt dependency on PATH."""
    import os

    env = dict(os.environ)
    env["PATH"] = f"{WIIMMS_BIN}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(  # noqa: S603 - local pinned tools, argv only
        args, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT, check=False, env=env
    )


def abmatt_script(
    work: Path, brres_files: list[str], script: str
) -> subprocess.CompletedProcess[str]:
    """ABMatt only accepts multi-word commands from a file, never -c."""
    path = work / "commands.txt"
    path.write_text(script, encoding="utf-8")
    args = [str(ABMATT)]
    for brres in brres_files:
        args += ["-b", brres]
    return run([*args, "-f", str(path), "-o"], work)


def material_state(work: Path, brres: str) -> dict[str, dict[str, str]]:
    """Read material flags back out of a file. Never trust an exit code alone."""
    result = abmatt_script(
        work, [brres], "info material xlu\ninfo material blend\ninfo material cullmode\n"
    )
    state: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines():
        if not line.startswith(">") or "\t" not in line:
            continue
        name = line.split("->")[-1].split("\t")[0].strip()
        key, _, value = line.split("\t")[1].partition(":")
        state.setdefault(name, {})[key.strip()] = value.strip()
    return state


def has_srt0(work: Path, brres: str) -> bool:
    result = abmatt_script(work, [brres], "info srt0\n")
    return "(SRT0)" in result.stdout


def texture_names(work: Path, brres: str) -> list[str]:
    result = abmatt_script(work, [brres], "info tex0\n")
    return sorted(
        line.split(":")[0].replace("TEX0", "").strip()
        for line in result.stdout.splitlines()
        if line.startswith("TEX0")
    )


def median_seconds(args: list[str], cwd: Path, runs: int = 5) -> float:
    times = []
    for _ in range(runs):
        started = time.monotonic()
        run(args, cwd)
        times.append(time.monotonic() - started)
    return round(statistics.median(times), 3)


def merge_materials(base_json: Path, edited_json: Path, dest: Path, carry_animations: bool) -> int:
    """Route C: copy material state by name, keeping the regenerated identity fields."""
    base = json.loads(base_json.read_text(encoding="utf-8"))
    edited = json.loads(edited_json.read_text(encoding="utf-8"))
    edited_materials = {m["name"]: m for m in edited["models"][0]["materials"]}
    merged = 0
    for material in base["models"][0]["materials"]:
        source = edited_materials.get(material["name"])
        if source is None:
            continue
        identity = {key: material[key] for key in ("id", "name")}
        material.update({k: v for k, v in source.items() if k not in ("id", "name")})
        material.update(identity)
        merged += 1
    if carry_animations:
        base["srts"] = edited.get("srts", [])
    dest.write_text(json.dumps(base), encoding="utf-8")
    return merged


def setup(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    for name in ("course_builtin.dae",):
        shutil.copy(S2_OUT / name, work / name)
    for png in S2_OUT.glob("*.png"):
        shutil.copy(png, work / png.name)
    # A regenerate where the user also renamed a material in Blender.
    renamed = (work / "course_builtin.dae").read_text(encoding="utf-8").replace("water", "waterB")
    (work / "course_renamed.dae").write_text(renamed, encoding="utf-8")
    shutil.copy(work / "water.png", work / "waterB.png")


def build_baseline(work: Path) -> dict[str, object]:
    """Generate the BRRES, then apply the 'external' edit to a copy of it."""
    run(
        [str(RSZST), "import-brres", "course_builtin.dae", "base.brres", "--model-name", "course"],
        work,
    )
    shutil.copy(work / "base.brres", work / "edited.brres")
    abmatt_script(work, ["edited.brres"], EDIT_COMMANDS)
    before = material_state(work, "base.brres")["water"]
    after = material_state(work, "edited.brres")["water"]
    return {"water_before": before, "water_after": after, "edit_applied": before != after}


def route_a(work: Path) -> dict[str, object]:
    """rszst presets: dump from the edited file, replay at import time."""
    run([str(RSZST), "dump-presets", "edited.brres", "presets"], work)
    presets = sorted(p.name for p in (work / "presets").glob("*"))
    run(
        [
            *[str(RSZST), "import-brres", "course_builtin.dae", "route_a.brres"],
            "--model-name",
            "course",
            "--preset-path",
            "presets",
        ],
        work,
    )
    renamed = run(
        [
            *[str(RSZST), "import-brres", "course_renamed.dae", "route_a_renamed.brres"],
            "--model-name",
            "course",
            "--preset-path",
            "presets",
        ],
        work,
    )
    return {
        "preset_files": presets,
        "restored": material_state(work, "route_a.brres")["water"],
        "textures": texture_names(work, "route_a.brres"),
        "renamed_material_restored": material_state(work, "route_a_renamed.brres")["waterB"],
        "renamed_exit_code": renamed.returncode,
        "seconds_dump": median_seconds(
            [str(RSZST), "dump-presets", "edited.brres", "presets_t"], work
        ),
        "seconds_import": median_seconds(
            [
                *[str(RSZST), "import-brres", "course_builtin.dae", "t_a.brres"],
                "--model-name",
                "course",
                "--preset-path",
                "presets",
            ],
            work,
        ),
    }


def route_b(work: Path) -> dict[str, object]:
    """ABMatt copy/paste between two open BRRES files."""
    run(
        [
            str(RSZST),
            "import-brres",
            "course_builtin.dae",
            "route_b.brres",
            "--model-name",
            "course",
        ],
        work,
    )
    paste = abmatt_script(
        work,
        ["edited.brres", "route_b.brres"],
        "copy material for * in edited.brres\npaste material for * in route_b.brres\n",
    )
    run(
        [
            str(RSZST),
            "import-brres",
            "course_renamed.dae",
            "route_b_renamed.brres",
            "--model-name",
            "course",
        ],
        work,
    )
    renamed = abmatt_script(
        work,
        ["edited.brres", "route_b_renamed.brres"],
        "copy material for water in edited.brres\n"
        "paste material for water in route_b_renamed.brres\n",
    )
    return {
        "restored": material_state(work, "route_b.brres")["water"],
        "textures": texture_names(work, "route_b.brres"),
        "renamed_state": material_state(work, "route_b_renamed.brres"),
        "renamed_textures": texture_names(work, "route_b_renamed.brres"),
        "renamed_autofix_note": "Unused textures" in renamed.stdout,
        "seconds": median_seconds(
            [
                str(ABMATT),
                "-b",
                "edited.brres",
                "-b",
                "route_b.brres",
                "-f",
                str(work / "commands.txt"),
                "-o",
            ],
            work,
            runs=3,
        ),
        "paste_ok": paste.returncode == 0,
    }


def route_c(work: Path) -> dict[str, object]:
    """JSON round-trip with a per-material merge done in Python."""
    run(
        [
            str(RSZST),
            "import-brres",
            "course_builtin.dae",
            "route_c.brres",
            "--model-name",
            "course",
        ],
        work,
    )
    run([str(RSZST), "brres-to-json", "route_c.brres", "route_c.json"], work)
    run([str(RSZST), "brres-to-json", "edited.brres", "edited.json"], work)
    merged = merge_materials(
        work / "route_c.json",
        work / "edited.json",
        work / "route_c_merged.json",
        carry_animations=False,
    )
    # json-to-brres reads <stem>.bin beside the json; it is the geometry buffer.
    shutil.copy(work / "route_c.bin", work / "route_c_merged.bin")
    written = run([str(RSZST), "json-to-brres", "route_c_merged.json", "route_c.brres"], work)
    (work / "no_sidecar.json").write_text(
        (work / "route_c_merged.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    missing_bin = run([str(RSZST), "json-to-brres", "no_sidecar.json", "no_sidecar.brres"], work)
    return {
        "materials_merged": merged,
        "restored": material_state(work, "route_c.brres")["water"],
        "textures": texture_names(work, "route_c.brres"),
        "exit_code": written.returncode,
        "missing_sidecar_exit_code": missing_bin.returncode,
        "missing_sidecar_wrote_file": (work / "no_sidecar.brres").exists(),
        "seconds_dump": median_seconds(
            [str(RSZST), "brres-to-json", "edited.brres", "t.json"], work
        ),
        "seconds_write": median_seconds(
            [str(RSZST), "json-to-brres", "route_c_merged.json", "t_c.brres"], work
        ),
    }


def animation_survival(work: Path) -> dict[str, object]:
    """Does each route carry an SRT0 animation through a regenerate?"""
    shutil.copy(work / "edited.brres", work / "srt.brres")
    abmatt_script(work, ["srt.brres"], "add srt0 for water\n")
    authored = has_srt0(work, "srt.brres")

    run([str(RSZST), "dump-presets", "srt.brres", "presets_srt"], work)
    run(
        [
            *[str(RSZST), "import-brres", "course_builtin.dae", "srt_a.brres"],
            "--model-name",
            "course",
            "--preset-path",
            "presets_srt",
        ],
        work,
    )

    run(
        [str(RSZST), "import-brres", "course_builtin.dae", "srt_b.brres", "--model-name", "course"],
        work,
    )
    abmatt_script(
        work,
        ["srt.brres", "srt_b.brres"],
        "copy material for water in srt.brres\npaste material for water in srt_b.brres\n",
    )

    run(
        [str(RSZST), "import-brres", "course_builtin.dae", "srt_c.brres", "--model-name", "course"],
        work,
    )
    run([str(RSZST), "brres-to-json", "srt_c.brres", "srt_c.json"], work)
    run([str(RSZST), "brres-to-json", "srt.brres", "srt_src.json"], work)
    for carry, stem in ((False, "srt_c_mat"), (True, "srt_c_full")):
        merge_materials(
            work / "srt_c.json",
            work / "srt_src.json",
            work / f"{stem}.json",
            carry_animations=carry,
        )
        shutil.copy(work / "srt_c.bin", work / f"{stem}.bin")
        run([str(RSZST), "json-to-brres", f"{stem}.json", f"{stem}.brres"], work)

    return {
        "authored_headlessly": authored,
        "route_a_presets": has_srt0(work, "srt_a.brres"),
        "route_b_copy_paste": has_srt0(work, "srt_b.brres"),
        "route_c_materials_only": has_srt0(work, "srt_c_mat.brres"),
        "route_c_with_srts": has_srt0(work, "srt_c_full.brres"),
    }


def main() -> int:
    if not RSZST.is_file() or not ABMATT.is_file():
        print("rszst or abmatt missing from .tools/; run scripts/bootstrap_tools.py and P0-T06a")
        return 1

    work = OUT / "work"
    shutil.rmtree(work, ignore_errors=True)
    setup(work)

    findings: dict[str, object] = {"baseline": build_baseline(work)}
    findings["route_a_presets"] = route_a(work)
    findings["route_b_abmatt_copy"] = route_b(work)
    findings["route_c_json_merge"] = route_c(work)
    findings["animations"] = animation_survival(work)

    destination = OUT / "s4_findings.json"
    destination.write_text(json.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(findings, indent=2, sort_keys=True))
    print(f"\nwrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
