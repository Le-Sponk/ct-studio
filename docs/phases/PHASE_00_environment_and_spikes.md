# Phase 0 — Environment, toolchain & spikes

**Goal:** prove the toolchain works in the dev container and replace guesses with evidence.
**Output:** `docs/dev/ENVIRONMENT.md`, `docs/dev/SPIKES.md`, updated `docs/reference/TOOLS.md` and
`docs/DECISIONS.md`, `scripts/bootstrap_tools.py`, fixture generator, small scripts under `spikes/`.
**Rules for spikes:** timebox each (stated per task). Record commands, versions, exit codes, output
snippets, timings, and a recommendation. Spike code is throwaway: never imported by `src/`.
If a timebox expires, write down what's known, pick the safest fallback, flag it, move on.
Before P1-T02 creates `scripts/check.py`, use the evidence gate in ADR-016, not a placeholder
quality script. Record task-specific checks and run `git diff --check` before committing.

---

### [x] P0-T01 — Environment audit (timebox 1 h) (commit b69cc17)
Determine: OS/distro, CPU arch, Python availability, whether you can install system packages
(apt/sudo), network access to szs.wiimm.de / github.com / download.blender.org / pypi, free disk,
presence of EGL/Mesa (for offscreen GL), git + git identity, whether the repo dir is a bind mount
visible to the host (ask the human in STATUS if unknown).
Packages likely needed on Debian/Ubuntu-based images: `git curl xz-utils unzip ca-certificates
libgl1 libegl1 libegl-mesa0 libgl1-mesa-dri libxkbcommon0 libxkbcommon-x11-0 libfontconfig1
libdbus-1-3 libxi6 libxrender1 libsm6 libxfixes3 libxcb-cursor0 xvfb` (+ for building RiiStudio:
`build-essential cmake clang libassimp-dev libglfw3-dev libfreetype-dev mesa-common-dev` and a Rust
toolchain).
**Acceptance:** `docs/dev/ENVIRONMENT.md` lists findings. If packages cannot be installed, write
`docker/dev.Dockerfile` (based on the current image) that adds them and add a BLOCKING "Needs human"
item asking the human to rebuild/restart the sandbox with it.

Audit evidence: [ENVIRONMENT.md](../dev/ENVIRONMENT.md). System installation, all four
network probes and software EGL/GLX contexts passed. No Dockerfile fallback was needed.

### [ ] P0-T02 — Toolchain bootstrap script (timebox 3 h)
`scripts/bootstrap_tools.py` (idempotent, cross-platform where possible, downloads into `.tools/`
which is gitignored, prints a version table, `--only <tool>`):
- **uv** (if missing) and Python 3.12 via uv.
- **Wiimms SZS Tools v2.42a** (Linux x86_64 tarball from szs.wiimm.de; Cygwin zip on Windows).
- **Blender 5.2 LTS** portable archive (the add-on is verified on 4.0–5.2; also allow `--blender 4.5`
  for compatibility runs).
- **ABMatt v1.3.2**: prefer the official Linux/Windows release binary; else an isolated venv from the
  git tag. Must not touch the project environment. Put `wimgt` on its PATH.
- **Lorenzi's KMP Editor** latest release (only needed for the launch-contract spike).
**Acceptance:** fresh run installs everything; second run is a no-op; `wszst version`,
`wkclt version`, `blender --version`, ABMatt help all succeed; versions + URLs recorded in TOOLS.md.

### [ ] P0-T03 — Synthetic fixture track (timebox 4 h)
`scripts/fixtures/make_fixture_blend.py`, run via `blender -b --factory-startup --python`, writes
`tests/fixtures/generated/` (gitignored, regenerated on demand; a small committed copy is fine if
< 2 MB). Deterministic. Contents:
- **Course** collection: closed ring road (~ track scale, inside ±131071), grass area, fence strip,
  a translucent water plane, textured with generated PNGs: opaque colour, binary-alpha fence,
  translucent water, grayscale detail; power-of-two sizes; one intentionally non-power-of-two
  texture in a separate "bad" variant for warning tests.
- **KCL** collection: simplified collision meshes named with `_F####` suffixes (road, offroad,
  wall, boost panel, fall boundary) using flag values read from the add-on source, not typed from memory.
- **Skybox** collection: inverted sphere with a gradient texture.
- Also generate a minimal KMP (start point, lap-counter checkpoint loop, enemy + item routes,
  respawn) via `wkmpt` from text, following the syntax in the official KMP text guide. If this
  exceeds the timebox, defer to P10-T05 and note it.
**Acceptance:** one command regenerates all fixtures in < 60 s; add-on exports and Wiimms tools
accept them (checked in S1/S2).

### [ ] P0-T04 — Spike S1: Wiimms assemble & check (timebox 2 h)
Stage a folder (`course.kcl`, a placeholder or ABMatt-made `course_model.brres`, `map_model.brres`,
`vrcorn_model.brres`, `course.kmp`, empty/absent `posteffect/`) → `wszst create` with fastest and
best compression → `wszst check` → `wszst slots` → `wszst list`.
Find: exact flags for destination/overwrite/compression levels/auto-add; whether `check` has a
machine-readable mode (`--json`/`--sections`?) or what text format to parse; exit codes; how missing
components are reported; timings for fast vs best.
**Acceptance:** SPIKES.md §S1; adapter-ready command table in TOOLS.md.

