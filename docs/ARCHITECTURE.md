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
Contracts (import-linter): `core` ↛ `gui`,`cli`,`PySide6`; `cli` ↛ `gui`; application ↛ `spikes`.
The contract includes external packages; an AST test additionally forbids `spikes` imports in
scripts/tests and any `blender_bridge` imports beyond stdlib/`bpy`. The three future layer
packages have importable `__init__.py` markers from P1-T03 so import-linter can evaluate
contracts before their implementations exist (core begins in P1-T04, GUI in P1-T06).
Every GUI feature must be reachable through core APIs, and most through the CLI (`ctstudio build`,
`status`, `doctor`, `open`) — this is what lets the agent test without a screen.

## 3. Source tree
```
src/ctstudio/
  __main__.py            # `ctstudio` with no args → GUI; with subcommand → CLI
  core/
    errors.py  logging.py  platform.py  fsutil.py  events.py
    project/     manifest.py manifest_io.py toml_table.py migrations.py project.py lock.py
                 watch.py
                 slots.py slots.json  settings.py (user-level)
    components/  registry.py  state.py  status.py  (one module per component type if large)
    build/       node.py  graph.py  cache.py  runner.py  events.py  part_state.py  build_log.py
                 stage.py  assemble.py  objects.py  validate.py  project_build.py
                 event_json.py
    pipelines/   blender_export.py course_model.py kcl.py minimap.py skybox.py
                 kmp.py posteffect.py assemble.py validate.py
    tools/       spec.py registry.py discovery.py availability.py process.py
                 wiimm.py rszst.py abmatt.py blender.py editors.py wine.py dolphin.py
    formats/     magic.py kcl.py kmp.py            # read-only parsers
    textures/    analyze.py recommend.py
    validation/  issues.py wszst_check.py kmp_rules.py report.py issue_parts.py
  cli/           __init__.py (COMMANDS)  new.py status.py open_file.py doctor.py setup.py build.py
  gui/           app.py main_window.py services.py theme/ widgets/ views/ viewport/ qtmodels/
                 build_controller.py dashboard_builds.py build_log_model.py
                 views/dashboard_follow.py views/issues_panel.py
                 watcher_bridge.py views/dashboard_watch.py
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
  *As built (P3-T03):* `core/components/registry.py` — `COMPONENTS` (dashboard order) and
  `COMPONENT_BY_ID`; each `ComponentSpec` has id, name, one plain sentence, an mkwiiki.org
  page (opened 2026-11-02), modes (the manifest's tuples; first = default), stage outputs
  (`posteffect/` is a folder; objects and track info have none), `required` (all but
  objects), tool ids per mode, and its `ctstudio.toml` table (`objects`: none, `track_info`:
  `[project]`). The skybox has a `template` mode (copy an original track's) with
  `template_track`, as PROJECT_BRIEF §5 and P8-T05 describe.
- **FileKind** (P3-T05) — `core/formats/magic.py`: `identify(path)` recognises SZS (Yaz0), U8,
  BRRES, KMP, KCL, the four post-effect files with a magic, PNG, DAE, OBJ and .blend (plain, gzip
  or Zstandard) from contents only; byte layouts in MKW_DOMAIN §11. Size fields must match, so
  cut-off files are not recognised. Raises `ProjectError` for an unreadable path.
- **ComponentStatus** — `Missing | Stale | Ready | Warning | Error | Manual | EditedExternally`
  plus reasons. Computed from manifest + filesystem fingerprints + `.ctstudio/state.json`.
  *As built (P3-T04):* `core/components/status.py` — `evaluate(project, tools, state=None)`
  returns every part's `ComponentStatus(state, reasons)` in dashboard order. Made parts:
  no record or an output gone → Missing; an output changed, or a file added to an output
  folder → EditedExternally (reported before Stale; never treated as needing a rebuild);
  settings (`settings_key`: the part's table without `file`, plus `.blend` + Blender
  collections when Blender makes it) or an input changed/gone → Stale; Missing/Stale that
  cannot be made now (tool not found, no `.blend`) → Error with every blocker listed. Manual:
  none chosen/not found → Missing, wrong type (`formats.magic`, the registry's `kind`) or an
  empty/non-folder post-effects folder → Error, else Manual. Objects: Warning when auto-add is
  off or Wiimm is missing. Track info: Warning with no author. `core/components/state.py` —
  `state.json` `{format: 1, components: {id: {settings, outputs, inputs}}}`, each file
  `{size, mtime_ns, digest}`; outputs keyed inside `.ctstudio/stage/`, inputs
  project-relative or absolute. Missing/damaged → empty (logged). Unchanged size+mtime → no
  hash; a touched file is hashed once (Fingerprint cache). 20 parts: ~70 ms cold, ~11 ms warm.
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

**As built (P3-T02):** `core/project/project.py` — `Project.create(dir, name, blend=None,
slot="beginner_course", force=False)` makes `files/ overrides/ build/ .ctstudio/`, the default
manifest and a `.gitignore` (`.ctstudio/`, `build/`; an existing one is left alone). It
refuses a non-empty folder unless `force`, and always refuses a folder that already has a
`ctstudio.toml`. A blend inside the project is stored relative with `/`, else absolute.
`Project.open(dir)` loads the manifest and takes the lock; `save` is refused when read-only;
`close()` (or `with`) releases the lock. `core/project/lock.py` — `.ctstudio/lock` is JSON
`{pid, host, token, since}` created with `O_EXCL`. Stale = same host and the pid is gone
(Windows `OpenProcess`/`GetExitCodeProcess`, POSIX `kill(pid, 0)`), or a damaged lock older
than 30 s; a lock from another host is always respected. A takeover runs under a second
`O_EXCL` file `lock.takeover` and re-checks before deleting, so two openers that see the same
stale lock cannot both win. Release removes the file only while it holds our token.

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

**As built (P3-T01):** `core/project/manifest.py` (frozen dataclasses, edit with
`dataclasses.replace`), `manifest_io.py` (`load`/`save`; tomllib reads, tomli-w writes, the
write is atomic), `toml_table.py` (key-path errors), `migrations.py` (`(from_version, fn)`
steps; only v1), `slots.py` (the 42 original tracks and arenas from the generated `slots.json`: file name,
Wiimm's English name and abbreviation, race/arena, cup and position; `find()` accepts any of
the three names; `slot` and `template_track` must be one of the file names). Differences from the sketch: every component may also have `file` (the user's file in
`manual` mode); an optional value is left out of the file, never written as `""`; texture and
material override tables hold only what is overridden; `[components.kmp]` `mode` is `manual`
only and `[components.posteffect]` `mode` is `template | manual`. Keys this version does not
know stay in each table's `extra`, are written back, and are logged once each. Comments are
lost on save (tomli-w); `docs/user/PROJECT_FILE.md` says so.

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
- **Nodes and edges** (P4-T01): `build/node.py` `Node` declares `inputs` (absolute paths; a
  folder means every file in it), `outputs` (at least one, inside the project), `params`
  (plain JSON, copied and read-only), `tools` (registry ids), `resources` and `impl_version`
  (>= 1); two nodes are equal when all but `run` is. A badly made node raises `ValueError`
  naming it. `build/graph.py` `BuildGraph` draws no edges by hand: a step waits for every
  step whose output equals, contains or sits inside one of its inputs (paths compared after
  `resolve()`). The same step given twice is kept once (one Blender export shared by several
  parts); two different steps with one id, or two steps writing overlapping paths, are
  refused. The order puts each step after those it waits for and otherwise keeps the given
  order, so a project always builds the same way. Steps that wait for each other raise
  `BuildGraphError` naming one loop (`stage:kmp → assemble → stage:kmp`); `subgraph(ids)` is
  "rebuild just this" (the ids plus everything they need, did-you-mean for a typo).
  `from_manifest(root, manifest, make_part, finish)` asks `make_part(spec, mode)` for the
  steps of every part with outputs, in dashboard order; `None` means CT Studio cannot make
  that mode yet and becomes a plain error naming the other modes.
- **Cache key** = blake2b over: canonical JSON of node params, each input's path and
  fingerprint (content hash; fast path skips hashing when `(size, mtime_ns)` matches the
  cached record), tool versions, `impl_version`. A new slot with identical bytes is a miss.
  Unchanged key + outputs present with recorded hashes ⇒ skip.
  `build/cache.py` (P4-T02, P4-GATE): `BuildCache.load(root)` reads `.ctstudio/cache.json`
  `{format: 1, nodes: {id: {key, inputs, outputs, issues}}}` (files `{size, mtime_ns, digest}`,
  keyed like state.json: project-relative with `/`, or absolute); missing/damaged → empty
  (logged). `check(node, tool_versions)` → `Lookup(node_id, key, fresh, inputs, issues, edited)`;
  the key takes only the node's own tools (a version must be given, `None` when unknown), a
  folder input as `[path, {name: digest}]` and a missing input as `[path, null]`. Fresh = same
  key and exactly the recorded output files (folders expanded), each unchanged; a hit
  records new mtimes and keeps the issues across repeated skips. `edited` lists output
  files changed by hand since CT Studio last wrote them, even on a forced rebuild. The
  runner copies them into `.ctstudio/backups/<UTC time>/<project-relative path>` before
  replacing them; a failed copy stops the step, leaving the edit. `store(node, lookup)`
  after a run (a declared output not written → `BuildError`, and the step is forgotten),
  `invalidate(id)` (forget the key, not output hashes), `clear()`, `save()` (atomic, only
  when changed). Thread-safe for the runner.
- **Runner** (P4-T03a): `build/runner.py` `run_build(graph, cache, request, on_event, *, cancel,
  jobs)`. The calling thread schedules and delivers events (`build/events.py`: `BuildStarted`,
  `NodeStarted`, `LogLine`, `CommandRun`, `NodeSkipped`, `NodeFinished`, `NodeFailed`,
  `BuildFinished`) one
  at a time; steps run in a `ThreadPoolExecutor` of `jobs` threads (default `min(4, CPUs)`),
  closed before return. A step starts when every step it needs ran or was skipped and none
  of its `resources` is held; a waiting step does not hold up later ready ones. Fresh in the
  cache → `NodeSkipped`; after a run the outputs are stored, and the cache is saved at the
  end (also on error). First failure or a cancel: nothing new starts, running steps finish
  (`ctx.cancel` is the build's `CancelToken`); `Cancelled` counts as cancelled only when the
  user cancelled. A non-CT Studio exception from a step is logged and shown as `BuildError`.
  If the event receiver raises (P5-T03a / TD-012), its exception propagates: no more steps
  start or callbacks run, but already submitted workers finish. Their queued results and log
  lines are drained after joining the pool, before saving the cache and part state, so reused
  outputs cannot be left without their completed part records. If recording or saving also
  fails during error cleanup, the original exception is kept, other results and independent
  saves are still attempted, and secondary failures are logged. No success event is fabricated.
  `BuildSummary(outcome, ran, skipped, failed, cancelled, not_run, issues, duration, log)`.
- **Part state** (P4-T03b, `build/part_state.py`): a step that makes a track part names it
  (`Node.component`, a part with outputs, one step per part). After it runs (or is skipped
  while state.json has no record of the part) the build records the part in `state.json`:
  settings key, its outputs (folders expanded) and the user's files it was made from: the
  inputs of the step and of every step it needs, minus files some step writes (the `.blend`,
  not the export). Saved once at the end, merged over the newest file; failed or cancelled
  steps record nothing, so status stays Missing/Stale.
- **Manual stage** (P4-T04, `build/stage.py`): `manual_parts(root, manifest)` gives
  `from_manifest` a step `stage:<part>` per part in manual mode. It checks the chosen file
  with the dashboard's own type check (`components.status.type_problem`), then copies it
  under its game name in `.ctstudio/stage/` (`course.kcl`; post-effects as a whole folder,
  swapped in so removed files go). A file is copied to a temporary name and replaced; a
  folder is copied beside the old one, which is put back if the swap fails. No file chosen,
  not found, wrong type, inside `.ctstudio/`, or a failed copy each fail the step with one
  `Issue` (`STAGE_*` code, hint, file, wiki) raised as `node.StepFailed` and carried in
  `NodeFailed.issues` and `BuildSummary.issues`. Unchanged file → skipped (cache).
  Hard links are not used (see STATUS Plan changes).
- **Assigning a supplied file** (P5-T04a, `components/assign.py`): `assign_file(project,
  part, source, *, reference=False)` → `Assigned(manifest, file, backup, manifest_backup)`.
  Before it touches anything it refuses, with a `ProjectError` and hint: a read-only project,
  ctstudio.toml no longer matching the open project, a part without its own manual mode, a
  missing source, a source inside `.ctstudio/` or containing it, a source overlapping the copy
  target, and the wrong type (`status.type_problem`, as status and the build use). By default
  the file, or the post-effects folder, is copied to `files/<game name>` (`course.kcl`,
  `posteffect/`); `reference=True` records the source instead (project-relative with `/` when
  inside the project) and copies nothing. An identical existing copy (byte-compared, folders
  entry by entry: same names, files vs folders, bytes) is left alone. Paths that cannot be
  resolved or read become a `ProjectError` too. Otherwise the copy is staged in a hidden folder beside the
  target and type-checked again; a different existing copy is backed up with
  `backups.save_copies` to `.ctstudio/backups/<UTC time>/files/…` (an incomplete backup
  folder is removed again) and set aside; the copy is
  moved in; ctstudio.toml is saved with `replace_with_backup(..., expected=raw)` (mode manual
  and file). If that save fails the new copy is taken out and the previous one put back; a
  previous copy that cannot be put back is kept and named in the error, never deleted. The
  caller publishes the returned manifest; the call blocks (GUI: run it on a worker).
- **Assemble** (P4-T05a, `build/assemble.py`): `assemble_step(root, manifest, profile)` reads
  the whole `.ctstudio/stage/` folder (so it waits for every stage step) and writes
  `build/<slot>.szs`, plus the identical `build/<slot>_d.szs` when `make_d_variant`.
  `wszst create` uses the profile's compression (test/release) into a temporary folder in
  `build/`; `wszst list` must show every staged file except dot-names, which wszst skips;
  only then are the outputs replaced, so a failure keeps the last good SZS. Nothing staged,
  a file missing from the archive, or a locked SZS → `StepFailed` Issue (`ASSEMBLE_*`).
  Objects (P4-T05b, `build/objects.py`): with auto-add on and a library set
  (`assemble_step(..., library)`, from the user settings key `auto_add_library`), the
  library is checked with `wszst autoadd -vv` every assemble and passed as `--auto-add` only
  when usable; the library folder is a step input. `wkmpt` lists the objects the staged KMP
  places and Wiimm's files for each; one warning (`OBJECTS_*`) per object whose files are in
  neither the stage nor the usable library, per unknown id, and for an unusable library.
  Warnings never stop the build.
- **Input keys** (P4-T08): `BuildCache._keyed` resolves each file once and the project
  folder once per cache (`components.state.resolved_key`); `Path.resolve` is slow on
  Windows and a no-change check of 1,000 inputs spent 0.94 s in it (now 0.25 s).
- **Validate** (P4-T06, `build/validate.py`): `validate_step(root, manifest, profile,
  strict=None)` reads `build/<slot>.szs` and writes `.ctstudio/issues.json` (`format`,
  `track`, `issues`; files inside the project stored relative). One error
  (`VALIDATE_PART_MISSING`, with the part's wiki link) per required part whose `sha1_*` is
  empty in `wszst analyze --json`, then `wszst check`'s findings without its duplicate
  "Missing file" lines for those parts. Test builds never fail on findings; strict (release
  by default, or the caller's choice) fails on any error with `VALIDATE_STRICT`, reporting
  every finding (`StepFailed(issue, also=...)`).
- **Issue report** (P5-T05a, `validation/report.py` + `validation/issue_parts.py`, read by
  the Issues panel; runs no tool): `load_report(root)` reads `issues.json` (None before the
  first check; a damaged, unreadable or absurdly nested file is a plain `ProjectError`).
  `part_of(issue, root)` names the card a finding is about: its part id; the model a check
  section names (`vrcorn_model`, or `course_d_model`, the model Wiimm's `_d` tracks carry);
  one of the part's files or a folder part (`posteffect/`), judged only inside the project
  so a project kept in a folder called "posteffect" is not one; or, only for a finding about
  the whole SZS (`archive`; CT Studio's own steps name their part), the part its measured
  wording names ("Optional file: ./posteffect/...", "File 'vrcorn_model.brres' has N
  vertices", "minimap MDL", "Track will|may|most likely (only|also|not) run at slot N").
  Extra files, effects, object models and totals stay under "Whole track", which comes last
  (on the 99 retail tracks: 77 of 1,048 findings). Parts follow dashboard order; within one,
  errors, warnings, hints, then notes, otherwise as found. `counts_text` ("1 error, 5
  warnings and 2 notes") and `report_text`, the "Copy report" Markdown: track, counts, a
  section per part with its help page, each finding with its hint and file (a code span
  that reads back as the same path; project files relative with "/"); text is escaped and
  folded to one line so a message, help link or project name cannot add headings or lists.
  A saved file whose text UTF-8 cannot hold, or with a NUL in a path, is refused too.
- **Issues panel** (P5-T05b, `gui/views/issues_panel.py`): the status thread reads the report
  with each status check (`StatusResult.issues`/`issues_problem`; an unreadable report never
  hides the statuses), so it is fresh on open, Refresh and after every build and the UI thread
  never reads it. The panel only displays: groups with counts, the selected finding's next
  step, file, part and help page, and "Copy report". A click or Enter on a finding emits
  `part_requested`; `Dashboard.focus_card` scrolls the enclosing scroll area to that card and
  focuses its first usable button (cards are click-focusable, named for screen readers).
  Switching project clears it at once; a failed check keeps the last report. Saved help links
  are restricted to HTTPS `mkwiiki.org/wiki/` URLs (no credentials or nonstandard port); an
  invalid issue link falls back to the registry page, or disables help for a whole-track issue.
- **Build a project** (P4-T07a, `build/project_build.py`, shared by `ctstudio build` and the
  Build page): `plan_build(root, manifest, profile, only=, configured=, library=)` gives the
  steps (a stage step per manual part, then assemble and validate; `only=PART` = that part's
  steps, no packing) and finds every tool they use as doctor does (a path set in CT Studio
  wins; PATH, usual folders, a checkout's `.tools/`; only programs started directly). A
  missing tool raises `ToolNotFound` before anything runs. Versions for the cache come from
  the version cache/probe (None when unknown). `build_project(plan, on_event, cancel=,
  force=)`; `force` forgets the plan's steps only.
- **`ctstudio build`** (P4-T07b, `cli/build.py`): takes the project lock, reads tool paths
  and the auto-add library from user settings, runs `build_project` on a thread named
  `ctstudio-build` while the main thread waits in short joins, so Ctrl+C sets the cancel
  token (a Ctrl+C before the thread starts still cancels). Text output holds each step's log
  lines until it ends; `--json-events` prints `event_json.event_to_json` lines whose schema is
  the JSON block in `docs/dev/CLI.md` (checked by the tests with `tests/unit/json_schema_check.py`).
  Exit 0/1/2/3.
- **Issues survive a skip** (P4-T06): the cache stores each step's issues with its entry, and
  a step skipped as unchanged reports them again (`NodeSkipped.issues`, the summary, the
  log marked "found before"). Old cache files without issues read as none.
- **Build log** (P4-T03b, `build/build_log.py`): `.ctstudio/logs/build-<UTC time>.log`, one
  UTC-stamped plain line per event, flushed as it goes; then only the newest 20 `build-*.log`
  are kept. A log that cannot be written is reported in the app log, never fails the build;
  `BuildSummary.log` is then `None`.
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
  P2-T03 implements `run()` (absolute argv only, inherited env plus additions, bounded 50-line
  tails, optional appended UTF-8 log, typed `ToolNotFound`/`ToolFailed`/`ToolTimedOut`/
  `Cancelled`) and `launch_detached()`. Callbacks run on the caller's thread in arrival order.
  P5-T03e33a: `run(..., sensitive=[...])` replaces each listed value with `<redacted>` (one
  pass, longest first) in every shown argv (command report, tool log, `ToolFailed`/
  `ToolTimedOut`) and in the tool's output lines (callback, log, tails); the tool gets the
  real argv. Executable path, working folder and environment are not covered. After a
  successful start it reports the shown argv through `core/tools/commands.py` to the reporter
  that `reporting()` installed on the same thread. The runner installs one around each step's
  `run`, turning reports into `CommandRun` events (redacted argv plus `command_text`:
  Microsoft C runtime quoting on Windows, not cmd.exe escaping; `shlex.join` elsewhere;
  round-trip tested through the real OS parser). Tool output and step log text never become
  commands; runs outside a step, or on other threads, report nothing. The disk build log gets
  one `command:` line per run; `--json-events` gets a `command` event.
- Cancellation/timeout kills the whole process tree (POSIX sessions + `killpg`; Windows
  kill-on-close job objects, assigned while the tool is suspended — ADR-024). Helpers left
  behind after a clean exit are also stopped.
- Windows: `CREATE_NO_WINDOW` for CLI tools; GUI editors launched detached.
- Linux: Windows-only GUI tools (BrawlCrate, KMP Cloud) run via a configured Wine prefix; paths
  converted with `winepath`. P2-T05g2 (`core/tools/wine.py`): the PE header decides the
  prefix architecture and a mismatch is refused before launch; the launch is watched for 3 s
  (`launch_detached(watch=)`) because Wine reports a wrong prefix or missing .NET by exiting
  at once. Sandboxed installs (Flatpak/Snap) handled per lessons from the
  Blender add-on (desktop launches don't inherit shell PATH; sandboxed apps can't see host paths).
- Discovery order: explicit user setting → PATH → standard install locations → Flatpak
  (Blender only) → managed copies (`ctstudio setup`, e.g. rszst) → `.tools/` (developer
  fallback, only in a source checkout: `pyproject.toml` beside `src/`; P2-GATE).
  Results cached with invalidation; "Re-check" always available.
  P2-T02a implements the filesystem-only half in `core/tools/discovery.py`: executable-file
  validation and launch metadata on both OS branches, Wiimm/Blender standard locations,
  exported Flatpak Blender app identity and opt-in `.tools/` development paths. A Flatpak
  location names the `flatpak` executable as `path` and `org.blender.Blender` as `app_id`.
  It does not launch tools or claim a version. `core/tools/versions.py` (P2-T02b, ADR-023)
  then runs only a spec's documented `version_args` + `version_regex` through the runner,
  up to 8 at once with a 10 s timeout each; Wine locations and GUI editors are never started
  for a version. Results persist in `<user config>/tool-versions.json`, keyed by tool id +
  resolved path + size + mtime (Flatpak: launcher + app id), so a changed file is probed
  again; failures and timeouts are reported, never cached; `force=True` re-checks.
  In a sandbox, host `/usr`/`/opt` are not treated as reachable installs.
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
  P5-T03e31 provides `gui/build_log_model.py`, a Qt list model used by the dashboard log
  panel (e32). It retains the newest 20,000 physical rows under a separate
  2,000,000-message-character budget, caps each message at 4,096 characters and each step ID
  at 128, and visibly marks truncated text. Limits count Unicode characters, not encoded
  bytes; step IDs have their own per-row bound. CRLF/CR become LF; empty/trailing rows are
  retained. Whole-row omissions increment an eviction counter; clear resets it. Standard
  remove/insert notifications preserve surviving persistent indexes, without per-append
  model resets. The GUI-thread model stores no hidden unbounded originals and does no I/O;
  the existing complete core disk log is unchanged. Ordinary LogLine text stays literal,
  not a source of commands. P5-T03e33b: a core `CommandRun` (e33a) becomes one bold "Ran:"
  row whose `LogRole.Command` holds the exact command text (line breaks shown as ↵ on the
  row only); it counts against the character budget and leaves with its row. A command that
  exceeds the line cap (shown cut) or whose row plus copy text exceeds the character budget
  (shown whole) keeps no copy text (tooltip: use the disk log).
  `BuildLogPanel.copy_command` (Ctrl+Shift+C, widget-scoped, plus the right-click menu)
  copies only `LogRole.Command` of the current row and is enabled only on such a row; while
  the menu is open it acts only on the row it opened on (a `QPersistentModelIndex`; none
  below the rows), so eviction never redirects it to a newer command. Qt's own Ctrl+C keeps
  copying the displayed line.

P5-T01a: `gui/services.py` `AppServices` holds the current `Project` (opened, so locked, by this
app; opening the same folder again keeps it, opening another closes the first only once the new
one opened; neither while a build runs), the `ToolsService` and the `BuildController`
(`gui/build_controller.py`). The controller runs one build at a time on a named Python thread
(`ctstudio-build`): reading the user's settings, `plan_build` (finding tools, probing versions) and
`build_project` all happen there. Core events come back through a parentless relay `QObject` as
queued signals (`build_event`, then `finished` with the summary or `failed` with the exception;
`notice` for a damaged settings file, `running_changed`). Each build has a generation number, so
signals queued by a build that `shutdown` already waited for are dropped. A read-only project is
refused (`project_build.check_buildable`, shared with `ctstudio build`). Deleting the controller
cancels the build; `AppServices.shutdown` cancels, waits, then closes the project, and keeps it
open (locked) if the build did not stop in time.

P5-T03e1: the dashboard's future build actions go through `AppServices.start_build`, not a
widget's enabled state. It validates the current project and rejects read-only, editing,
launching, already-building and pending/running status-check states using memory only, then
passes release/force/component options unchanged to the existing worker. Build completion
joins that worker before releasing its running owner; interrupts and startup failures are
reported without stranding ownership. Buttons/live part progress and the bounded log remain
T03e2/T03e3; no tool adapter or core build semantics change in e1.
For supported CPython 3.12/3.13, `threading.enumerate()` includes pending native bootstrap;
classification snapshots it before reading `ident`, which remains set after a worker exits.
An interrupted pending start stays cancelled/owned and shutdown returns False without waiting
on unacknowledged bootstrap. Once it completes, normal joined delivery reports the original
startup exception. Shutdown rechecks ownership after its synchronous idle notification, so a
callback-started replacement worker cannot be reported as stopped or have its lock released.

P5-T03e21: `gui/views/build_controls.py` is a signal-only native-palette build bar, first
exercised separately in GUI tests and embedded by T03e22. `build_requested(bool)` distinguishes
release from test, and `cancel_requested()` asks the owner to stop; neither signal performs
I/O. Explicit `set_state(enabled=..., running=...)` avoids caching disabled ancestors. Known
step IDs give deduplicated progress (unchanged/skipped steps count); unknown IDs are ignored.
Planning is indeterminate, and `BuildFinished` alone never publishes a final result: only
`show_summary`/`show_error` from the joined owner does so. Cancelling disables repeated cancel
requests without presenting completion. Labels use plain text, wrap bounded summaries and
keep complete notices in tooltips/accessibility text. Shortcuts are Ctrl+B test, Ctrl+Shift+B
release and Esc cancel, active only for visible/enabled controls. T03e22 owns current-project
routing, AppServices eligibility, live cards and dashboard/window integration; T03e3 owns the
bounded log. No new core semantics or tool operations are introduced by e21.

P5-T03e22: `gui/dashboard_builds.py` binds the build bar to the dashboard's current project.
Requests go only through `AppServices.start_build`, with a run snapshot of the project, root
and manifest captured before calling it (startup failure can be synchronous). MainWindow
injects the welcome/history busy guard; eligibility uses explicit state, not a disabled
ancestor's effective button state. Build events, notices and joined outcomes are rendered only
while the service and displayed project still match that snapshot. Same-project navigation
preserves progress; a new/changed binding clears the previous run's presentation. Project
header actions use a two-column grid, preserving creation/tab order and complete native labels
at minimum width even with wider desktop font metrics (Ubuntu's 150% case caught the old row).
Component mode text sits above its change button: Ubuntu's full-app enlarged-font log check
exposed their combined minimum width exceeding half the dashboard. Native labels and logical
mode/copy/More focus order remain intact; no font shrinking or horizontal-overflow exemption.
Known `stage:<component>` steps receive separate plain-text card overlays; assembly/validation
remain overall progress. A step's done/unchanged/error/cancelled/not-run state never overwrites
its last checked component status. The existing AppServices completion refresh is reused,
not duplicated. Cancellation delegates to the existing worker and retains its project owner.
Repeated refused closes show the dashboard and stopping notice without rebinding or requesting
another status check. No new build adapter or worker is introduced here.

P5-T03e32: `gui/views/build_log.py` presents that bounded model in a collapsed-by-default
`QListView` above the build bar. Matching `LogLine` events use the same captured-run guards;
collecting is independent of expansion. A new accepted request clears the old messages while
preserving expansion, rebinding also collapses, and same-project navigation/outcomes retain
the log. Native list selection/keyboard and internal scrolling keep long output out of the
outer dashboard's width. A caption reports retained/omitted history. Deferred following is
coalesced through one owned single-shot timer, stops when the reader scrolls back, and resumes
at the end. A private list subclass distinguishes native layout range clamping from reader
scrolls. Persistent top-row/pixel anchors remain authoritative through all native batches;
incomplete native hit-testing uses a logarithmic lookup of measured geometry, not a uniform
row-size assumption. If that row was evicted, the oldest retained row is shown. End explicitly
resumes following, including an immediately appended burst. It does no I/O. Ordinary output
stays literal; trusted command provenance/copying is deliberately e33.

P5-T03e34: `gui/views/dashboard_follow.py` keeps the outer dashboard scroll area at its end
while a build presentation is current, so the newest log lines, build bar and a late
result/error stay visible in small windows. `DashboardBuilds` starts it for an eligible request
(so a start failure shown at the bottom is revealed too) and stops it on rebinding; MainWindow attaches it to `dashboardScroll`. It reacts to the
scroll bar's range changes (each queued layout pass), not to build events, so it never scrolls
to a stale range. A reader scrolling the dashboard up pauses it until they return to the end.
It never moves keyboard focus, owns no timer or thread and does no I/O.

P5-T01b: `gui/status_service.py` `StatusService` works the part statuses out on a named thread
(`ctstudio-status`): the user's settings, `availability.available_tools` (discovery only) and
`components.status.evaluate`. `request(project)` restarts a 300 ms single-shot timer, so a burst
gives one run; a request while a run is going gives exactly one more run afterwards, for the
newest project. `updated` carries a `StatusResult` (root, statuses, settings problem) and
`failed` the exception, both on the UI thread; `clear` (project closed) drops a result still to
come. `AppServices` asks for statuses when a project opens and after every build, finished or
failed. `gui/watchdog.py` `StallWatchdog` (started by `run_gui` only when `CTSTUDIO_DEV=1`) beats
a 25 ms precise timer on the UI thread; a named watcher thread (`ctstudio-watchdog`) logs a
warning with the UI thread's stack (`sys._current_frames`) once per stall longer than 100 ms.

P5-T02a: `gui/views/new_project.py` `NewProjectWizard` (pages in `new_project_pages.py`): name
and folder, .blend (optional), track to replace (searched by words of the name, abbreviation or
cup), summary. The folder is named from the track by `folder_name` (characters Windows forbids
become `_`, trailing dots and spaces go, reserved names such as `CON` get a `_`). Each page's
check is a single look at one folder or file, so it stays on the UI thread. Finish runs
`Project.create` on a named thread (`ctstudio-new-project`), joined before the wizard closes;
Back, Finish and Cancel (and Escape) are off meanwhile, a failure is shown on the summary page,
and the project is handed over open (locked) as `wizard.project`. `MainWindow` takes
`AppServices`; File → New project… (Ctrl+N) makes a fresh wizard each time, passes the new
project to `AppServices.adopt` (refused while a build runs, closing the new project so no lock is
left) and shuts the services down when the window closes, giving the lock back.

P5-T02b: the shell shows `gui/views/welcome_page.py` `WelcomePage`: New, Open (Ctrl+O),
recent folders and explicit missing-folder labels. `gui/recent_projects.py` `RecentProjects`
loads `recent_projects` from the user's settings, resolves/deduplicates paths, keeps the newest
10 and preserves unknown keys/tool settings with a backup on save. Missing entries stay until
removed; Remove changes only the list. Damaged settings/history are shown without overwriting.
A single named worker (`ctstudio-welcome`) handles checks, opens and history writes; busy actions
are disabled. Results return through a queued relay and the worker is joined before delivery.
The receiver owns an opened project; shutdown closes one still awaiting delivery and suppresses
queued results. A window refuses to close if welcome/build/status work has not stopped in time.
Successfully created and opened projects are remembered; history-save failure does not undo an
open. An already-current project is reused rather than reacquiring its own lock read-only.

P5-T03b: `gui/views/dashboard.py` consumes `StatusService` results without checking files on the
UI thread. `component_card.py` uses the registry and shared status words for all eight parts,
native icons, plain-text summaries, and complete tooltip/accessible reasons. Path copying is
lexical: supplied file, planned stage output, or manifest; Objects has no single path. The
header shows project folder, replacement file, optional Blender source and read-only reason.
Refresh is off while checking/building; errors retain last good statuses, closed/other-root
results are ignored, and returning mid-build does not clear checked statuses. A scroll area
keeps all controls keyboard-reachable. Opening/creating shows the dashboard; View offers
Recent projects (Ctrl+H) and Project dashboard (Ctrl+D), keeping the project lock. Welcome
progress, navigation/history errors and shutdown-timeout explanations remain visible rather
than being hidden by the dashboard switch. Component/launch actions and build/log controls
remain separate tasks.

P5-T03d: `gui/component_modes.py` adds a blocking mode service using registry capabilities.
It changes only the selected component's mode, retaining inactive file/template/custom settings
and unknown keys. It never moves generated/manual files, starts builds or publishes the live
manifest. The stable loader and `persist_snapshot` commit path are shared with project details;
both still reject read-only/closed/foreign/stale state, including no-ops, and pass expected
bytes into replacement after staging. Callers must own the lock/busy lifetime, join before
publishing and refresh statuses; dashboard controls follow in T03f, launch actions in T03g.
No widget changes or new launch contracts are introduced in that persistence-only slice.

P5-T03f: `ComponentCard` exposes signal-only mode entry/overflow actions, plus lexical path
copying. The dashboard gates mutating actions while checking/building/editing/read-only;
the window rechecks ownership and registry capabilities before creating an editor. Eligibility
comes from explicit application/project/path state, not effective widget-enabled flags that
include temporarily disabled ancestors. Menu checkmarks stay at the persisted mode until a
successful rebind. `ComponentModeDialog` reuses
`ProjectDetailsDialog`'s joined-worker, Save/Cancel and modal lock ownership via small field/
loader hooks, rather than introducing another thread owner. The window shares editor finish/
close handling, invalidates status results and rebinds only after a successful save; cancel
and errors retain last-good cards. Navigation also disables the dashboard during Open/history
work. File assignment, launches and GUI build controls remain separate tasks.

P5-T03g: `gui/blender_launch.py` provides a blocking project-aware Blender launch service.
It uses the live project's chosen source and freshly loaded machine tool settings, refuses
read-only/closed projects, missing source and preparation-time project changes, and fails closed
on damaged settings rather than silently discovering another executable. The existing measured
`core.tools.editors.open_in` adapter validates the document and starts the detached editor;
its launch result and warnings pass through unchanged, never claiming the document loaded.
The service writes nothing and does not install/enable add-ons. Its caller must hold project
ownership and run it off the UI thread; joined dashboard launch controls follow in T03i.
The add-on remains the tested, pinned Le-Sponk fork, not a moving branch.

P5-T03h: `gui/folder_reveal.py` resolves current registry/manifest component locations for
inspection, using `core.tools.folders.open_folder` to dispatch an existing directory to the
system file manager. File outputs use their containing folder, even before that file is
built; folder outputs and supplied post-effect folders use the directory itself. Missing
folders and components without one location are errors, not requests to create directories
or open an unrelated ancestor. Read-only and closed project snapshots remain inspectable;
preparation-time root/manifest changes are refused. No project/settings/lock writes or file
editing occurs. The portable adapter launches only absolute directory arguments through the
existing detached runner: Windows system Explorer, Linux `xdg-open` with an early-error watch.
Its receipt proves dispatch, not that a desktop displayed the folder. T03i owns off-thread
invocation, current-project lifetimes and dashboard controls; no widgets change in T03h.

P5-T03i: `gui/launch_controller.py` owns one joined `ctstudio-launch` worker that calls the
T03g/T03h services, capturing project/root/manifest at start. Its relay is not a child, so a
late emit cannot touch a deleted owner; `busy` stays true until the UI-thread delivery joins the
worker, and typed errors, crashes and interrupts all arrive as one `LaunchResult`. A timed-out
`shutdown` keeps ownership. `AppServices.start_launch` checks eligibility from memory only
(Blender needs writable + source; folders allow read-only) and refuses switching, adopting,
closing, details and shutdown while a launch is busy. The dashboard and cards only emit
requests; `MainWindow` routes them, and the dashboard shows a separate launch notice that
status checks never overwrite, ignoring results whose project, root or manifest are stale.

P5-T04b: the same owner runs one `assign_file` call (`LaunchController.assign`, injectable
`assign=`), so a file assignment, a Blender launch and a folder reveal never overlap and every
existing launch guard (switching, adopting, closing, editors, shutdown) also covers it.
`AppServices.start_assign` refuses from memory only (no project, read-only, editing, build,
launch or status check busy, unknown part); `assign_file` checks the rest on the worker. Cards
of parts with a manual mode and their own table accept one local dropped file or folder and
offer Choose file… / Reference file in place… (injected `choose`); a drop is always accepted
as a copy (never a move, so a file manager cannot delete the original) and only when the drag
allows copying. Cards only emit `assign_requested` and show the outcome in a per-card note
(wording in `gui/assign_text.py`; long paths are shortened there, full ones go in the tooltip). On a fresh `LaunchResult` (source
set) the dashboard publishes `Assigned.manifest` on the UI thread after the join, rebinds the
cards and rechecks statuses; a refusal, crash or interrupt publishes nothing.

P5-T03c: `gui/project_details.py` is a blocking persistence service. A `DetailsSnapshot` retains
exact manifest bytes plus the parsed immutable manifest; save refuses a stale disk file, live
manifest, different project or lost write lock, validates slot/source on the worker, preserves
other and unknown values, and uses `replace_with_backup` for changed writes. The expected
bytes are checked again in the replacement commit path after staging/fsync, so a change during
preparation is refused without overwriting the unexpected destination. This is optimistic
conflict detection, not cross-process compare-and-swap: an unrelated writer can still race
between the final check and `os.replace`; the UI docs advise against concurrent manual editing.
It never mutates
`Project.manifest`; the receiver publishes the saved snapshot on the UI thread after joining.
`gui/views/project_details.py` is a modal Save/Cancel dialog, with a named joined worker for
load/save, error banner and busy guards. While open it owns `AppServices.editing`, so navigation,
adoption and project closure cannot release the lock; the main window refuses closing during
an active operation. Successful save invalidates queued status results, rebinds the updated
header/cards and requests fresh statuses. Cancel retains the existing cards. No tool is launched.

P1-T06 shell (now extended by P5-T02/P5-T03b): `ctstudio` with no arguments opens the Qt Widgets welcome;
Help → About shows package version, GPL-3.0-or-later and an explicit third-party-notices
placeholder. Widgets keep Qt's native palette (no hard-coded stylesheet), so a system palette
change reaches open windows. `ctstudio --offscreen-smoke <png>` forces offscreen before importing
Qt, renders a PNG and exits without the event loop; it refuses an existing destination rather
than overwriting user work. `--version`/`--help` remain Qt-free. On Windows the offscreen plugin
can enumerate zero system fonts; only in that case the shell loads the installed Segoe UI font
from `%WINDIR%/Fonts` (Linux fallback: system DejaVu Sans) so screenshots have real glyphs.
No font is bundled. GUI screenshots are reviewed from `tests/artifacts/screens/` in light/dark and
at 150% scaling; project slot/source edits are implemented, while component/launch actions
and build/log controls remain P5-T03d/e.

## 11. File watching
watchfiles in a background thread watches the project folder, the `.blend`, and referenced
external files. Events are debounced (≈500 ms), coalesced, and turned into status re-evaluation.
Blender's `.blend1` backups and temp files are ignored. Atomic-save patterns (write temp + rename)
must be handled — watch directories, not individual inodes.

Implemented in P5-T06a. `core/project/watch.py` `watch_plan(root, manifest)` lists what to
watch: the project folder recursively, plus each folder outside it that holds the `.blend` or a
supplied part's file (flat, for those names only; an outside post-effects folder is watched
itself). `ProjectWatcher` runs one named thread for the project folder (`ctstudio-watch`) and,
when needed, one for outside folders (`ctstudio-watch-outside`), with watchfiles' default filter
off and `ChangeFilter` instead: `.ctstudio/` except the made files in `.ctstudio/stage/`, the
finished tracks in `build/`, `.git/`, and `.blendN`/`.blend@` are ignored; outside folders count
only the watched names (case per the system's rule; links and Windows short names resolved).
A burst arrives once (`DEBOUNCE_MS` 500). The stop event is checked every `STEP_MS` 50 ms and
the system call wakes every `TICK_MS` 250 ms, so `stop()` ends both threads in well under 1 s.
A folder that cannot be watched, a project folder that goes away, a watch that ends without
being asked, or a crash is reported as a `ProjectError` through `on_error`, and the whole
watcher then stops: `intact` turns False, so the next follow of the same plan (Refresh) starts
a new one instead of keeping half a watcher. Outside folders may come and go (a drive): a
missing one is not an error, as status already reports the file missing; the outside thread
checks which are present every tick, reports a folder going away or coming back as a change,
and watches the present ones again. Inside/outside is decided on the path text, so a supplied
file reached through a link inside the project is watched as inside (its real folder is not).
Accepted trade-offs: a failure while watching an outside folder (for example a network share
without change notices) stops project-folder watching too, so the notice shows and Refresh
retries the whole watcher; the presence check (`is_dir()` per outside folder each tick) runs
on the outside thread, so a hanging network path can delay that thread's stop past
`STOP_GRACE_S` (a no-wait close then asks the user to close again; threads are daemons).
Measured on Windows 11 with watchfiles 1.3.0: watching does not lock the folder (rename/delete
still work), deleting the watched project folder ends the loop without an exception (now
reported as "the folder is gone"), deleting a watched outside folder silently stops its
reports (hence the presence check), and an edit reaches the dashboard in about 0.6–0.8 s.

`gui/watcher_bridge.py` `WatcherBridge` re-emits on the UI thread (`changed(root)`,
`failed(error)`) and drops news from a replaced or stopped watcher by generation number.
Following the same plan keeps the running watcher while it is `intact`; a changed plan (a
saved `.blend` or supplied file elsewhere) or a failed watcher starts a new one.
`shutdown(timeout)` waits at least
`STOP_GRACE_S` (0.6 s), because the threads end that quickly; the window's no-wait close tests
rely on it. `AppServices` follows the plan on open/adopt, stops on close and asks for statuses on
a change to the current root unless a build runs (its own refresh follows). The dashboard
(`views/dashboard_watch.py`) shows that check as running and keeps a separate notice when
watching stopped; Refresh statuses re-follows, which retries. `Dashboard.recheck()` drops a
status check on its way and checks again (a published assignment uses it, so a check started
by the assignment's own file copy cannot leave the dashboard waiting). The banner with
Keep/Lock/Discard actions is P5-T06c.

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
P2-T06b: `core/tools/rszst_setup.py` (pin, managed folder, `setup.json`, Linux steps and
preflight; no I/O beyond reads) and `core/tools/rszst_install.py` (download / build through
`process.run`) back `ctstudio setup rszst` (`cli/setup.py`). Discovery adds the `managed`
source; doctor adds `route`.
P2-T06: `core/tools/doctor.py` builds the tool report (no subprocess of its own; versions via
`versions.py`), `cli/doctor.py` renders it as a table or JSON, and `__main__` dispatches the
`doctor` subcommand without importing Qt. Exit 1 only when a required tool (`wszst`) is not
ready; optional tools only add fix hints.
P3-T07: `cli/__init__.py` `COMMANDS` maps each subcommand to its module (`add_parser`, `run`);
`__main__` dispatches every subcommand through it without importing Qt. `cli/new.py` wraps
`Project.create`; `cli/status.py` loads the manifest without the lock and renders
`components.status.evaluate` (table or JSON, schema in `docs/dev/CLI.md`); `cli/open_file.py`
picks an editor by file type and calls `editors.open_in`. `core/tools/availability.py` gives
the ids of the tools that are there to use (discovery only, nothing started).

P1-T04 foundation: `core/logging.py` configures the package logger once at startup via
`configure_logging()` (`platformdirs.user_log_dir("ctstudio")/ctstudio.log`, UTF-8 JSON lines,
5 MB/3 backups by default); `get_logger(__name__)` names its children. CLI startup may also
request a human-readable stderr handler. Reconfiguration closes only CT Studio-owned handlers.
JSON fields: UTC `timestamp`, `level`, `logger`, `message`, optional `exception`; multiline
messages are JSON-escaped to one line. The per-build logs under `.ctstudio/logs/` are plain
text written by the build itself (`core/build/build_log.py`, §7), not by this logger.
`core/errors.py` keeps `user_message` and an actionable `hint` separate from `details` (argv,
stderr tail, paths): `str(error)` shows the first two, never raw diagnostics. Typed subclasses
carry tool argv/exit/log path, manifest key, or build node ID as appropriate.

## 15. Performance budgets (checked by benchmarks / tests)
| Metric | Budget |
|---|---|
| Packaged cold start → dashboard interactive | < 2.0 s |
| Open project + status evaluation (typical) | < 300 ms |
| No-change rebuild | < 1 s (P4-T08: 41–48 ms; as a process ~0.5 s) |
| UI thread stall (dev watchdog) | never > 100 ms |
| KCL parse, 500k triangles | < 0.5 s |
| Preview: 200k tris load / frame | < 1 s / ≥ 60 fps on integrated GPU |
| Idle memory with project open | < 250 MB |
| Test build excl. Blender export, typical track | < 10 s (P4-T08: a real track's parts 1.1 s) |
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

P1-T05 filesystem policy: `core.fsutil.ensure_inside(root, path)` resolves symlinks and checks
containment for *existing or prospective* project paths; callers must separately guard any
symlink swap between validation and use. `atomic_write_bytes/text` stages and fsyncs a temporary
file in the destination directory before `os.replace`, and is **only for app-managed files**.
User-editable files must use `replace_with_backup(path, data)`: an existing regular file is copied
to a uniquely named adjacent `.bak` before atomic replacement; a new file returns no backup.
A process-local lock serializes replacements (Windows rename/open-handle behavior), not external
processes. The target is preserved on failed staging, backup or replacement; if replacement fails
a completed backup may remain. Both write helpers take materialized bytes (not stream inputs).
`hash_file` streams BLAKE2b in 1 MiB chunks. `Fingerprint.from_path` captures size and nanosecond
mtime; its `digest` hashes lazily and uses a 256-entry in-memory LRU keyed by resolved path, size
and mtime. An unchanged size+mtime after an external edit can yield a stale cache hit; no cryptographic
claim is made for the fast path. These operations belong off the GUI thread.
`core.platform` detects the running process's OS/sandbox and exposes platformdirs config/data/cache/log
paths. Blender's own sandbox must be diagnosed in its process, not inferred from the app's process.
