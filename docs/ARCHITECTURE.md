# Architecture

Status: initial design. Sections marked **(spike)** are confirmed or amended in Phase 0.
When code and this document disagree, fix one of them in the same commit.

## 1. Stack
| Concern | Choice | ADR |
|---|---|---|
| Language | Python 3.12 | 001 |
| GUI | PySide6 (Qt 6.11+), Qt Widgets (not QML) | 001 |
| Env/deps | `uv` + committed `uv.lock` | 010 |
| Lint/format/types | ruff, pyright (strict on `core`) | 010 |
| Tests | pytest, pytest-qt, pytest-timeout, pytest-cov, pytest-benchmark, hypothesis (P13) | 010 |
| Architecture enforcement | import-linter | 002 |
| Code health | vulture, radon/xenon, pylint `duplicate-code` only | 010 |
| Numerics / images | numpy, Pillow | 001 |
| Project file | TOML (`tomllib` read, `tomli-w` write) | 014 |
| File watching | watchfiles | 011 |
| 3D preview | moderngl inside `QOpenGLWidget` **(spike S6)** | 008 |
| BRRES backend | pluggable; default chosen by **spike S3** | 004 |
| Packaging | PyInstaller one-folder (evaluate Nuitka in P13) | 013 |

## 2. Layers and import rules
```
            ┌──────────── gui (PySide6) ────────────┐
            │  views, widgets, viewport, Qt models  │
            └───────────────┬───────────────────────┘
┌──── cli (argparse) ────┐  │
└───────────┬────────────┘  │
            ▼               ▼
┌───────────────────── core (no Qt) ─────────────────────┐
│ project · components · build · pipelines · tools ·     │
│ formats · textures · validation · fsutil · errors      │
└────────────────────────────────────────────────────────┘
blender_bridge/  → runs INSIDE Blender; stdlib + bpy only; talks to core via JSON files
```
Contracts (import-linter): `core` ↛ `gui`,`cli`,`PySide6`; `cli` ↛ `gui`; nothing imports `spikes`.
Every GUI feature must be reachable through core APIs, and most through the CLI (`ctstudio build`,
`status`, `doctor`, `open`) — this is what lets the agent test without a screen.

## 3. Source tree
```
src/ctstudio/
  __main__.py            # `ctstudio` with no args → GUI; with subcommand → CLI
  core/
    errors.py  logging.py  platform.py  fsutil.py  events.py
    project/     manifest.py  layout.py  migrations.py  settings.py (user-level)
    components/  registry.py  status.py  (one module per component type if large)
    build/       node.py  graph.py  cache.py  runner.py  cancel.py
    pipelines/   blender_export.py course_model.py kcl.py minimap.py skybox.py
                 kmp.py posteffect.py assemble.py validate.py
    tools/       spec.py registry.py discovery.py process.py
                 wiimm.py rszst.py abmatt.py blender.py editors.py wine.py dolphin.py
    formats/     magic.py kcl.py kmp.py            # read-only parsers
    textures/    analyze.py recommend.py
    validation/  issues.py wszst_check.py kmp_rules.py
  cli/           main.py  commands/*.py
  gui/           app.py main_window.py services.py theme/ widgets/ views/ viewport/ qtmodels/
  blender_bridge/ run_job.py  exporters.py  preview_mesh.py
vendor/blender-mkw-utilities/   # git submodule (pinned commit)
tests/  unit/ contract/ integration/ gui/ e2e/ benchmarks/ fakes/ fixtures/
scripts/ check.py bootstrap_tools.py fixtures/make_fixture_blend.py
spikes/  (Phase 0 throwaway, never imported)
docs/
```

## 4. Core concepts
- **Project** — a folder + `ctstudio.toml`. Loaded into an immutable `Manifest` snapshot; edits
  produce a new snapshot and are written atomically. Unknown TOML keys are preserved.
- **Component** — a track part (course_model, kcl, minimap, skybox, kmp, posteffect, objects,
  track_info). Declares modes (`auto`/`manual`/`template`), inputs, stage outputs, help text, wiki link.
