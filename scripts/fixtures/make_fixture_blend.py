"""Build the synthetic fixture .blend (P0-T03).

Run inside Blender:

    blender -b --factory-startup --python scripts/fixtures/make_fixture_blend.py -- --out DIR

Produces a deterministic track-shaped project with the three collections the pipeline
cares about (Course, KCL, Skybox), the textures from make_textures.py, and a manifest
describing what was generated so tests assert against data instead of hard-coded numbers.

No Nintendo assets: every mesh and texture is generated here (AGENTS.md rule 7).

Geometry is in Blender units; the add-on exports at scale 100 (verified in its source,
`kclExportScale` default). The ring is sized so that the exported extent stays well
inside the +/-131071 game coordinate limit documented in MKW_DOMAIN.md section 4.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_textures import NON_POWER_OF_TWO, generate_textures

# --- constants -------------------------------------------------------------------

EXPORT_SCALE = 100.0  # add-on default (kclExportScale); see TOOLS.md
GAME_COORD_LIMIT = 131071  # MKW_DOMAIN.md section 4

RING_RADIUS = 120.0  # Blender units -> 12000 game units after scale
ROAD_HALF_WIDTH = 14.0
RING_SEGMENTS = 48  # keeps the fixture small but still a closed loop

# KCL flags. Values are the add-on's own labelDict base types (T00 ROAD, T03 OFFROAD,
# T0C WALL, T06 BOOST_PANEL, T10 FALL_BOUNDARY) encoded as the 4 hex digits the
# exporter expects after "_F". Read from the add-on source, never typed from memory.
KCL_FLAGS: dict[str, str] = {
    "road": "0000",  # T00 road
    "offroad": "0003",  # T03 off-road
    "wall": "000C",  # T0C wall
    "boost": "0006",  # T06 boost panel
    "fall": "0010",  # T10 fall boundary
}

COLLECTIONS = ("Course", "KCL", "Skybox")


# --- helpers ---------------------------------------------------------------------


def reset_scene() -> None:
    """Empty the factory-startup scene so output does not depend on Blender's defaults."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def new_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def mesh_from_data(
    name: str,
    verts: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def make_material(name: str, image: bpy.types.Image | None, blend: str) -> bpy.types.Material:
    """Material with one image texture; blend method marks the transparency intent."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes["Principled BSDF"]
    if image is not None:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.location = (-320, 260)
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    # Blender 4.2+ renamed the EEVEE blend properties; set whichever exists.
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "BLENDED" if blend != "OPAQUE" else "DITHERED"
    elif hasattr(material, "blend_method"):
        material.blend_method = blend
    return material


def ring_strip(
    radius: float, half_width: float, z: float, segments: int
) -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]:
    """A closed annulus: the drivable ring used for both the model and the collision."""
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        verts.append(((radius - half_width) * cos_a, (radius - half_width) * sin_a, z))
        verts.append(((radius + half_width) * cos_a, (radius + half_width) * sin_a, z))
    for i in range(segments):
        inner, outer = 2 * i, 2 * i + 1
        next_inner, next_outer = (2 * ((i + 1) % segments), 2 * ((i + 1) % segments) + 1)
        faces.append((inner, outer, next_outer, next_inner))
    return verts, faces


def ring_wall(
    radius: float, height: float, segments: int, z: float = 0.0
) -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]:
    """Vertical band around the ring, used for the wall collision."""
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        verts.append((radius * cos_a, radius * sin_a, z))
        verts.append((radius * cos_a, radius * sin_a, z + height))
    for i in range(segments):
        low, high = 2 * i, 2 * i + 1
        next_low, next_high = (2 * ((i + 1) % segments), 2 * ((i + 1) % segments) + 1)
        faces.append((low, next_low, next_high, high))
    return verts, faces


def quad(
    cx: float, cy: float, z: float, half_x: float, half_y: float
) -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]:
    verts = [
        (cx - half_x, cy - half_y, z),
        (cx + half_x, cy - half_y, z),
        (cx + half_x, cy + half_y, z),
        (cx - half_x, cy + half_y, z),
    ]
    return verts, [(0, 1, 2, 3)]


def uv_unwrap(obj: bpy.types.Object) -> None:
    """Cheap deterministic UVs: project each face onto XY. Enough for texture tests."""
    mesh = obj.data
    uv_layer = mesh.uv_layers.new(name="UVMap")
    scale = 0.02
    for loop in mesh.loops:
        vert = mesh.vertices[loop.vertex_index].co
        uv_layer.data[loop.index].uv = (vert.x * scale, vert.y * scale)


def icosphere(radius: float, subdivisions: int, collection: bpy.types.Collection, name: str):
    """Skybox sphere with flipped normals so it is viewed from inside."""
    bpy.ops.mesh.primitive_ico_sphere_add(radius=radius, subdivisions=subdivisions)
    obj = bpy.context.active_object
    obj.name = name
    for other in list(obj.users_collection):
        other.objects.unlink(obj)
    collection.objects.link(obj)
    mesh = obj.data
    mesh.flip_normals()
    return obj


# --- scene construction ----------------------------------------------------------


def build_course(collection: bpy.types.Collection, images: dict[str, bpy.types.Image]) -> list[str]:
    """Visual model: ring road, grass field, fence strip, translucent water plane."""
    built: list[str] = []

    verts, faces = ring_strip(RING_RADIUS, ROAD_HALF_WIDTH, 0.0, RING_SEGMENTS)
    road = mesh_from_data("course_road", verts, faces, collection)
    road.data.materials.append(make_material("road", images["road"], "OPAQUE"))
    uv_unwrap(road)
    built.append(road.name)

    verts, faces = quad(0.0, 0.0, -0.5, RING_RADIUS * 1.4, RING_RADIUS * 1.4)
    grass = mesh_from_data("course_grass", verts, faces, collection)
    grass.data.materials.append(make_material("grass", images["grass"], "OPAQUE"))
    uv_unwrap(grass)
    built.append(grass.name)

    # Fence: a vertical strip, textured with binary alpha (the cutout case).
    verts, faces = ring_wall(RING_RADIUS + ROAD_HALF_WIDTH + 2.0, 8.0, RING_SEGMENTS)
    fence = mesh_from_data("course_fence", verts, faces, collection)
    fence.data.materials.append(make_material("fence", images["fence"], "CLIP"))
    uv_unwrap(fence)
    built.append(fence.name)

    # Water: partial alpha everywhere (the translucent case).
    verts, faces = quad(0.0, 0.0, -0.25, 40.0, 40.0)
    water = mesh_from_data("course_water", verts, faces, collection)
    water.data.materials.append(make_material("water", images["water"], "BLEND"))
    uv_unwrap(water)
    built.append(water.name)

    return built


def build_kcl(collection: bpy.types.Collection) -> list[str]:
    """Collision meshes, each named with the `_F####` suffix the add-on requires.

    Every mesh gets a material even though collision has no visual appearance: the
    add-on's minimap export runs through ABMatt, which fails on material-less meshes
    (verified in spike S2, P0-T05).
    """
    built: list[str] = []

    def add(name: str, verts: list, faces: list) -> None:
        obj = mesh_from_data(name, verts, faces, collection)
        obj.data.materials.append(make_material(f"kcl_{name.split('_F')[0]}", None, "OPAQUE"))
        built.append(obj.name)

    verts, faces = ring_strip(RING_RADIUS, ROAD_HALF_WIDTH, 0.0, RING_SEGMENTS)
    add(f"road_F{KCL_FLAGS['road']}", verts, faces)

    verts, faces = ring_strip(RING_RADIUS + ROAD_HALF_WIDTH + 6.0, 6.0, 0.0, RING_SEGMENTS)
    add(f"offroad_F{KCL_FLAGS['offroad']}", verts, faces)

    verts, faces = ring_wall(RING_RADIUS + ROAD_HALF_WIDTH + 2.0, 10.0, RING_SEGMENTS)
    add(f"wall_F{KCL_FLAGS['wall']}", verts, faces)

    # Boost panel: one short section of the ring, offset slightly to avoid z-fighting.
    verts, faces = quad(RING_RADIUS, 0.0, 0.05, 6.0, ROAD_HALF_WIDTH * 0.8)
    add(f"boost_F{KCL_FLAGS['boost']}", verts, faces)

    verts, faces = quad(0.0, 0.0, -40.0, RING_RADIUS * 2.0, RING_RADIUS * 2.0)
    add(f"fall_F{KCL_FLAGS['fall']}", verts, faces)

    return built


def build_skybox(collection: bpy.types.Collection, images: dict[str, bpy.types.Image]) -> list[str]:
    sky = icosphere(RING_RADIUS * 3.0, 2, collection, "vrcorn_sky")
    sky.data.materials.append(make_material("sky", images["sky"], "OPAQUE"))
    uv_unwrap(sky)
    return [sky.name]


def scene_extent() -> dict[str, list[float]]:
    """World-space bounds of every mesh, in Blender units and in game units."""
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            for axis in range(3):
                lo[axis] = min(lo[axis], point[axis])
                hi[axis] = max(hi[axis], point[axis])
    return {
        "min_blender": lo,
        "max_blender": hi,
        "min_game": [v * EXPORT_SCALE for v in lo],
        "max_game": [v * EXPORT_SCALE for v in hi],
    }


# --- entry point -----------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Args after Blender's '--' separator."""
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description="Generate the CT Studio fixture track")
    parser.add_argument("--out", required=True, type=Path, help="output directory")
    parser.add_argument(
        "--variant",
        choices=("good", "bad"),
        default="good",
        help="'bad' swaps in the non-power-of-two texture for warning tests",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv)
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    texture_dir = out_dir / "textures"
    texture_paths = generate_textures(texture_dir)

    reset_scene()
    images = {name: bpy.data.images.load(str(path)) for name, path in texture_paths.items()}
    if args.variant == "bad":
        # Same material slots, deliberately wrong texture size.
        images["road"] = images[NON_POWER_OF_TWO]

    collections = {name: new_collection(name) for name in COLLECTIONS}
    manifest = {
        "variant": args.variant,
        "blender": bpy.app.version_string,
        "export_scale": EXPORT_SCALE,
        "game_coord_limit": GAME_COORD_LIMIT,
        "kcl_flags": KCL_FLAGS,
        "textures": {
            name: {"file": path.name, "size": list(images[name].size)}
            for name, path in sorted(texture_paths.items())
        },
        "objects": {
            "Course": build_course(collections["Course"], images),
            "KCL": build_kcl(collections["KCL"]),
            "Skybox": build_skybox(collections["Skybox"], images),
        },
    }
    manifest["extent"] = scene_extent()

    limit = max(abs(v) for v in manifest["extent"]["min_game"] + manifest["extent"]["max_game"])
    if limit > GAME_COORD_LIMIT:
        raise SystemExit(
            f"fixture exceeds the game coordinate limit: {limit:.0f} > {GAME_COORD_LIMIT}"
        )
    manifest["max_abs_game_coord"] = limit

    blend_path = out_dir / f"fixture_track_{args.variant}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    manifest_path = out_dir / f"fixture_manifest_{args.variant}.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    counts = {k: len(v) for k, v in manifest["objects"].items()}
    print(f"[fixture] wrote {blend_path.name} ({blend_path.stat().st_size} bytes) objects={counts}")
    print(f"[fixture] max |coord| in game units: {limit:.0f} (limit {GAME_COORD_LIMIT})")
    print(f"[fixture] manifest: {manifest_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
