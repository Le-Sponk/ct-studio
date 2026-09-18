# Phase 6 — Blender bridge

**Goal:** the `.blend` is the source of truth; exports happen automatically and headlessly.
**Exit:** fixture `.blend` → exports for course, KCL, skybox (and minimap source if present) in one
Blender launch, on Linux and Windows CI; errors become actionable Issues.
**Read first:** SPIKES.md §S2, ARCHITECTURE §12.

### [ ] P6-T01 — Bridge job runner
**From S2 (P0-T05), already proven:** call the operators directly (`kcl.export`,
`export.autodesk_dae`, `export_scene.objkcl`, `export.minimap`) — all six export variants
run under `-b --factory-startup` with no context setup. Two things the runner must do
itself, because the add-on's own errors are misleading or late:
extend `PATH` with both `.tools/wiimms-szs-tools/bin` and `.tools/abmatt/bin` before
launching (factory startup discards add-on preferences), and check ABMatt availability
plus "every mesh has a material" *before* calling `export.minimap`, whose `poll()`
failure surfaces as `context is incorrect`. The add-on directory name
`blender-mkw-utilities` is not importable: stage/vendor it under a valid module name.
`blender_bridge/run_job.py` (stdlib + bpy only): parse `job.json` (schema versioned: blend path,
add-on dir, output dir, list of exports with options), register the add-on from `vendor/`, run the
exports using the entry points chosen in S2, write `export_manifest.json` (per export: files, object
names, material → texture mapping, triangle counts, extents in game units, skipped objects + reason,
warnings, timings, Blender version, add-on commit). On failure: write `error.json`
(`{code, message, details}`) and exit non-zero. Also write `preview_mesh.npz` if `numpy` is available
inside Blender (it is bundled with Blender); otherwise a compact binary fallback.
**Acceptance:** integration test on the fixture produces all files; schema documented in
`docs/dev/BRIDGE.md`; job/manifest schema unit tests on the core side.

### [ ] P6-T02 — Collection mapping & conventions
Detect on project creation: collections named like Course/KCL/Collision/Skybox/Minimap
(case-insensitive, configurable synonyms); KCL candidates = objects with valid `_F####` suffix
(same rule as the add-on). A lightweight inspection job (`inspect` mode in run_job) returns
collections, object counts and flag-suffix stats in < 5 s for the fixture. Mapping review dialog in
the GUI (choose collection per component; show counts; warn on objects without flags in the KCL
collection).
**Acceptance:** inspection integration test; dialog pytest-qt test with a recorded inspection JSON.

### [ ] P6-T03 — Export node
Single node `blender_export` producing all requested exports into `.ctstudio/exports/`. Inputs: `.blend`
fingerprint, external images referenced by the previous export manifest, mapping + export options,
bridge version, add-on commit, Blender version. Resource tag `blender`. Downstream nodes depend on
specific files from the manifest.
**Acceptance:** cache test — re-saving the `.blend` without changes still re-exports (content differs;
acceptable) but downstream nodes skip when exported files' hashes are unchanged.

### [ ] P6-T04 — Error mapping
Translate add-on/bridge output into Issues: objects without KCL flags; meshes without materials (the
add-on already reports some); missing/unsaved/packed images; extents beyond ±131071; Blender version
unsupported; add-on failed to register; tool not found inside Blender.
**Acceptance:** tests from recorded failure outputs (create them with deliberately broken fixtures).

### [ ] P6-T05 — Source panel & auto-rebuild
GUI: source card/header shows `.blend`, last export time and summary, "Open in Blender", "Export now",
"Review mapping". Option "Rebuild when .blend is saved" (watch `.blend`, ignore `.blend1`, debounce
2 s, don't start while a build runs — queue one).
**Acceptance:** pytest-qt test simulating a save triggers exactly one build.

### [ ] P6-T06 — Cross-platform integration
Integration tests on Linux and Windows CI using the fixture; Blender 5.2 LTS required, 4.5 LTS in a
weekly compatibility job.
**Acceptance:** both OS green.

### [ ] P6-T07 — (stretch, needs human approval) Live link in the add-on
Propose a small, isolated change to the add-on repo: a "CT Studio" panel with "Export to project"
and "Auto-export on save", writing the same export manifest into the project's `.ctstudio/exports/`.
Write the proposal in `docs/dev/ADDON_LIVE_LINK.md` and add a non-blocking "Needs human" item. Only
implement (on a branch in the submodule) after approval.

### [ ] P6-GATE — Phase review
