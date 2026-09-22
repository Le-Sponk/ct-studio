"""S4 contract tests: preserving external material edits across a regenerate.

Pins the behaviour ADR-012 relies on, measured in P0-T07 against
RiiStudio Alpha 5.11.5 and ABMatt 1.3.2. Findings: docs/dev/SPIKES.md §S4.

These run against the real tools and skip when they are absent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / ".tools"
RSZST = TOOLS / "riistudio-build-pinned" / "source" / "cli" / "rszst"
ABMATT = TOOLS / "abmatt" / "bin" / "abmatt"
WIIMMS_BIN = TOOLS / "wiimms-szs-tools" / "bin"
FIXTURE_DAE = REPO / "spikes" / "out" / "s2" / "course_builtin.dae"

pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.integration,
    pytest.mark.skipif(not RSZST.is_file(), reason="rszst not built (P0-T06a)"),
    pytest.mark.skipif(not ABMATT.is_file(), reason="abmatt not installed"),
    pytest.mark.skipif(not FIXTURE_DAE.is_file(), reason="S2 fixture DAE not generated"),
]

EDIT = "set xlu:true for water\nset cullmode:none for water\nset blend:true for water\n"
EDITED_WATER = {"xlu": "1", "blend": "1", "cullmode": "none"}
PRISTINE_WATER = {"xlu": "0", "blend": "0", "cullmode": "inside"}


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{WIIMMS_BIN}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(  # noqa: S603 - local pinned tools, argv only
        args, cwd=cwd, capture_output=True, text=True, timeout=120, check=False, env=env
    )


def abmatt(work: Path, brres_files: list[str], script: str) -> subprocess.CompletedProcess[str]:
    path = work / "cmd.txt"
    path.write_text(script, encoding="utf-8")
    args = [str(ABMATT)]
    for name in brres_files:
        args += ["-b", name]
    return run([*args, "-f", str(path), "-o"], work)


def water_state(work: Path, brres: str, material: str = "water") -> dict[str, str]:
    result = abmatt(
        work, [brres], "info material xlu\ninfo material blend\ninfo material cullmode\n"
    )
    state: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if line.startswith(">") and f"->{material}\t" in line:
            key, _, value = line.split("\t")[1].partition(":")
            state[key.strip()] = value.strip()
    return state


def textures(work: Path, brres: str) -> list[str]:
    result = abmatt(work, [brres], "info tex0\n")
    return sorted(
        line.split(":")[0].replace("TEX0", "").strip()
        for line in result.stdout.splitlines()
        if line.startswith("TEX0")
    )


def has_srt0(work: Path, brres: str) -> bool:
    return "(SRT0)" in abmatt(work, [brres], "info srt0\n").stdout


def import_brres(work: Path, dae: str, dest: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return run([str(RSZST), "import-brres", dae, dest, "--model-name", "course", *extra], work)


@pytest.fixture
def work(tmp_path: Path) -> Path:
    """Fixture DAE plus textures, with the baseline and edited BRRES built."""
    shutil.copy(FIXTURE_DAE, tmp_path / "course.dae")
    for png in FIXTURE_DAE.parent.glob("*.png"):
        shutil.copy(png, tmp_path / png.name)
    import_brres(tmp_path, "course.dae", "base.brres")
    shutil.copy(tmp_path / "base.brres", tmp_path / "edited.brres")
    abmatt(tmp_path, ["edited.brres"], EDIT)
    return tmp_path


def test_edit_changes_state_and_regenerate_loses_it(work: Path) -> None:
    """The premise: a regenerate discards the user's edit, so something must restore it."""
    assert water_state(work, "base.brres") == PRISTINE_WATER
    assert water_state(work, "edited.brres") == EDITED_WATER
    import_brres(work, "course.dae", "regenerated.brres")
    assert water_state(work, "regenerated.brres") == PRISTINE_WATER


def test_route_a_presets_restore_the_edit(work: Path) -> None:
    dumped = run([str(RSZST), "dump-presets", "edited.brres", "presets"], work)
    assert dumped.returncode == 0
    assert sorted(p.name for p in (work / "presets").glob("*")) == [
        "fence.rspreset",
        "grass.rspreset",
        "road.rspreset",
        "water.rspreset",
    ]
    result = import_brres(work, "course.dae", "out.brres", "--preset-path", "presets")
    assert result.returncode == 0
    assert water_state(work, "out.brres") == EDITED_WATER


def test_route_b_abmatt_copy_paste_restores_the_edit(work: Path) -> None:
    import_brres(work, "course.dae", "out.brres")
    result = abmatt(
        work,
        ["edited.brres", "out.brres"],
        "copy material for * in edited.brres\npaste material for * in out.brres\n",
    )
    assert result.returncode == 0
    assert water_state(work, "out.brres") == EDITED_WATER


def test_route_c_json_merge_restores_the_edit(work: Path) -> None:
    import_brres(work, "course.dae", "out.brres")
    run([str(RSZST), "brres-to-json", "out.brres", "out.json"], work)
    run([str(RSZST), "brres-to-json", "edited.brres", "edited.json"], work)

    base = json.loads((work / "out.json").read_text(encoding="utf-8"))
    edited = json.loads((work / "edited.json").read_text(encoding="utf-8"))
    by_name = {m["name"]: m for m in edited["models"][0]["materials"]}
    for material in base["models"][0]["materials"]:
        source = by_name.get(material["name"])
        if source is None:
            continue
        identity = {k: material[k] for k in ("id", "name")}
        material.update({k: v for k, v in source.items() if k not in ("id", "name")})
        material.update(identity)
    (work / "merged.json").write_text(json.dumps(base), encoding="utf-8")

    shutil.copy(work / "out.bin", work / "merged.bin")
    result = run([str(RSZST), "json-to-brres", "merged.json", "merged.brres"], work)
    assert result.returncode == 0
    assert water_state(work, "merged.brres") == EDITED_WATER


