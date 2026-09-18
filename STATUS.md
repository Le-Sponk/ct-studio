# STATUS

> The agent updates this file at the end of every session. The human reads it to see progress
> and to answer "Needs human" items. Keep entries short; link to files/commits for detail.

**Current phase:** 0 — Environment, toolchain & spikes
**Next task:** P0-T08 — Spike S5: headless minimap
**Name:** CT Studio · package/CLI `ctstudio` · project data `.ctstudio/` (ADR-015)
**Last green commit:** eae0ba3 (ADR-016 evidence gate; `check.py` arrives in P1-T02)
**Last phase gate passed:** —

## In progress
<!-- Task ID, one-line plan, acceptance criteria restated, files expected to change -->
_none_

## Done (newest first)
<!-- `P0-T01` — short summary — commit abc1234 -->
- `P0-T07` — Spike S4 (preserving external material edits): **ADR-012 Accepted** —
  capture with `rszst dump-presets`, reapply with `import-brres --preset-path`. All three
  candidate routes restore the edit, so failure modes decided it: ABMatt copy/paste
  **deletes the orphaned texture** on a renamed material at exit 0 and its `-a` flag
  cannot disable that in 1.3.2. Presets miss silently, so P7-T07 must report orphans
  itself. 10 integration tests, 5/5 mutations caught.
  [SPIKES.md §S4](docs/dev/SPIKES.md#s4--preserving-external-material-edits-p0-t07) — commit eae0ba3
- `P0-T06b` — Spike S3b (BRRES backend bake-off): **ADR-004 Accepted** — rszst imports,
  ABMatt post-processes, both platforms. Decided by a one-way interop wall: rszst cannot
  read an ABMatt BRRES. 14 integration tests, 4/4 mutations caught.
  [SPIKES.md §S3b](docs/dev/SPIKES.md#s3b-fixture-bake-off-and-backend-decision-p0-t06b) — commit 5f96d10
- `P0-T06a` — built RiiStudio Alpha 5.11.5 CLI on Linux without source patches;
  pinned build recipe, nine CLI recordings and ten integration tests. 68 tests pass,
  ruff clean, overwrite mutation caught. [SPIKES.md S3](docs/dev/SPIKES.md#s3-brres-backend-bake-off-p0-t06a--p0-t06b).
  Help and argument errors both exit 255; conversion/default decision stays in S3b.
  Overall redistribution licence unconfirmed. — commit 08bf2dd
- `P0-T05` — Spike S2 (headless Blender exports): add-on pinned as a submodule at
  v1.12.0; all six exports (KCL x2, DAE x2, OBJ, minimap BRRES) run headlessly via
  operators. [SPIKES.md §S2](docs/dev/SPIKES.md). 10 integration tests, 2/2 mutations
  caught. Minimap BRRES verified by `wszst minimap`. — commit 3a6a453
  **Follow-up (2026-09-19):** the two accepted wishlist items were implemented upstream
  and merged as add-on PR #1 (`ffa905f`); submodule pin bumped and P6-T01 rewritten to
  use the callable API. Also fixed five latent add-on defects — `os.popen` shell
  injection in KCL encoding, ABMatt exit codes ignored (stale BRRES republished),
  child collections skipped by active-collection minimap export, non-mesh objects
  counted in selection-only KCL, and the `blender -b` scripts exiting 0 on failure.
  Verified on Blender 4.2.23 LTS **and** 5.2.2 LTS.
- `P0-T04` — Spike S1 (Wiimms assemble & check): `spikes/s1_wszst.py` +
  [SPIKES.md §S1](docs/dev/SPIKES.md) + adapter command table in TOOLS.md.
  Found that `wszst check`'s exit code is not pass/fail and that `analyze --json`
  supersedes `slots`. 11 integration tests, 3/3 mutations caught. — commit 5688ad1
- `P0-T03` — synthetic fixture track: `scripts/fixtures/` generates two `.blend` variants,
  7 PNGs and a valid `course.kmp` in 0.85 s (budget 60 s), deterministically. Proved with
  the real tools: add-on exported 5 KCL objects / 292 triangles, `wkclt flags` confirmed
  all five flag types. 38 unit tests, 3/3 mutations caught. — commit 1d44633
- `P0-T02` — `scripts/bootstrap_tools.py` + `scripts/tool_catalogue.py` install Wiimms
  2.42a, Blender 5.2.2 LTS and ABMatt 1.3.2 into `.tools/` with checksum verification.
  Fresh run 55 s, second run 0.35 s no-op; 22 unit tests, 3/3 mutations caught.
  [TOOLS.md](docs/reference/TOOLS.md) — commit cbbb5f4
- `P0-T01` — environment audit: Debian 13.4 x86_64 container, root apt works, all four
  download origins reachable, Mesa llvmpipe gives GL 4.5 core via surfaceless EGL and
  Xvfb, no Python 3.12 yet. [ENVIRONMENT.md](docs/dev/ENVIRONMENT.md) — commit b69cc17

## Plan changes
<!-- Date · what changed · why (evidence link) · affected ADR/phase files -->
- 2026-09-19 (S4): **ADR-012 names a concrete mechanism** (rszst presets) and explicitly
  rejects ABMatt copy/paste, which the plan had listed as an equal candidate. Evidence:
  its autofix silently deletes an orphaned texture and `-a`/`--auto-fix` is unusable in
  1.3.2. ARCHITECTURE §8, P7-T07 and HC2 updated; P7-T07 gains an explicit
  "diff captured presets against regenerated materials" requirement because no tool
  reports an unmatched preset.
- 2026-09-19: **P6-T01 rewritten** for the merged add-on export API (`ffa905f`). The
  bridge now calls `export_kcl` / `export_collada` / `export_minimap_brres` and reads
  counts from the returned dictionary; the planned stdout parsing and the pre-flight
  ABMatt / material checks are dropped, because the add-on returns a typed reason.
  `export_scene.objkcl` still goes through `bpy.ops` (no extracted form). Evidence:
  [SPIKES.md §S2 wishlist](docs/dev/SPIKES.md), TOOLS.md "Callable export API".
  Affects PHASE_06, TOOLS.md, SPIKES.md, submodule pin.
- 2026-09-19: Blender **4.2.23 LTS** added to `scripts/tool_catalogue.py` as an optional
  tool (`--only blender-4.2`). It is the add-on manifest's declared floor, so
  compatibility runs need it reproducibly rather than by hand. Published checksum
  verified on download.
- P0-T06 split under the task-loop size rule: P0-T06a obtains/probes the CLI;
  P0-T06b runs the fixture bake-off and decides ADR-004. The six-hour total is unchanged.
  Native build troubleshooting plus both backends' material/JSON round-trips is too
  large for one bounded change. No backend recommendation is inferred from CLI help.
- 2026-09-17: ADR-016 adds the pre-P1-T02 evidence gate because the mandatory script
  does not exist yet (real invocation exited 2). Evidence: ENVIRONMENT.md, quality gate
  section. Phase 0, WORKFLOW and AGENTS rule 6 now reference this bounded exception.
- 2026-09-17: human rewrote AGENTS rule 3 — `subprocess` is confined to
  `core/tools/process.py` inside `src/ctstudio/`, while `scripts/`, `spikes/` and
  `tests/` may spawn processes directly with argv lists, explicit timeouts and exit-code
  handling; never `shell=True`; spike code is never copied into `src/`. P0-T02 onward
  follows this. No ADR needed (it tightens the wording of an existing accepted rule).
- 2026-09-17: name settled as **CT Studio** (ADR-015 now Accepted). Docs renamed:
  package/CLI `trackstudio` → `ctstudio`, manifest `ctstudio.toml`, app folder
  `.ts/` → `.ctstudio/`, `TRACKSTUDIO_DEV` → `CTSTUDIO_DEV`, `TrackStudioError` →
  `CTStudioError`. Done before any code exists, so P1-T01 writes the new names directly.
- 2026-09-17: **Lorenzi's KMP Editor has no Linux build** — only a Windows `.exe` and a
  macOS arm64 zip, in every release back to v0.7.0 (GitHub releases API). P0-T02 planned
  to install it; it now isn't installed at all and P0-T10 must drive it through Wine like
  BrawlCrate. Affects P0-T02/P0-T10 and the Linux launch contract in TOOLS.md.
- 2026-09-17: bootstrap installs **3 tools, not 5**. uv itself is already present and
  Python 3.12 comes from `uv python install 3.12` (3.12.13, ~4 s), so neither needs a
  catalogue entry. Recorded in TOOLS.md; P0-T02 wording updated.
- 2026-09-18: fixture KMP is complete **except the `[CAME]` opening camera**, which needs
  the four-lines-per-camera layout; compiling therefore reports 2 expected camera warnings
  (asserted by the generator and a test, so a third warning fails the build). P0-T03 allowed
  this deferral; the note landed on **P10-T01**, not P10-T05, because P10-T05 is about
  editor round-trips while P10-T01 is where KMP sections are actually handled.
- 2026-09-18: added `pytest.ini` (marker registry from TESTING_STRATEGY §1) and extended
  `ruff.toml`, both pre-P1 stand-ins that P1-T01/P1-T02 fold into `pyproject.toml`.
- 2026-09-18 (S1): **`wszst check` exit codes are not a pass/fail signal** — valid track,
  warning-laden track and empty archive all exit 2 (`DIFFER`), but a corrupt file exits
  **0** while printing `ERROR #39`. The adapter must parse output and treat `ERROR #` as
  failure. Affects P2-T05 (`wiimm.py`) and P4-T06 (validate node); both updated.
- 2026-09-18 (S1): `check --sections` and `slots --sections` are rejected; **only
  `analyze` is machine-readable** (`--json`/`--sections`). `analyze --json` carries
  `slot_info`, `lap_count`, `n_ckpt0`, coordinate ranges and per-component SHA1s, so
  `slots()` is dropped from the P2-T05 adapter surface in favour of `analyze()`.
- 2026-09-18 (S1): `wszst create` never validates (it builds from an empty directory),
  and `--auto-add` is a **silent no-op** without a library. The app must guard both.
- 2026-09-18 (S2): **calling the add-on's operators is enough** — no context juggling
  needed headless, so the P6 bridge does not need internal-function access. ARCHITECTURE
  §12 and P6-T01 updated with the confirmed entry points.
- 2026-09-18 (S2): `export.minimap` reports a **missing ABMatt as `poll() failed, context
  is incorrect`**, which points at the wrong cause, and it refuses meshes without
  materials. The bridge must check both itself. This also **changed the P0-T03 fixture**:
  KCL meshes now carry a material (collision has no appearance; it is purely for ABMatt).
- 2026-09-18 (S2): `daeExportMethod=AUTO` equals `BUILTIN` on Linux because the bundled
  FbxConverter is a Windows binary. **DAE bytes will differ on Windows CI** — no
  cross-OS byte-comparison tests.
- 2026-09-18 (S3b): **rszst cannot read an ABMatt BRRES** (`Invalid quantization for
  normal data: U16`, exit 255) while ABMatt reads rszst output fine. This one-way wall,
  not a preference, fixes the pipeline order in ADR-004 (now Accepted) and is recorded
  in P7-T01.
- 2026-09-18 (S3b): **`set_texture_formats` is dropped from the ABMatt backend** —
  `set tex0 format:` exits 0 and changes nothing. ADR-004's interface list and P7-T01
  updated; the operation must raise the typed unsupported error instead.
- 2026-09-18 (S3b): ABMatt takes the MDL0 name from the **source filename stem** (no
  flag) and rejects a `<slot>_model.brres` destination that disagrees; `abmatt -c`
  mangles multi-word commands, so command files (`-f`) are the supported route.

## Needs human — BLOCKING
<!-- Question · options · agent's recommendation · what is blocked -->
_none_

## Needs human — non-blocking
- ~~RiiStudio licence / bundling~~ **answered 2026-09-18: never bundle it.** Ship
  detection + a link to the official releases page + an optional user-initiated
  download from the upstream URL; keep it out of the installer. Asking the maintainer
  for an explicit LICENSE is a **Phase 12** question, not a blocker. Recorded in
  ADR-004 and P12-T01/T03.
- ~~S2 add-on wishlist~~ **answered and closed 2026-09-19.** (1) minimap poll message and
  (2) callable export functions returning result dictionaries: both **merged** as add-on
  PR #1 (`ffa905f`); the submodule pin is updated and P6-T01 now specifies the callable
  API with no stdout scraping. (3) a module-name-safe package directory: **declined**;
  the bridge keeps the copy-to-`mkw_utilities` step.
- Auto-add (from S1) still needs a library built from your own game files to test for
  real; I cannot create one here. HC0 question, relevant before P4.

## Blocked tasks
<!-- Task ID · what was tried · what's needed -->
_none_

## Tech debt (each item has a task ID or "Deep Clean #N")
_none_

## Human checkpoint results
<!-- HC0..HC4: date · outcome · issues filed as task IDs -->
_none_
