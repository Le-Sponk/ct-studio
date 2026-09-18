"""Spike S2: headless export entry points in Blender-MKW-Utilities (P0-T05).

Throwaway evidence-gathering. Findings go to docs/dev/SPIKES.md §S2; the real bridge
(`src/ctstudio/blender_bridge/run_job.py`) is written fresh in P6 (AGENTS.md rule 3).

Runs *inside* Blender:

    blender -b FIXTURE.blend --factory-startup --python spikes/blender_export_spike.py \
        -- --addon vendor/blender-mkw-utilities --out spikes/out/s2

Driven by spikes/s2_blender.py, which is the thing you actually run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

import bpy


def parse_args(argv: list[str]) -> argparse.Namespace:
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon", required=True, type=Path, help="add-on directory")
    parser.add_argument("--out", required=True, type=Path, help="output directory")
    parser.add_argument("--tools-bin", type=Path, help="directory to prepend to PATH")
    return parser.parse_args(argv)


def register_addon(addon_dir: Path) -> dict[str, object]:
    """Register the add-on straight from its checkout, the way the bridge will.

    The add-on is a package directory, so its *parent* goes on sys.path and the
    directory name is the module name.
    """
    sys.path.insert(0, str(addon_dir.parent))
    module = __import__(addon_dir.name)
    module.register()
    return {
        "module": addon_dir.name,
        "bl_info_version": getattr(module, "bl_info", {}).get("version"),
        "registered": True,
    }


def collection_objects(name: str) -> list[bpy.types.Object]:
    return list(bpy.data.collections[name].objects) if name in bpy.data.collections else []


def select_only(objects: list[bpy.types.Object]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


def attempt(name: str, fn) -> dict[str, object]:
    """Run one export, capturing what an adapter needs to know when it fails."""
    started = time.monotonic()
    record: dict[str, object] = {"name": name}
    try:
        result = fn()
        record["result"] = sorted(result) if isinstance(result, set) else str(result)
        record["ok"] = True
    except Exception as exc:  # a spike records failures; it does not handle them
        record["ok"] = False
        record["error_type"] = type(exc).__name__
        record["error"] = str(exc)
        record["traceback"] = traceback.format_exc().splitlines()[-3:]
    record["seconds"] = round(time.monotonic() - started, 3)
    return record


def main() -> int:
    args = parse_args(sys.argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    if args.tools_bin:
        os.environ["PATH"] = f"{args.tools_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    findings: dict[str, object] = {
        "blender": bpy.app.version_string,
        "blend_file": bpy.data.filepath,
        "path_has_tools": bool(args.tools_bin),
    }
    findings["addon"] = register_addon(args.addon)

    # What the add-on exposes once registered: the bridge needs stable operator names.
    findings["export_operators"] = sorted(
        op
        for group in ("kcl", "export", "export_scene")
        for op in (f"{group}.{name}" for name in dir(getattr(bpy.ops, group)))
        if any(k in op for k in ("export", "minimap", "dae", "objkcl"))
    )

    exports: list[dict[str, object]] = []

    # --- KCL: the one export we already know works (P0-T03) ---------------------
    kcl_objects = collection_objects("KCL")
    for mode in ("LOWER", "NONE"):
        select_only(kcl_objects)
        dest = out / f"course_{mode.lower()}.kcl"
        record = attempt(
            f"kcl.export unBeanCorner={mode}",
            lambda d=dest, m=mode: bpy.ops.kcl.export(
                filepath=str(d), kclExportScale=100.0, kclExportUnBeanCorner=m
            ),
        )
        record["output_exists"] = dest.exists()
        record["output_bytes"] = dest.stat().st_size if dest.exists() else 0
        exports.append(record)

    # --- DAE: the course model path, needed by S3 -------------------------------
    course_objects = collection_objects("Course")
    for method in ("AUTO", "BUILTIN"):
        select_only(course_objects)
        dest = out / f"course_{method.lower()}.dae"
        record = attempt(
            f"export.autodesk_dae method={method}",
            lambda d=dest, m=method: bpy.ops.export.autodesk_dae(
                filepath=str(d),
                daeExportScale=100.0,
                daeExportSelection=True,
                daeExportMethod=m,
                daeExportCopyTextures=True,
            ),
        )
        record["output_exists"] = dest.exists()
        record["output_bytes"] = dest.stat().st_size if dest.exists() else 0
        record["sidecar_files"] = sorted(
            p.name for p in out.glob("*") if p.suffix.lower() in {".png", ".jpg"}
        )
        exports.append(record)

    # --- OBJ: the exporter the KCL path uses internally -------------------------
    select_only(kcl_objects)
    dest = out / "course.obj"
    record = attempt(
        "export_scene.objkcl",
        lambda d=dest: bpy.ops.export_scene.objkcl(
            filepath=str(d),
            use_selection=True,
            use_materials=False,
            use_normals=True,
            use_triangles=True,
            global_scale=100.0,
        ),
    )
    record["output_exists"] = dest.exists()
    record["output_bytes"] = dest.stat().st_size if dest.exists() else 0
    exports.append(record)

    # --- Minimap BRRES: needs ABMatt on PATH ------------------------------------
    select_only(kcl_objects)
    dest = out / "map_model.brres"
    record = attempt(
        "export.minimap",
        lambda d=dest: bpy.ops.export.minimap(
            filepath=str(d), exportScale=100.0, exportSelection=True
        ),
    )
    record["output_exists"] = dest.exists()
    record["output_bytes"] = dest.stat().st_size if dest.exists() else 0
    exports.append(record)

    findings["exports"] = exports

    # --- did the un-bean modes actually change the output? ----------------------
    # Same triangle count either way, so compare bytes rather than size.
    kcl_hashes = {
        mode: hashlib.sha256((out / f"course_{mode}.kcl").read_bytes()).hexdigest()
        if (out / f"course_{mode}.kcl").exists()
        else None
        for mode in ("lower", "none")
    }
    findings["kcl_unbean_differs"] = (
        kcl_hashes["lower"] is not None and kcl_hashes["lower"] != kcl_hashes["none"]
    )
    findings["kcl_hashes"] = kcl_hashes

    # --- DAE methods: AUTO falls back to the built-in writer without FbxConverter -
    dae_hashes = {
        method: hashlib.sha256((out / f"course_{method}.dae").read_bytes()).hexdigest()
        if (out / f"course_{method}.dae").exists()
        else None
        for method in ("auto", "builtin")
    }
    findings["dae_auto_equals_builtin"] = dae_hashes["auto"] == dae_hashes["builtin"]
    findings["dae_sidecar_textures"] = sorted(p.name for p in out.glob("*.png"))

    # --- operator vs internal function -----------------------------------------
    # The bridge could call internals to dodge context requirements; check whether the
    # operators even need a context in background mode.
    findings["context_notes"] = {
        "background": bpy.app.background,
        "active_object": bpy.context.view_layer.objects.active.name
        if bpy.context.view_layer.objects.active
        else None,
    }

    (out / "s2_findings.json").write_text(
        json.dumps(findings, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for record in exports:
        status = "ok " if record.get("ok") else "FAIL"
        size = record.get("output_bytes", 0)
        print(f"[s2] {status} {record['name']:42} {record['seconds']:>6}s  {size} bytes")
        if not record.get("ok"):
            print(f"[s2]      {record.get('error_type')}: {str(record.get('error'))[:120]}")
    print(f"[s2] findings: {out / 's2_findings.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
