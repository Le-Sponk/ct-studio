# Architecture Decision Records

Format: **Status** (Accepted / Provisional / Superseded) · Context · Decision · Consequences ·
Revisit when. Append new ADRs at the bottom; never rewrite history — supersede instead.

---

## ADR-001 — Python 3.12 + PySide6 (Qt Widgets) for the application
**Status:** Accepted
**Context:** Desktop app for Windows + Linux that mostly orchestrates external tools, watches files,
shows status, edits settings, and renders a simple 3D preview. Built primarily by LLM agents in a
Linux Docker container; must be testable headlessly. The Blender add-on and ABMatt are Python.
**Alternatives:**
- *Tauri (Rust + TS web UI):* small binaries, fast start; but two languages + IPC boundary increases
  agent error rate, WebKitGTK WebGL quirks on Linux, harder headless GUI testing.
- *C# + Avalonia:* good perf; BrawlLib is WinForms/.NET Framework so no real reuse; less agent fluency.
- *Electron:* heavy, no benefit over Tauri here.
**Decision:** Python 3.12, PySide6 Qt Widgets, numpy/Pillow for data work.
**Consequences:** Heavy lifting stays in native tools (wszst, rszst, Blender) so Python overhead is
irrelevant to build time; we must still guard start-up time (lazy imports) and keep the UI thread
free. Bundles are ~100–150 MB. Headless GUI tests via `QT_QPA_PLATFORM=offscreen` + pytest-qt.
**Revisit when:** packaged cold start misses budget after P13 optimisation, or preview needs exceed
what moderngl in Qt can do.

## ADR-002 — Qt-free core with CLI parity
**Status:** Accepted
**Decision:** All logic in `ctstudio.core` (no Qt). CLI exposes `new`, `status`, `build`, `doctor`,
`open`. GUI is a thin layer. import-linter enforces.
**Consequences:** Agent can test nearly everything without a display; power users can script builds.

## ADR-003 — External tools only via subprocess adapters
**Status:** Accepted
**Context:** ABMatt pins very old dependencies (PyQt5, numpy 1.19, pillow 9) that conflict with our
stack; RiiStudio and Wiimms are native binaries; licences vary.
**Decision:** Never import third-party track tools in-process. Run them as subprocesses through
typed adapters. ABMatt runs from its release binary or an isolated environment.
**Consequences:** Clean dependency tree and licence separation; small per-call overhead (acceptable).

## ADR-004 — Pluggable BRRES backend; rszst imports, ABMatt post-processes
**Status:** Accepted (decided by spike S3; was Provisional)
**Context:** Candidates:
- *RiiStudio CLI (`rszst`)*: `import-brres` from DAE/FBX, `--preset-path` material presets,
  `dump-presets`, `optimize`, `--model-name` (5.11.3+), `brres-to-json`/`json-to-brres` (5.11.2+,
  format may change between releases), fast SZS compression algorithms, best-in-class triangle
  strip/fan optimisation (fewer facepoints → less slowdown risk). Prebuilt for Windows/macOS; Linux
  must be built from source. Alpha software; development pace slowed after 2024. Licence must be
  checked before any redistribution.
- *ABMatt*: DAE/OBJ → BRRES, rich material command language (xlu, cull, blend, layers, TEX0
  formats), materials with matching names inherit previous settings on replace, creates map models.
  Releases for Windows/Linux; last release v1.3.2 (2022); needs `wimgt` on PATH.
