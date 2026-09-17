# Phase 9 — 3D preview

**Goal:** see collision (coloured by type), source geometry and minimap inside the app — the fastest
way to spot wrong flags, holes, or a broken minimap without launching the game.
**Read first:** SPIKES.md §S6, ADR-008, ARCHITECTURE §13/§15.
**Exit:** preview budgets met in benchmarks; screenshots reviewed.

### [ ] P9-T01 — Viewport widget foundation
`gui/viewport/`: `QOpenGLWidget` + moderngl context (GL 3.3 core), camera (orbit/pan/zoom, frame all,
top/front views; Blender-like mouse defaults, configurable), grid/axes, lazy resource creation,
explicit release on project close, `paintGL` only draws. Graceful fallback panel if GL context creation
fails (message + "Copy diagnostics"), never a crash.
**Acceptance:** offscreen render test produces a non-empty image; GL-failure fallback test (mock).

### [ ] P9-T02 — Mesh upload pipeline
Background loading (worker) → numpy arrays → single interleaved VBO + index buffer per layer upload on
the GUI thread in one call; no Python per-triangle loops anywhere. Memory released on layer unload.
**Acceptance:** 200k-triangle load < 1 s end-to-end (benchmark); RSS returns near baseline after 10
load/unload cycles.

### [ ] P9-T03 — Collision layer
Colours by KCL base type (palette + legend, colour-blind-safe option), per-type visibility toggles,
wireframe toggle, hover label (type name, flag hex, variant bits) via GPU ID buffer read on mouse
move (throttled), highlight of triangles flagged by Issues (e.g. outside coordinate limits).
**Acceptance:** screenshot tests; picking test on a synthetic mesh.

### [ ] P9-T04 — Source geometry layer
Load `preview_mesh.npz` from the Blender export; textured rendering with generated mipmaps (textures
loaded off-thread, uploaded lazily), simple lambert shading; toggle vs collision overlay with alpha.
**Acceptance:** fixture renders textured; missing texture shows a checker, not a crash.

### [ ] P9-T05 — Minimap layer
Top-down orthographic grayscale render of the minimap geometry (from the minimap node's intermediate
OBJ/mesh), optionally overlaid on collision; replaces the P8 rasterised thumbnail with a GL-rendered
one when GL is available.
**Acceptance:** screenshot test.

### [ ] P9-T06 — Integration into the app
Preview dock/tab; card buttons ("Preview") focus the right layer; state (camera, toggles) remembered
per project in `.ts/ui_state.json`.
**Acceptance:** pytest-qt flow; UI remains responsive while loading (watchdog clean).

### [ ] P9-T07 — Performance & leak tests
Benchmarks in CI (llvmpipe numbers are relative — compare against stored baseline, fail on > 25 %
regression); open/close project 20× without growth of GL objects or threads.
**Acceptance:** tests green; BENCHMARKS.md updated.

### [ ] P9-GATE — Phase review