### [ ] P0-T05 — Spike S2: headless Blender exports with Blender-MKW-Utilities (timebox 3 h)
Add the add-on as submodule `vendor/blender-mkw-utilities` (github.com/Le-Sponk/Blender-MKW-Utilities,
pin the commit). Read its source to list operator `bl_idname`s and internal export functions for:
KCL export (incl. un-bean modes / `lower-walls.txt`), Collada export (built-in method + copy
textures), OBJ export, minimap BRRES export. Run each in `blender -b --factory-startup` on the
fixture. Compare calling operators vs internal functions (robustness to context requirements).
Record: arguments, outputs, stdout markers (e.g. the "[MKW Utilities] KCL export: …" lines),
failure modes, timing, and how the add-on locates wszst/wkclt/ABMatt when run headless.
**Acceptance:** `spikes/blender_export_spike.py` reproduces all exports; SPIKES.md §S2 with the
recommended bridge approach; list of add-on changes that would help (for the human to decide).

### [ ] P0-T06 — Spike S3: BRRES backend bake-off (timebox 6 h)
Obtain `rszst`: (a) build RiiStudio CLI from source in the container (timebox 2 h of the 6), or
(b) if impossible, plan to evaluate the Windows prebuilt in the Windows CI runner and note it.
For each backend on the fixture DAE (course + skybox) measure and record:
success; time; BRRES size; material/texture counts; control over per-texture format & mipmaps;
control over per-material transparency (opaque/alpha-test/translucent) and culling; ability to set
model name (`course`, `vrcorn`, `map`); `wszst check`/`wszst brsub` warnings; primitive/facepoint
statistics if obtainable (e.g. via `rszst brres-to-json`); whether ABMatt can open and re-save an
rszst-made BRRES without damage; whether `brres-to-json` → edit material → `json-to-brres` works.
**Acceptance:** SPIKES.md §S3 with a comparison table and per-platform default recommendation;
ADR-004 moved to Accepted (or re-scoped) with evidence; BrresBackend interface sketch confirmed.

### [ ] P0-T07 — Spike S4: preserving external material edits (timebox 3 h)
Simulate an external edit on a generated BRRES (change transparency, culling, a TEV/blend setting,
add an SRT0 animation if feasible). Regenerate from the DAE and try to restore the edit via:
(a) `rszst dump-presets` + `import-brres --preset-path`; (b) ABMatt replace-with-matching-names /
copy+paste material; (c) JSON material merge. Check persistence, texture duplication, animation
survival, speed.
**Acceptance:** SPIKES.md §S4; ADR-012 updated; list of what must be re-verified with a real
BrawlCrate-edited file at HC2.

### [ ] P0-T08 — Spike S5: headless minimap (timebox 3 h)
Paths to evaluate: (1) KCL → OBJ filtered by KCL types (`wkclt` options) → ABMatt convert as map
model; (2) Blender minimap collection → DAE/OBJ → backend with model name `map` + bones;
(3) add-on's own minimap export. Then `wszst minimap --auto`. Verify model named `map`, bone `map`
with children `posLD`/`posRU` (or document reliance on a Minimap Control AREA instead).
**Acceptance:** a `map_model.brres` produced headlessly; `wszst minimap` output recorded; recommended
path in SPIKES.md §S5.

### [ ] P0-T09 — Spike S6: preview rendering stack (timebox 3 h)
PySide6 `QOpenGLWidget` + moderngl: render a 200k-triangle coloured mesh; offscreen in the container
(EGL/llvmpipe or Xvfb); save a screenshot; measure mesh upload time and frame time. Check GL version
available on llvmpipe and minimum GL we will require (target 3.3 core).
**Acceptance:** screenshot in `spikes/out/`, numbers in SPIKES.md §S6, ADR-008 confirmed or changed.

### [ ] P0-T10 — Spike S7: external editor launch contracts (timebox 2 h)
From source code/docs (and runs where possible) determine for BrawlCrate, RiiStudio GUI, Lorenzi's
KMP Editor, KMP Cloud, Blender, Dolphin: does a file path argument open the file? single-instance
behaviour? Wine invocation for BrawlCrate on Linux (prefix, `winetricks dotnet48`, `win10`, 32-bit,
`winepath -w` conversion). Lorenzi's editor auto-loads `course.kcl` from the KMP's folder — confirm.
**Acceptance:** "Launch contracts" table in TOOLS.md with evidence links; unknowns listed for HC0/HC2.

### [ ] P0-T11 — Spike S8: Dolphin test-launch options (research only, timebox 2 h)
Compare: booting an extracted game folder (`dolphin-tool extract`, then `-e <dir>/sys/main.dol`)
with the slot SZS replaced; generated Riivolution XML + folder under Dolphin's `Load/Riivolution`;
MKW-SP "My Stuff". Consider CLI flags (`-e`, `-b`, `-u`), whether Riivolution can be enabled from
the command line, disk space, and user legal constraints (their own copy).
**Acceptance:** SPIKES.md §S8 recommendation + open questions. No implementation.

### [ ] P0-T12 — Phase wrap-up
Update DECISIONS.md statuses; amend later phase files where evidence changes the plan (log in STATUS
"Plan changes"); update TOOLS.md; fill in HC0 questions in STATUS "Needs human — BLOCKING".
Run `mkw-phase-review` (lightweight for P0: evidence completeness + plan consistency).