- *BrawlCrate*: GUI only, no headless automation → escape hatch, not a backend.
**Hypothesis to test:** rszst for import (quality) + JSON or preset-based material edits; ABMatt as
fallback where rszst is unavailable and for minimap creation.
**Decision:** Define `BrresBackend` interface (import, inspect, apply material settings,
capture/reapply material state). Pick default per platform from S3 evidence.
**S3a evidence:** Alpha 5.11.5 (`09e5754`) builds on Linux with pinned Corrosion 0.4.10,
explicit `<memory>` inclusion and `libstdc++exp` linkage; no source patches.
Help/version and invalid arguments all exit 255 on Linux. See [SPIKES.md S3](dev/SPIKES.md#s3-brres-backend-bake-off-p0-t06a--p0-t06b).
**S3b decision (evidence: [SPIKES.md S3b](dev/SPIKES.md#s3b-fixture-bake-off-and-backend-decision-p0-t06b),
`tests/integration/test_brres_backends.py`):** `rszst` **imports**, ABMatt
**post-processes materials and builds minimaps**, on every platform. Decided by a
one-way interop wall, not preference: ABMatt reads an rszst BRRES, but rszst fails to
read an ABMatt BRRES (`Invalid quantization for normal data: U16`, exit 255). rszst is
also ~22x faster (0.013 s vs 0.293 s) and is the only one with a model-name flag and a
JSON round-trip. Both produce SZS files that pass `wszst check`.
**Consequences:** the pipeline direction is fixed — never feed ABMatt output to rszst.
Because Linux rszst needs a source build (S3a) and its licence is unresolved, ABMatt
must remain usable standalone; it converts, packs and validates on its own. The
interface is `import_model`, `inspect`, `apply_materials`, `capture_presets`;
`set_texture_formats` is deliberately **not** in the ABMatt implementation because
`set tex0 format:` is a silent no-op there.
**Distribution (human decision, 2026-09-18):** **never bundle RiiStudio.** CT Studio
ships *detection* plus a link to the official releases page, and an optional
**user-initiated** download from the upstream URL. It stays out of the installer, so
the unresolved licence (S3a) does not block anything. Asking the maintainer for an
explicit LICENSE is a **Phase 12 question**, not a prerequisite. This is why ABMatt
must stay usable standalone: a user who never downloads rszst still gets a working app.
**Revisit when:** a backend breaks on real tracks at HC2, rszst gains ABMatt-BRRES read
support, or the maintainer grants an explicit licence (P12).
**S5 exception (P0-T08):** the **minimap must use ABMatt, not rszst**. rszst's
`import-brres --model-name map` names the MDL0 but creates no `posLD`/`posRU` bones,
which the game requires; ABMatt creates them, keyed on the destination filename
containing a lowercase `map`. This is a component-level exception to "rszst imports",
recorded here so the P8-T03 implementation is not read as a violation.
See [SPIKES.md §S5](dev/SPIKES.md).

## ADR-005 — Project = plain folder + `ctstudio.toml`; app data in `.ctstudio/`
**Status:** Accepted
**Decision:** See ARCHITECTURE §5–6. Stage folder is directly consumable by `wszst create`.
**Consequences:** Projects are git-friendly and usable without the app; `.ctstudio/` can be deleted.

## ADR-006 — Incremental build graph with content-hash cache
**Status:** Accepted
**Decision:** Nodes with declared inputs/params/tool versions; blake2b cache keys; stat fast-path.
**Consequences:** Minimal redundant work, which is the main performance lever of this app.

## ADR-007 — Blender integration via headless bridge reusing Blender-MKW-Utilities
**Status:** Accepted (entry points confirmed by spike S2)
**Decision:** Add-on as pinned git submodule; `blender -b --factory-startup --python run_job.py`;
JSON job in, JSON export manifest out; one Blender launch per build. Live link (add-on panel that
exports to the project on demand/on save) is a later, optional task coordinated with the human,
because the add-on repo is theirs.

## ADR-008 — Preview with moderngl inside QOpenGLWidget; no BRRES rendering in v1
**Status:** Accepted (confirmed by spike S6, P0-T09)
**Decision:** Render collision, source geometry (`preview_mesh.npz`), minimap and KMP overlay.
**S6 evidence** ([SPIKES.md §S6](dev/SPIKES.md)): headless GL is **4.5 core** (Mesa/llvmpipe),
well past the 3.3 core target; a 200k-triangle interleaved VBO is 13.7 MB and uploads in
under 0.04 s; `QOpenGLWidget` hands moderngl a working context.
**Constraint this imposes on testing:** `QT_QPA_PLATFORM=offscreen` **cannot create a GL
context** (`QOpenGLWidget is not supported on this platform`). Viewport tests must run under
`xvfb-run` with `QT_QPA_PLATFORM=xcb`; the offscreen convention still applies to ordinary
widget tests. `libgl-dev` (for the `libGL.so` symlink) is required alongside the runtime
library or moderngl fails after Qt has already succeeded.
**Not settled by S6:** the ARCHITECTURE §15 preview budget (≥60 fps at 200k triangles on an
integrated GPU). llvmpipe managed ~10 fps, which is a software-rasteriser floor and neither
confirms nor refutes the budget — re-measure on real hardware at HC3.
**Revisit when:** users need to see final BRRES materials in-app (consider `rszst brres-to-json`),
or HC3 shows the §15 budget is missed on real hardware.

## ADR-009 — Licence GPL-3.0-or-later
**Status:** Provisional — confirm at HC0
**Context:** Reusing code from Blender-MKW-Utilities (GPL-2.0-or-later) e.g. `kcl_parse.py` is
compatible with GPL-3.0-or-later. Tools are invoked as separate programs.
**Decision:** GPL-3.0-or-later; third-party notices maintained in `THIRD_PARTY_NOTICES.md`.

## ADR-010 — Dev tooling
**Status:** Accepted
uv, ruff (format+lint), pyright (strict for `core`, basic for `gui`), pytest (+qt, timeout, cov,
benchmark), import-linter, vulture, radon/xenon, pylint duplicate-code, pyinstrument/py-spy.
Single entry point `scripts/check.py` (cross-platform, no Makefile).

## ADR-011 — File watching with watchfiles
**Status:** Accepted
**Context:** QFileSystemWatcher loses track of files replaced by atomic saves and is Qt-bound.
**Decision:** watchfiles (Rust-backed, cross-platform) in core, bridged to Qt in gui.

## ADR-012 — Preserve external material edits by capture-and-reapply
**Status:** Accepted for the mechanism (spike S4, P0-T07); the *coverage* of that
mechanism stays provisional until HC2 confirms it against a real BrawlCrate edit.
**Decision:** Capture with `rszst dump-presets` into `overrides/captured/<component>/`;
reapply with `import-brres --preset-path` on the next regenerate. See ARCHITECTURE §8.
Always back up before overwrite.
**Why not the alternatives** (evidence: [SPIKES.md §S4](dev/SPIKES.md)): all three
candidate routes restore the edit, so the decision is made by failure modes, not
capability. ABMatt `copy`/`paste material` is **rejected as the primary mechanism**:
pasting onto a renamed material leaves the edit applied but deletes the orphaned
texture, exit code 0, and ABMatt 1.3.2's `-a`/`--auto-fix` flag cannot be used to
disable that (`-a 0` parses the value as a command). The JSON merge route is kept as
the **inspection/diff format**, not the capture format: its `.json` is not
self-contained (a `<stem>.bin` geometry sidecar must travel with it) and a
material-only merge silently drops SRT0 animations.
**Consequence the app must implement:** presets match on material name, and an
unmatched preset is skipped **silently**. Renaming a material in Blender therefore
orphans its captured edits with no warning from any tool. The regenerate step must
diff captured preset names against the regenerated material list and surface orphans
to the user.

## ADR-013 — Packaging with PyInstaller one-folder
**Status:** Provisional
**Decision:** Start with PyInstaller (predictable, well known); exclude unused Qt modules; evaluate
Nuitka for start-up/size in P13.

## ADR-014 — TOML for human-edited files, JSON for machine state
**Status:** Accepted

## ADR-015 — Name "CT Studio", package `ctstudio`
**Status:** Accepted (superseded the provisional working name "MKW Track Studio")
**Context:** The planning kit used the working name "MKW Track Studio" with package
`trackstudio` and project data in `.ts/`, pending the human's decision at HC0.
**Decision:** The project is **CT Studio**. Python package and CLI `ctstudio`, project
manifest `ctstudio.toml`, app-managed folder `.ctstudio/`, dev flag `CTSTUDIO_DEV`, base
error `CTStudioError`. Done before P1-T01 writes `pyproject.toml`, so no code changed.
**Consequences:** Docs use the new names throughout; nothing else is pending at HC0 for
the name. `.ts/` never shipped, so no migration path is needed for user projects.

## ADR-016: Evidence gate before P1-T02
**Status:** Accepted
**Context:** P0-T01 confirmed that the planning-only repository has no `scripts/check.py`,
`pyproject.toml` or `uv.lock`. Running the mandatory command exits 2 (missing script).
P1-T02 creates the gate, so requiring it for earlier commits creates a dependency cycle.
Evidence: [environment audit](dev/ENVIRONMENT.md#quality-gate-and-remaining-boundaries).
**Decision:** Supplement ADR-010: until P1-T02, each task records real commands, versions,
exit codes and acceptance evidence, runs any task-specific tests, reviews its diff, and
passes `git diff --check`. Documentation-only tasks also validate local file links.
Do not create a no-op check script or report the absent gate as green. From P1-T02 onward,
the full `check.py` requirement applies, including to P1-T02 itself.
**Consequences:** Phase 0 remains evidence-driven without pulling application scaffolding
forward. No exemption for skipped/weak tests, runtime dependencies or application layering.
**Revisit when:** P1-T02 is implemented; use the full gate thereafter.

## ADR-017 — External editors are launch-only; the app never claims a file opened
**Status:** Accepted (decided by spikes S7 and S8, P0-T10/P0-T11)
**Context:** "Open in…" (P5-T07) and the `editors` adapter (P2-T05) need to know what an
editor launch can be observed to have done. S7 launched all five editors for real; S8 added
the RiiStudio finding that closed the question.
**Decision:** `open_in(tool_id, file)` reports **launched**, never **opened**. One filesystem
path per launch and one process per launch. No success inference from process liveness, window
titles, or editor stdout.
**Why** (evidence: [SPIKES.md §S7](dev/SPIKES.md), [§S8](dev/SPIKES.md), TOOLS.md launch table):
- **Liveness proves nothing.** RiiStudio kept an empty window up after failing to load ABMatt's
  BRRES (`Invalid quantization for normal data: U16`), with no dialog and no exit.
- **Titles prove nothing** for two of five: RiiStudio's is version-only, KMP Cloud's is a fixed
  product name. BrawlCrate and Lorenzi do put the path in the title, but a rule that holds for
  three of five tools is not a contract.
- **RiiStudio's `File:` line is not a receipt either** (TD-001): it is printed only when stdout is
  a tty *and* only after its mandatory GitHub update check completes. With the endpoint
  unreachable the line never appears at all, and upstream Alpha-5.11.5 exposes no flag,
  environment variable, config file or build define to disable that check.
- **No editor we could probe is single-instance** (BrawlCrate, KMP Cloud, Lorenzi measured;
  **RiiStudio is source-read only** — the S7 spike never probed it), so a second launch is a second
  process, never a hand-off.
**Evidence grades, so a later reader does not over-trust this:** bullets 1-2 are pinned by
integration tests; bullet 3 rests on a `network`-marked test that is excluded from the default
suite and skips when GitHub is unreachable (TD-001); bullet 4 is three-of-five measured.
**Consequences:** the adapter surface has no "did it open" query; the UI says "Opened in
BrawlCrate…" only as a past-tense launch statement and offers a Re-check/refresh path instead of
a completion signal; P5-T06 change detection watches the *file*, not the editor. BrawlCrate must
never receive two paths (its `argv[1]` is a node path inside `argv[0]`'s file) and Lorenzi's
editor must receive the path first (it parses no flags).
**Revisit when:** HC1 answers whether a load is observable at all without a tty on the user's own
machines, or an upstream release adds a machine-readable status.

## ADR-018 — Test launches use an extracted game folder, not a patched image
**Status:** Accepted (decided by spike S8, P0-T11)
**Context:** P11's "Build & launch" needs one route from a built `<slot>.szs` to racing it that
CT Studio can start without the user clicking through Dolphin's GUI.
**Decision:** The primary route is the **extracted game folder**: the user's own disc image is
extracted once with `dolphin-tool extract`, installing a build is a plain file copy over
`files/Race/Course/<slot>.szs`, and the launch target is `<game>/sys/main.dol`. Dolphin's
**game-mod descriptor** JSON (Riivolution without the GUI) is kept as an optional second route
(P11-T02b). MKW-SP "My Stuff" stays a documented manual path, not automation.
**Why** (evidence: [SPIKES.md §S8](dev/SPIKES.md), Dolphin section of
[TOOLS.md](reference/TOOLS.md)): route 1 needs no packing step and no XML generation, and
`dolphin-tool extract -i <game>/sys/main.dol -l` verifies the slot path without booting anything.
Route 2 leaves the user's game untouched, which is why it survives as an option, but it carries a
failure mode route 1 does not: a descriptor whose XML is missing, malformed, or scoped to another
game id **still boots, exit 0, silently** (`RiivolutionParser.cpp:352-354` skips invalid patches
with `continue`; no Riivolution log line exists at any verbosity).
**Consequences the app must implement:** never pass the game *folder* to `--exec` (rejected,
exit 1 — append `sys/main.dol`); confirm the `Booting from disc:` log line rather than an exit
code, because a game folder whose `sys/boot.bin` is missing or shorter than 0x20 bytes (a
half-extracted or wrong folder) is **not** rejected — Dolphin silently boots the DOL as a bare
*executable* with no file system, so the track is absent while everything looks fine; create
`Logs/` before trusting file logging, since Dolphin never creates it; drive
`dolphin-emu-nogui` when the app must know an outcome, because `dolphin-emu --batch` sits on a
modal panic dialog instead of failing; treat a successful boot as never-exiting; and if route 2
ships, validate the generated XML in-app, because Dolphin will not.
*(Measured precisely: the DOL header is not what selects the path — a DOL with a zeroed entry
point still boots as a disc. `IsValidDirectoryBlob` keys on `sys/boot.bin`.)*
**Revisit when:** HC3 confirms a patched slot actually loads on the real game, or the user
reports MKW-SP is their real test setup.