- **ComponentStatus** — `Missing | Stale | Ready | Warning | Error | Manual | EditedExternally`
  plus reasons. Computed from manifest + filesystem fingerprints + `.ctstudio/state.json`.
- **Node** — a build step with declared inputs (files, params, tool versions), outputs, and an
  `impl_version`. Pure w.r.t. declared inputs so it can be cached.
- **BuildGraph / Runner** — topologically ordered nodes, bounded parallel execution, cancellation,
  structured events.
- **ToolSpec / ToolLocation / Adapter** — static description of an external tool; where it was found
  and how to launch it (direct, wine, flatpak-spawn); a typed Python facade that builds argument
  lists and parses output.
- **Issue** — `{severity, component, code, message, hint, source, file?, wiki?}`. All validators
  produce Issues; the GUI shows one list.
- **Event** — dataclass messages (`NodeStarted`, `LogLine`, `NodeFinished`, `StatusChanged`, …)
  delivered through a plain callback. GUI adapts them to Qt signals; CLI prints them or JSONL.

## 5. Project folder on disk
```
MyTrack/
  ctstudio.toml
  files/            # user-supplied manual files (course.kmp, vrcorn_model.brres, …)
  overrides/        # material/texture overrides, captured edits, ABMatt command files, hooks
  build/            # outputs: <slot>.szs, <slot>_d.szs, release/
  .ctstudio/        # app-managed; safe to delete (rebuilt)
    exports/        # Blender exports (DAE, OBJ, PNG, preview_mesh.npz, export_manifest.json)
    stage/          # U8 directory tree → `wszst create` input
    state.json      # last generated output hashes, input fingerprints
    cache.json      # node cache keys
    issues.json  logs/  backups/
```
The `.blend` may live anywhere; the manifest stores its path (relative when inside the project).

## 6. Manifest sketch (`ctstudio.toml`)
```toml
schema_version = 1

[project]
name = "Sponk Speedway"
author = "Le-Sponk"
version = "1.0"
slot = "beginner_course"
blend = "source/track.blend"

[build]
test_compression = "fast"        # mapped to verified wszst flags in the adapter
release_compression = "best"
make_d_variant = true
auto_add = true
extra_wszst_args = []

[blender.collections]           # mapping; auto-detected on project creation, user-reviewable
course = "Course"
kcl = "KCL"
skybox = "Skybox"
minimap = ""                     # empty → derive from KCL

[components.course_model]
mode = "auto"                    # auto | manual
backend = "default"              # resolves to the ADR-004 choice
extra_import_args = []
post_import_commands = ""        # optional ABMatt command file under overrides/

[components.course_model.textures."road.png"]    # only stored when overriding a recommendation
format = "CMPR"
mipmaps = 4

[components.course_model.materials."fence"]
transparency = "cutout"          # auto | opaque | cutout | translucent
cull = "none"                    # front (default) | back | none

[components.kcl]
mode = "auto"
unbean = "lower"                 # passed through to the Blender add-on exporter

[components.minimap]
mode = "auto"
source = "kcl"                   # kcl | blender | file
include_kcl_types = ["road", "slippery_road", "boost_panel", "boost_ramp", "jump_pad"]  # names from flag table

[components.kmp]
mode = "manual"
file = "files/course.kmp"
editor = "lorenzi"

[components.skybox]
mode = "manual"
file = "files/vrcorn_model.brres"

[components.posteffect]
mode = "template"
template_track = "beginner_course"

[hooks]                           # optional power-user scripts, run with documented env vars
post_stage = ""
post_build = ""
```
Machine-specific settings (tool paths, game files folder, recent projects, theme) live in the
user settings file under `platformdirs.user_config_dir("ctstudio")`, never in the project.