def test_json_to_brres_needs_its_bin_sidecar(work: Path) -> None:
    """The .bin beside the .json holds geometry; without it the write fails loudly."""
    import_brres(work, "course.dae", "out.brres")
    run([str(RSZST), "brres-to-json", "out.brres", "out.json"], work)
    (work / "orphan.json").write_text(
        (work / "out.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    result = run([str(RSZST), "json-to-brres", "orphan.json", "orphan.brres"], work)

    assert result.returncode == 255
    assert not (work / "orphan.brres").exists()
    assert "orphan.bin" in result.stdout + result.stderr


def test_presets_are_matched_by_material_name(work: Path) -> None:
    """A renamed material silently gets no preset: rename = lost edit, exit code still 0."""
    renamed = (work / "course.dae").read_text(encoding="utf-8").replace("water", "waterB")
    (work / "renamed.dae").write_text(renamed, encoding="utf-8")
    shutil.copy(work / "water.png", work / "waterB.png")
    run([str(RSZST), "dump-presets", "edited.brres", "presets"], work)

    result = import_brres(work, "renamed.dae", "out.brres", "--preset-path", "presets")

    assert result.returncode == 0
    assert water_state(work, "out.brres", "waterB") == PRISTINE_WATER


def test_abmatt_paste_to_missing_name_drops_the_texture(work: Path) -> None:
    """Route B's failure mode is destructive: autofix deletes the now-unused texture."""
    renamed = (work / "course.dae").read_text(encoding="utf-8").replace("water", "waterB")
    (work / "renamed.dae").write_text(renamed, encoding="utf-8")
    shutil.copy(work / "water.png", work / "waterB.png")
    import_brres(work, "renamed.dae", "out.brres")
    assert "waterB" in textures(work, "out.brres")

    result = abmatt(
        work,
        ["edited.brres", "out.brres"],
        "copy material for water in edited.brres\npaste material for water in out.brres\n",
    )

    assert result.returncode == 0
    assert "Unused textures" in result.stdout
    # The material kept its new name but now points at a texture that was removed.
    assert "waterB" not in textures(work, "out.brres")
    assert water_state(work, "out.brres", "waterB") == EDITED_WATER


def test_abmatt_autofix_level_flag_is_unusable(work: Path) -> None:
    """`-a 0` would disable the destructive autofix, but the value parses as a command."""
    result = run([str(ABMATT), "-a", "0", "-b", "edited.brres", "-f", str(work / "cmd.txt")], work)

    assert result.returncode != 0
    assert "Unknown command '0'" in result.stdout + result.stderr


def test_srt0_animation_survives_presets_and_copy_but_not_a_material_only_merge(work: Path) -> None:
    """Animations live outside the material list, so a material merge must carry them."""
    shutil.copy(work / "edited.brres", work / "srt.brres")
    abmatt(work, ["srt.brres"], "add srt0 for water\n")
    assert has_srt0(work, "srt.brres")

    run([str(RSZST), "dump-presets", "srt.brres", "presets"], work)
    import_brres(work, "course.dae", "a.brres", "--preset-path", "presets")
    assert has_srt0(work, "a.brres")

    import_brres(work, "course.dae", "b.brres")
    abmatt(
        work,
        ["srt.brres", "b.brres"],
        "copy material for water in srt.brres\npaste material for water in b.brres\n",
    )
    assert has_srt0(work, "b.brres")

    import_brres(work, "course.dae", "c.brres")
    run([str(RSZST), "brres-to-json", "c.brres", "c.json"], work)
    run([str(RSZST), "brres-to-json", "srt.brres", "srt.json"], work)
    base = json.loads((work / "c.json").read_text(encoding="utf-8"))
    source = json.loads((work / "srt.json").read_text(encoding="utf-8"))
    assert base["srts"] == []
    assert len(source["srts"]) == 1

    shutil.copy(work / "c.bin", work / "materials_only.bin")
    (work / "materials_only.json").write_text(json.dumps(base), encoding="utf-8")
    run([str(RSZST), "json-to-brres", "materials_only.json", "materials_only.brres"], work)
    assert not has_srt0(work, "materials_only.brres")

    base["srts"] = source["srts"]
    shutil.copy(work / "c.bin", work / "with_srts.bin")
    (work / "with_srts.json").write_text(json.dumps(base), encoding="utf-8")
    run([str(RSZST), "json-to-brres", "with_srts.json", "with_srts.brres"], work)
    assert has_srt0(work, "with_srts.brres")


def test_no_route_duplicates_textures(work: Path) -> None:
    expected = ["fence", "grass", "road", "water"]
    run([str(RSZST), "dump-presets", "edited.brres", "presets"], work)
    import_brres(work, "course.dae", "a.brres", "--preset-path", "presets")
    import_brres(work, "course.dae", "b.brres")
    abmatt(
        work,
        ["edited.brres", "b.brres"],
        "copy material for * in edited.brres\npaste material for * in b.brres\n",
    )
    assert textures(work, "a.brres") == expected
    assert textures(work, "b.brres") == expected
