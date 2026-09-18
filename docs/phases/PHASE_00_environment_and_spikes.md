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

### [x] P0-T02 — Toolchain bootstrap script (timebox 3 h) (commit cbbb5f4)
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

Done. Fresh run installed all three tools (55 s); second run is a 0.35 s no-op. All four
acceptance commands verified, plus `wkmpt`/`wimgt`/`wbmgt`/`wstrt`. Pins, checksums and
the surprises are in [TOOLS.md](../reference/TOOLS.md#bootstrap-pins-p0-t02-verified-2026-09-17-by-real-download--run).
Two plan corrections: **Lorenzi's KMP Editor has no Linux build ever published**, so it is
not auto-installed (P0-T10 must use Wine); and Python 3.12 comes from `uv python install`,
not the image. `--only`, `--force` and `--list` work; unknown tool names exit 2.

### [x] P0-T03 — Synthetic fixture track (timebox 4 h) (commit 1d44633)
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

Done. `uv run python scripts/fixtures/make_fixtures.py` regenerates everything in **0.85 s**
(budget 60 s): both `.blend` variants (~102 KB each, under the 2 MB commit limit), seven PNGs
and `course.kmp`. Textures and manifests are byte-identical across runs.
Already proved against the real tools rather than waiting for S1/S2: the add-on registered
headlessly and `bpy.ops.kcl.export` exported 5 objects / 292 triangles, skipping the 5 unflagged
visual meshes; `wkclt flags` then reported exactly the five intended types (Road, Off-road,
Boost Pad, Wall, Fall Boundary). 38 unit tests, 3/3 mutations caught.
**KMP partially deferred:** KTPT/ENPT/ENPH/ITPT/ITPH/CKPT/CKPH/JGPT/STGI are all present and
valid, but the `[CAME]` opening camera is not, so compiling reports 2 expected camera warnings.
Writing a valid CAME block is deferred to P10-T05 as the task allows.

### [x] P0-T04 — Spike S1: Wiimms assemble & check (timebox 2 h) (commit 5688ad1)
Stage a folder (`course.kcl`, a placeholder or ABMatt-made `course_model.brres`, `map_model.brres`,
`vrcorn_model.brres`, `course.kmp`, empty/absent `posteffect/`) → `wszst create` with fastest and
best compression → `wszst check` → `wszst slots` → `wszst list`.
Find: exact flags for destination/overwrite/compression levels/auto-add; whether `check` has a
machine-readable mode (`--json`/`--sections`?) or what text format to parse; exit codes; how missing
components are reported; timings for fast vs best.
**Acceptance:** SPIKES.md §S1; adapter-ready command table in TOOLS.md.

Done. [SPIKES.md §S1](../dev/SPIKES.md) + command table and caveats in
[TOOLS.md](../reference/TOOLS.md). Reproduce with `uv run python spikes/s1_wszst.py`;
11 integration tests in `tests/integration/test_wszst_contract.py` pin the behaviour
(3/3 mutations caught).
**Headline:** `wszst check`'s exit code is not pass/fail — a valid track, a track with
warnings and an empty archive all exit **2**, while a **corrupt file exits 0** with
`ERROR #39` on stdout. Adapters must parse output and treat `ERROR #` as failure.
`check --sections` and `slots --sections` are rejected; **`analyze --json`** is the
machine-readable path and supersedes `slots` (it carries `slot_info`, `lap_count`,
`n_ckpt0`, coordinate ranges and per-component SHA1s that are empty when a file is
missing). `create` never validates, and `--auto-add` is a silent no-op with no library.

### [x] P0-T05 — Spike S2: headless Blender exports with Blender-MKW-Utilities (timebox 3 h) (commit 3a6a453)
Add the add-on as submodule `vendor/blender-mkw-utilities` (github.com/Le-Sponk/Blender-MKW-Utilities,
pin the commit). Read its source to list operator `bl_idname`s and internal export functions for:
KCL export (incl. un-bean modes / `lower-walls.txt`), Collada export (built-in method + copy
textures), OBJ export, minimap BRRES export. Run each in `blender -b --factory-startup` on the
fixture. Compare calling operators vs internal functions (robustness to context requirements).
Record: arguments, outputs, stdout markers (e.g. the "[MKW Utilities] KCL export: …" lines),
failure modes, timing, and how the add-on locates wszst/wkclt/ABMatt when run headless.
**Acceptance:** `spikes/blender_export_spike.py` reproduces all exports; SPIKES.md §S2 with the
recommended bridge approach; list of add-on changes that would help (for the human to decide).

Done. Add-on pinned as submodule `vendor/blender-mkw-utilities`, originally v1.12.0
(244ecfd), now `ffa905f` after the merged export-API refactor (add-on PR #1).
`uv run python spikes/s2_blender.py` reproduces **all six exports headlessly**: KCL
(LOWER + NONE), DAE (AUTO + BUILTIN, with textures copied alongside), OBJ, and the
minimap BRRES. See [SPIKES.md §S2](../dev/SPIKES.md) and the operator table in
[TOOLS.md](../reference/TOOLS.md). 10 integration tests, 2/2 mutations caught.
**Calling operators is enough** — no context juggling. Two preconditions bite though:
`export.minimap` reports a missing ABMatt as `poll() failed, context is incorrect`
(misleading), and it refuses meshes without materials, which forced a fixture change.
`method=AUTO` silently equals `BUILTIN` on Linux (FbxConverter is a Windows binary), so
DAE bytes will differ on Windows CI. Add-on wishlist is in §S2 — nothing is required.

### P0-T06 — Spike S3: BRRES backend bake-off (timebox 6 h total)

#### [x] P0-T06a — Obtain and probe RiiStudio CLI (timebox 2 h) (commit 08bf2dd)
Pin source and build prerequisites; attempt a Linux CLI build and record reproducible
commands, licence, version, exit codes and command help in SPIKES.md §S3 and TOOLS.md.
Attempt the Linux build first; if blocked, record a Windows prebuilt evaluation for P2-T08.
Acceptance: a runnable CLI with recorded help, or an evidenced build blocker and a
specific Windows CI fallback. No backend default is chosen from help alone.

Done: Alpha 5.11.5 builds on Linux without source patches, with Corrosion 0.4.10,
explicit `<memory>` and `libstdc++exp`. Nine live query recordings and ten integration
tests; 68 tests pass. Help/version and bad arguments all exit 255.
[Build recipe and limitations](../dev/SPIKES.md#s3-brres-backend-bake-off-p0-t06a--p0-t06b).
Overall licence grant remains unconfirmed; no binary redistribution. S3b remains open.

#### [x] P0-T06b — Fixture comparison and backend decision (timebox 4 h) (commit 5f96d10)
Depends on P0-T06a. Acceptance: the comparison and ADR/interface decision below.
For each backend on the fixture DAE (course + skybox) measure and record:
success; time; BRRES size; material/texture counts; control over per-texture format & mipmaps;
control over per-material transparency (opaque/alpha-test/translucent) and culling; ability to set
model name (`course`, `vrcorn`, `map`); `wszst check`/`wszst brsub` warnings; primitive/facepoint
statistics if obtainable (e.g. via `rszst brres-to-json`); whether ABMatt can open and re-save an
rszst-made BRRES without damage; whether `brres-to-json` → edit material → `json-to-brres` works.
**Acceptance:** SPIKES.md §S3 with a comparison table and per-platform default recommendation;
ADR-004 moved to Accepted (or re-scoped) with evidence; BrresBackend interface sketch confirmed.

Done. [SPIKES.md §S3b](../dev/SPIKES.md#s3b-fixture-bake-off-and-backend-decision-p0-t06b)
has the comparison table; ADR-004 is **Accepted**: rszst imports, ABMatt post-processes,
same on both platforms. Reproduce with `uv run python spikes/s3_backend_bakeoff.py`;
14 integration tests in `tests/integration/test_brres_backends.py` (4/4 mutations caught).
**Headline:** the interop wall is one-way — ABMatt reads rszst output, but **rszst cannot
read an ABMatt BRRES** (`Invalid quantization for normal data: U16`, exit 255), which
fixes the pipeline order regardless of preference. rszst is also ~22x faster
(0.013 s vs 0.293 s). Both pack into an SZS that passes `wszst check`.
Three traps recorded: ABMatt takes the MDL0 name from the **source filename** and
rejects a mismatched `<slot>_model.brres` destination; `abmatt -c` mangles multi-word
commands (use `-f`); `set tex0 format:` is a **silent no-op**, so per-texture format
control is excluded from the ABMatt backend. rszst's `--mipmaps` needs `--min-mip`
lowered to do anything. Interface confirmed, minus `set_texture_formats` for ABMatt.
Skybox note: the fixture's `vrcorn` model is covered via `--model-name vrcorn`
(naming is the part that differs per slot); the geometry path is identical to `course`.

### [x] P0-T07 — Spike S4: preserving external material edits (timebox 3 h) (commit P0T07_COMMIT)
Simulate an external edit on a generated BRRES (change transparency, culling, a TEV/blend setting,
add an SRT0 animation if feasible). Regenerate from the DAE and try to restore the edit via:
(a) `rszst dump-presets` + `import-brres --preset-path`; (b) ABMatt replace-with-matching-names /
copy+paste material; (c) JSON material merge. Check persistence, texture duplication, animation
survival, speed.
**Acceptance:** SPIKES.md §S4; ADR-012 updated; list of what must be re-verified with a real
BrawlCrate-edited file at HC2.

Done. [SPIKES.md §S4](../dev/SPIKES.md#s4--preserving-external-material-edits-p0-t07).
`uv run python spikes/s4_material_edits.py` reproduces all three routes.
All three restore the edit with no texture duplication, so the decision is made by
failure modes: **ADR-012 accepts route (a) presets** — fastest (0.006 s dump + 0.013 s
import vs ABMatt's 0.198 s), one tool, carries SRT0 for free, and a name miss is a
silent no-op. Route (b) is **rejected**: pasting onto a renamed material applies the
settings then deletes the orphaned texture at exit 0, and ABMatt 1.3.2's `-a`/`--auto-fix`
cannot disable it (all three spellings rejected). Route (c) is kept as the inspection/diff
format only — its `.json` needs a `<stem>.bin` sidecar (255 without it) and a
material-only merge silently drops SRT0. Presets match on **material name** and an
unmatched preset is skipped silently, so P7-T07 must diff and report orphans itself.
10 integration tests, 5/5 mutations caught. HC2 re-verification list in
HUMAN_CHECKPOINTS.md (TEV/indirect/multi-layer/PAT0/CLR0 coverage, and whether a
BrawlCrate-saved BRRES re-imports into rszst at all).

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
**Updated by P0-T02:** Lorenzi's KMP Editor publishes no Linux build (only Windows `.exe` and
macOS arm64, checked back to v0.7.0), so treat it as a Wine target on Linux like BrawlCrate,
and budget for that. It is not installed by `bootstrap_tools.py`.
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