## 7. Build graph
```
.blend ──► [blender_export] ──► DAE+PNG ──► [course_model] ──┐
                   │         ──► KCL ─────► [kcl_stage] ──────┼──► [minimap] ─┐
                   │         ──► skybox DAE ► [skybox] ───────┤               │
files/course.kmp ─────────────────────────► [kmp_stage] ─────┤               │
template/manual ──────────────────────────► [posteffect] ────┤               │
                                                              ▼               ▼
                                                        [assemble: wszst create (+auto-add)]
                                                                      │
                                                              [validate: wszst check + own rules]
```
- **Cache key** = blake2b over: canonical JSON of node params, input fingerprints (content hash;
  fast path skips hashing when `(size, mtime_ns)` matches the cached record), tool versions,
  `impl_version`. Unchanged key + outputs present with recorded hashes ⇒ skip.
- **Outputs** are written to a temp path then atomically replaced.
- **One Blender launch** exports everything the build needs (Blender start-up costs seconds).
- **Parallelism**: default `min(4, os.cpu_count())`; nodes that call Blender or write the same
  stage file are serialised via resource tags.
- **Profiles**: *test* (fast compression, skip optional optimisation) vs *release* (best
  compression, `_d` variant, strict validation).

## 8. External edits (reconciliation)
```
generated file hash == state.json hash ? → normal
                 else → status EditedExternally → user chooses:
   1 Keep & capture  → capture material state into overrides/captured/<component>/  → reapplied after every regenerate
   2 Lock as manual  → copy file to files/, component.mode = manual
   3 Discard         → backup to .ctstudio/backups/<timestamp>/, regenerate
```
The capture/reapply mechanism is **`rszst dump-presets` → `import-brres --preset-path`**,
chosen by **spike S4** (ADR-012; ABMatt copy/paste rejected because its autofix deletes
orphaned textures and cannot be disabled). Presets match on **material name**, and an
unmatched preset is skipped silently, so the regenerate step must diff captured preset
names against the regenerated material list and warn the user about orphans — no tool
reports this. Before any overwrite of a file whose hash differs from what the app last
wrote, a timestamped backup is made — no exceptions.

## 9. Running external tools
- `core/tools/process.py` is the only place that spawns processes. Arguments are lists. Output is
  streamed line-by-line by reader threads (no pipe deadlocks), decoded UTF-8 with replacement,
  tails kept for error messages, full output to the build log.
- Cancellation/timeout kills the whole process tree (POSIX process groups; Windows job/tree kill).
- Windows: `CREATE_NO_WINDOW` for CLI tools; GUI editors launched detached.
- Linux: Windows-only GUI tools (BrawlCrate, KMP Cloud) run via a configured Wine prefix; paths
  converted with `winepath`. Sandboxed installs (Flatpak/Snap) handled per lessons from the
  Blender add-on (desktop launches don't inherit shell PATH; sandboxed apps can't see host paths).
- Discovery order: explicit user setting → PATH → standard install locations → `.tools/` (dev).
  Results cached with invalidation; "Re-check" always available.
- Adapters own all flag knowledge. Flags are verified and recorded in `docs/reference/TOOLS.md`.
- **GUI editor launches are launch-only (ADR-017).** `editors.open_in` takes exactly one filesystem
  path and starts one detached process; there is no "did it open" query, because S7/S8 showed no
  editor offers a trustworthy signal (liveness, title and stdout all fail on at least one tool).
  Wine prefix architecture is dictated by the executable: **win32 + dotnet48 + win10** for
  BrawlCrate and KMP Cloud, **win64** for RiiStudio and Lorenzi's Windows build.
- **Dolphin is driven through `core/tools/dolphin.py` (ADR-018).** Launch target is
  `<extracted game>/sys/main.dol`, never the folder; `dolphin-emu-nogui` is used whenever the app
  must observe an outcome, since `dolphin-emu --batch` blocks on a modal panic dialog; a boot is
  confirmed by the `Booting from disc:` log line, not an exit code.

## 10. GUI integration & threading
- The GUI thread only renders and reacts. Disk access beyond trivial reads, hashing, parsing,
  subprocesses and image analysis run in a worker (`QThreadPool` for short jobs, one dedicated
  worker thread for builds). Results return via signals.
