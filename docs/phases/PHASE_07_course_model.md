# Phase 7 — Course model pipeline

**Goal:** milestone M2 — saving in Blender rebuilds `course_model.brres` with sensible texture
formats and material settings, and never loses edits made in BrawlCrate/RiiStudio.
**Read first:** SPIKES.md §S3/§S4, ADR-004, ADR-012, MKW_DOMAIN.md (textures, transparency).
**Exit:** fixture end-to-end auto build passes `wszst check`; captured edits survive regeneration;
HC2 passed.

### [ ] P7-T01 — BrresBackend interface + default implementation
`core/pipelines/brres_backend.py` (Protocol) with: `import_model(src, dest, model_name, options)`,
`inspect(brres) -> ModelInfo` (materials; textures with format, size, mipmaps; polygon/facepoint stats
if available), `apply_material_settings(brres, settings)`, `set_texture_formats(brres, specs)`,
`capture_material_state(brres, dest_dir)`, `reapply_material_state(brres, src_dir)`.
Implement the default backend chosen in S3 fully; implement the fallback backend for
`import_model` + `inspect` at minimum. Backend selection per platform from ADR-004.
**Acceptance:** integration tests for each method on the fixture; unsupported operations raise a typed
error that the GUI can explain ("not supported by ABMatt backend — switch backend or open in …").

### [ ] P7-T02 — Texture analysis & recommendation
`core/textures/analyze.py` (Pillow → numpy, vectorised, cached by content hash): dimensions,
power-of-two, ≤ 1024 px, alpha class (none / binary / translucent, with tolerance), grayscale
detection, has-gradient heuristic. `recommend.py`: rules table (data, not code branches), defaults:
opaque → CMPR; binary alpha → CMPR; translucent colour → RGB5A3; translucent grayscale → IA8;
opaque grayscale → CMPR (offer I8); mipmaps: on for tiling surface textures, count until 8 px or max 4
(tune after HC2); estimated encoded size per format. Warnings: non-POT, > 1024, huge total size.
**Acceptance:** tests with generated images for every class; 100 × 1024² textures analysed in < 3 s
(benchmark, parallel via thread pool — Pillow/numpy release the GIL for heavy ops).

### [ ] P7-T03 — Textures page
Table: thumbnail, name, dimensions, alpha class, recommended, chosen format (dropdown), mipmaps (spin),
estimated size; multi-select bulk edit; "Reset to recommended"; total size footer; filter "only
overridden / only warnings". Only overrides are written to the manifest.
**Acceptance:** pytest-qt: override persists, rebuild uses it (verified via `inspect`); thumbnails are
generated off the UI thread and cached in `.ctstudio/thumbs/`.

### [ ] P7-T04 — Material rules & Materials page
Per material: transparency (auto/opaque/cutout/translucent; auto derives from the texture alpha
class), culling (front default / back / none), wrap U/V, min/mag filter, LOD bias, lightmap/fog flags
only if the backend supports them. Page shows material → textures, current effective settings, and
hints: translucent → Harry Potter effect risk; double-sided → performance cost. Advanced link: "Open
in BrawlCrate/RiiStudio".
**Acceptance:** settings applied and verified via `inspect` in integration tests.

### [ ] P7-T05 — Course model node
Pipeline: exported DAE → `import_model` (model name `course`) → texture formats → material rules →
`reapply_material_state` (captured edits, P7-T07) → optional post-import ABMatt command file →
(release profile) optimise if the backend supports it → stage `course_model.brres`. Card summary:
materials, textures, BRRES size, facepoints (if known), warnings.
**Acceptance:** fixture auto build end-to-end; cached when nothing changed; each sub-step logged with
its exact command.

### [ ] P7-T06 — Power-user hooks
`overrides/course_model.abmatt` (ABMatt command file) executed after rules when present;
`extra_import_args`; project `hooks.post_stage` script run with env vars (`TS_PROJECT`, `TS_STAGE`,
`TS_PROFILE`). Documented in user docs with examples.
**Acceptance:** tests for hook invocation, failure reporting, and env vars.

### [ ] P7-T07 — External edit reconciliation (capture & reapply)
Complete ARCHITECTURE §8 option 1 using the S4 mechanism: "Keep & capture" stores material state
under `overrides/captured/course_model/` with a human-readable summary (which materials, what
changed); captured state is reapplied on every regenerate; materials that no longer exist are
reported, not silently dropped; "Forget captured edits" per material. Backups always.
**Acceptance:** integration test: generate → simulate edit → capture → change DAE → regenerate →
edit persists; renamed material reported.

### [ ] P7-T08 — Open-in for course model (incl. Wine)
Wire BrawlCrate/RiiStudio launch for `course_model.brres` with Linux Wine support and a clear
explanation panel: "Edit and save in BrawlCrate. CT Studio will detect the change and ask
what to keep."
**Acceptance:** argument construction tests; manual verification scheduled for HC2.

### [ ] P7-T09 — Skybox reuse
Skybox (Blender collection mode) uses the same node with model name `vrcorn` and its own texture /
material overrides namespace. (Template/manual modes come in P8.)
**Acceptance:** fixture skybox builds; `wszst check` doesn't flag it.

### [ ] P7-GATE — Phase review
### [ ] P7-HC2 — Human checkpoint 2