- `gui/services.py` owns the current `Project`, the build controller, the watcher bridge and the
  tool registry; views get what they need by injection, not globals.
- Dev mode (`CTSTUDIO_DEV=1`) runs a watchdog that logs UI-thread stalls > 100 ms with a stack.
- Log view is virtualised and capped (e.g. last 20k lines in memory; full log on disk).

## 11. File watching
watchfiles in a background thread watches the project folder, the `.blend`, and referenced
external files. Events are debounced (≈500 ms), coalesced, and turned into status re-evaluation.
Blender's `.blend1` backups and temp files are ignored. Atomic-save patterns (write temp + rename)
must be handled — watch directories, not individual inodes.

## 12. Blender bridge
`blender -b <file.blend> --factory-startup --python run_job.py -- <job.json>` (pattern already used
by the add-on's own tests). `run_job.py` registers the add-on from `vendor/`, performs the requested
exports, writes `export_manifest.json` (files, objects, materials, textures, counts, extents,
skipped objects, warnings, timings, Blender + add-on versions) and exits non-zero with a structured
error JSON on failure. It also writes `preview_mesh.npz` (positions, normals, uvs, material ids)
so the preview never needs a COLLADA parser. Entry points confirmed by **spike S2**: the
operators `kcl.export`, `export.autodesk_dae`, `export_scene.objkcl` and `export.minimap`
all work headlessly; tools reach the add-on through `PATH` (see TOOLS.md / SPIKES.md §S2).
Optional later: a live link panel in the add-on ("Export to CT Studio", auto-export on save).

## 13. Preview
`QOpenGLWidget` + moderngl. Layers: collision (colour by KCL base type, per-type toggles, hover
labels via GPU ID buffer), source geometry (textured, from `preview_mesh.npz`), minimap (top-down
orthographic), KMP overlay (points, routes, checkpoint pairs, objects). No BRRES decoding in v1.
GL resources created lazily and released on project close. `paintGL` only draws.

## 14. Diagnostics
Structured logging (JSON lines) to the user log dir; one log file per build in `.ctstudio/logs/`;
"Copy diagnostics" in Help (versions, tool table, last build log tail, no personal paths beyond
what the user approves); `ctstudio doctor [--json]`.

## 15. Performance budgets (checked by benchmarks / tests)
| Metric | Budget |
|---|---|
| Packaged cold start → dashboard interactive | < 2.0 s |
| Open project + status evaluation (typical) | < 300 ms |
| No-change rebuild | < 1 s |
| UI thread stall (dev watchdog) | never > 100 ms |
| KCL parse, 500k triangles | < 0.5 s |
| Preview: 200k tris load / frame | < 1 s / ≥ 60 fps on integrated GPU |
| Idle memory with project open | < 250 MB |
| Test build excl. Blender export, typical track | < 10 s |
Budgets may be revised with evidence (log in DECISIONS.md); they may not be silently ignored.

## 16. Platform matrix
| | Windows 10/11 | Linux (Mint/Ubuntu, x86_64) | macOS |
|---|---|---|---|
| App | ✔ | ✔ | best-effort |
| Wiimms SZS Tools | ✔ (Cygwin build) | ✔ | ✔ |
| Blender + add-on | ✔ | ✔ | untested |
| RiiStudio CLI | ✔ prebuilt | build from source / unavailable **(spike)** | ✔ prebuilt |
| ABMatt | ✔ release | ✔ release | via pip |
| BrawlCrate | ✔ | via Wine (+ .NET 4.8) | ✘ |
| Lorenzi's KMP Editor | ✔ | ✔ | ✔ |
| Dolphin | ✔ | ✔ | ✔ |

## 17. Safety
No `shell=True`; manifest paths validated to stay inside the project unless explicitly external;
downloads only from official URLs, with checksum verification where published; user consent before
touching game files; backups before overwrites.
