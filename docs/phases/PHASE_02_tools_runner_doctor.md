# Phase 2 — Tools: registry, discovery, process runner, doctor

**Goal:** the app can find, version, and safely run every external tool on Windows and Linux.
**Exit:** `ctstudio doctor` shows a correct table using real tools in `.tools/`; integration CI
runs on both OSes.

### [x] P2-T01 — ToolSpec & registry (commit 157fc62)
`core/tools/spec.py`: `ToolSpec(id, name, kind: cli|gui, exe_names per OS, version_args,
version_regex, min_version, homepage, download_page, licence, used_for)`. Registry entries: wszst,
wkclt, wkmpt, wimgt, rszst, abmatt, blender, brawlcrate, riistudio, kmp_editor_lorenzi, kmp_cloud,
dolphin, dolphin_tool, wine, winetricks. User-defined custom tools: `name, exe, args_template`
(placeholders `{file}`, `{dir}`, `{project}`).
**Acceptance:** registry is data-driven (one table); unit tests validate entries (unique ids,
regex compiles, URLs well-formed). Verified by 10 focused tests, Windows `check.py` (140
passed / 1 optional skip) and [Ubuntu + Windows CI](https://github.com/Le-Sponk/ct-studio/actions/runs/36356549228).
Version probes are only the seven documented commands; unknown compatibility floors stay
`None` pending P2-T02b, not silently assumed to support every version.

### [x] P2-T02a — Location discovery (no process spawning) (commits 51ef73f, a1bda6b, d6513dc)
`core/tools/discovery.py`: order = user setting → PATH → standard locations per OS (Wiimms:
`%ProgramFiles%\Wiimm\SZS`, `/usr/local/bin`, `/usr/bin`, `~/bin`; Blender: Program Files/Blender
Foundation/*, `/usr/bin`, `/opt/blender*`, `~/Applications`, Flatpak `org.blender.Blender` via
`flatpak run`; Steam not supported) → `.tools/` (dev only, behind a flag).
Return a `ToolLocation(path, version=None, source, launcher: direct|wine|flatpak)`; Flatpak uses
its application ID as its target rather than pretending it is a filesystem path. Discovery checks
visible executable files only, not host locations hidden by a Flatpak/Snap sandbox. Desktop-launched
apps may not inherit the shell PATH, so scan standard locations even when PATH is empty.
**Acceptance:** fake directory trees/executables on both OS branches, PATH precedence, explicit
selection, sandbox visibility, Wine/Flatpak launch metadata, and dev-only opt-in tests.
Verified by 27 focused tests (26 run on Windows; the POSIX execute-bit test runs on Linux),
Windows `check.py --all` (167 passed / 2 skipped) and
[Ubuntu + Windows CI](https://github.com/Le-Sponk/ct-studio/actions/runs/36370497638).
Discovery only inspects files; no Flatpak, Wine or tool process was executed.

### [x] P2-T03 — Process runner (prerequisite to P2-T02b) (commit c138e66)
`core/tools/process.py`: `run(cmd: Sequence[str|Path], *, cwd, env=None, timeout=None,
on_line=None, cancel: CancelToken|None) -> RunResult(exit_code, duration, stdout_tail, stderr_tail,
log_path)`; `launch_detached(cmd, cwd)` for GUI editors. Reader threads for stdout/stderr, bounded
tail buffers, full output appended to a log file, UTF-8 with replacement. Kill process tree on
cancel/timeout (POSIX `start_new_session` + `killpg`; Windows `CREATE_NEW_PROCESS_GROUP` + tree
termination). `CREATE_NO_WINDOW` for CLI tools on Windows. Environment: inherit, then apply
explicit additions; never `shell=True`.
**Acceptance:** tests with fake tools: streaming order, 50 MB output without deadlock, timeout kill,
cancel mid-run, non-zero exit → `ToolFailed` with tail, unicode paths/args. Test timeouts ≤ 10 s.
Verified by 17 tests (16 on Linux; one Windows console-window test) using interpreter fakes,
grandchild heartbeats and a src/ spawning scan; Windows `check.py --all` 183 passed / 2 skipped;
[Ubuntu + Windows CI](https://github.com/Le-Sponk/ct-studio/actions/runs/40448766227).
13 Windows source mutations, 12 caught (survivor: explicit job termination is redundant with
kill-on-close). Tree mechanism: ADR-024.

### [x] P2-T02b — Version probing and cache (after P2-T03) (commits 6969b1f, 40fbb96)
Use only documented `version_args`/`version_regex` through `core/tools/process.py` with short
timeouts; run independent probes concurrently. Persist results in user settings keyed by executable
path and mtime (Flatpak: application identity); invalidate on change and support forced re-check.
Unknown/GUI version probes remain `None`, never launch GUIs for versions. Extend `ToolLocation` with
its verified version.
**Acceptance:** fake process tools exercise concurrent probes, timeouts, unset probes, persistent
cache reuse and invalidation for changed mtime on Windows/Linux; no import of `subprocess` outside
`core/tools/process.py` in src/. This split and interleave are explained in ADR-023.
Verified by 14 tests (`test_tool_versions.py`, `test_tool_version_cache.py`) using real fake
executables (Windows: copied launcher; Linux: shebang script) and recorded `rszst` output;
Windows `check.py --all` 198 passed / 2 skipped; Ubuntu/Windows CI run 40519561490. No real
tool's version was probed yet (deferred to the P2-T06 doctor checkpoint).

### [x] P2-T04a — Help recordings and flag contract checker (commit 9d891bf)
Record each pinned CLI's real help through `core/tools/process.py` with
`scripts/record_tool_help.py`: Wiimm's `version` + `help <command>` per used command, rszst's
existing recording, ABMatt `--help`, Blender `--version`/`--help`. Write JSON (argv, exit code,
stdout, stderr; LF newlines, no user paths) to `tests/fakes/recordings/<tool>/<version>/`.
`tests/fakes/help_contract.py` parses each help family (Wiimm option tables, clap, ABMatt's
pipe table, Blender) into the set of flags each command accepts.
**Acceptance:** every flag in the verified argv templates in TOOLS.md exists in the pinned
recording; replacing a flag with a non-existent one, or using one under the wrong command, fails a
test; recording folders match `scripts/tool_catalogue.py` pins; the recorder refuses an unpinned
version.
Verified by 17 tests (`test_help_contract.py`, `test_record_tool_help.py`): 27 TOOLS.md table
templates + 6 prose-verified invocations pass; 7/7 checker mutations caught. Windows
`check.py --all` 215 passed / 2 skipped; Ubuntu/Windows CI run 40527275382. Recordings are
Windows-only (Linux help output for Wiimm/ABMatt/Blender not yet recorded; rszst has both).

### [x] P2-T04b — Wiimm fakes, operation recordings and `fake_tools_path` (commit dd99b04)
`scripts/record_tool_outputs.py` records real Wiimm operations on the generated fixtures
(create/list/check/analyze/minimap, wkmpt encode/decode, wkclt decode, wimgt encode, plus
error cases: missing input, existing destination, missing destination folder, unknown flag)
into `tests/fakes/recordings/<tool>/<version>/<os>-ops.json`. `tests/fakes/` gains a shared
fake runtime (argv log, flag check through P2-T04a's contract, the tools' own error
formats), fake `wszst`/`wkclt`/`wkmpt`/`wimgt`, and real per-platform executables for them
(Windows: the console-script launcher pip uses; Linux: a sh/Python polyglot that survives
spaces in the repo path). Pytest fixture `fake_tools_path` puts them first on PATH.
**Acceptance:** fakes run through `core/tools/process.py` and discovery finds them; their
output equals the recorded real output for every deterministic recorded case (messages, exit
codes, file left unchanged or created); an unknown or foreign flag is rejected the way the real
tool rejects it; an unmodelled-but-recorded command fails loudly instead of pretending.
Verified by `test_fake_wiimm.py`: 57 real Wiimm 2.42a operation runs (Windows 11) replayed
against the fakes through the core runner, plus 22 help/version runs byte-for-byte; unknown
(110) and foreign (108) options as the real getopt; 7 unmodelled argv shapes exit 121 with
nothing written; discovery and version probes find the fakes on PATH. 18/18 mutations of the
fakes caught. CI run 40595338853 green on Ubuntu (sh/Python launchers) and Windows (`.exe`).
Not verified: Linux recordings of the real tools (the fakes fall back to the Windows ones).

### [x] P2-T04c — rszst fake and operation recordings
`scripts/fixtures/make_fixtures.py` also exports `course.dae` (the add-on's built-in COLLADA
writer, textures beside it), so rszst has a real fixture input. `scripts/record_tool_outputs.py`
grows a per-tool case table and records real `rszst` 5.11.5 runs: `import-brres` (default and
explicit destination, `--model-name`, `--mipmaps --min-mip`, `--preset-path` present/missing,
missing input, junk input, missing destination folder), `brres-to-json`, `json-to-brres`,
`dump-presets` (new/existing folder, destination is a file) and clap errors (unknown, misspelt
and value-less options, unknown subcommand). Measured on Windows: every failure *and* `--help`
/ `--version` exit -1; an existing destination is replaced silently, but a fresh one gets
"will be overwritten"; a missing destination folder exits 0 and writes nothing; the mesh
progress bars count distinct instanced geometries.
**Acceptance:** as P2-T04b for `rszst`: replay equals the recordings through the core runner;
clap errors as recorded; non-ASCII absolute paths fail like the real Windows build
(`FileNotExist`) and are unmodelled on Linux; anything unrecorded exits 121.

### [x] P2-T04d — ABMatt fake and operation recordings (commit 78f66cc)
Same for `abmatt` 1.3.2: `convert` DAE/OBJ → BRRES (with/without `-o`, existing destination),
`-b FILE -f CMDS -o`, `-b FILE -c info`; getopt errors (exit 2). Measured on Windows: it needs
`wimgt` on PATH (else an `ERROR: wimgt not found` line and no textures); "already exists" and a
missing command file exit **0**; a missing `convert` input exits 1, a missing `-b` file and a
command parse error exit -1 with a frozen-Python traceback; `-c 'X for *'` appends its own
` for *` and fails.
**Acceptance:** as P2-T04b for `abmatt`.

### [ ] P2-T04e — Blender fake
`blender -b [FILE] --factory-startup [--python-exit-code N] --python SCRIPT -- ARGS`: the fake
runs SCRIPT with the test interpreter (no `bpy`, so a script that needs it fails as an honest
`ModuleNotFoundError`) and frames it like Blender 5.2.2: the version banner, `Blender quit`,
exit 0 on a script exception unless `--python-exit-code`, `sys.exit(n)` → n with no quit line,
an unknown argument loaded as a file (exit 1), a missing/unsupported `.blend` exit 1.
**Acceptance:** as P2-T04b for `blender`; `fake_tools_path` provides all seven tools.

### [ ] P2-T05 — Adapters
Thin typed facades; flags only from TOOLS.md:
**From S1 (P0-T04), non-negotiable for `wiimm.py`:** `wszst check` exits 2 for valid *and*
broken tracks but 0 for a corrupt file, so `check()` must parse output and raise on
`ERROR #`, never branch on the exit code. Add `analyze(szs) -> dict` (`analyze --json`)
and prefer it for status; it supersedes `slots()`.
- `wiimm.py`: `create_szs(stage, dest, compression, auto_add, extra)`, `check(szs|dir) -> list[Issue]`,
  `analyze(szs) -> dict`, `minimap_auto(file)`, `kcl_analyze(kcl)`, `kcl_flags(kcl)`, `kmp_to_text/ from_text`,
  `img_encode(png, dest, format, mipmaps)`, `autoadd_status()`, and
  `autoadd_create(race_course_dir, dest)`. The auto-add parser follows the human recording in
  TOOLS.md: status returns the current path plus indexed search paths, while create success is exit
  0 plus one `ANALYZE YAZ0.U8:<path>` line per processed archive (there is no summary). Add fake-tool
  outputs with synthetic paths for both forms. `auto_add=True` must fail loudly unless a separate
  content check says the library is usable: status exit 0, directory existence, and search-path
  count do **not** establish that (wszst otherwise ignores the flag silently).
- `abmatt.py`, `rszst.py`: only the operations S3/S4/S5 proved useful.
  **From P0-T13 (native Windows):** `rszst` cannot open a non-ASCII absolute path (it reads
  argv through the ANSI code page and reports `FileNotExist`); run it with `cwd` = the file's
  directory and bare file names — always, so there is one code path. Failure exit status is
  -1 as the OS reports it (255 Linux, 0xFFFFFFFF Windows): test "non-zero", never a literal.
  ABMatt can crash *after* writing its output (CJK path → `UnicodeEncodeError`, exit 0), so
  success = the output file exists and parses, not a clean log.
- `blender.py`: `run_script(blend, script, args, timeout)`.
- `editors.py`: `open_in(tool_id, file)` using the S7 launch contracts (TOOLS.md); `wine.py`: prefix
  handling, `winepath`. S7 pinned the shape: **one path per launch, one process per launch**, never
  two documents (BrawlCrate's second argument is a node path *inside* the first file, Blender's
  replaces the first). Options go **after** the path — Lorenzi's editor opens `argv[1]` whatever it
  is. `wine.py` must select the prefix by executable architecture (PE32 → win32, PE32+ → win64;
  `Bad EXE format` otherwise) and convert with `winepath -w`. `open_in` returns "launched", never
  "opened": RiiStudio stays up with an empty window after a failed load, and two of the five editors
  never name the file in their window title, so neither liveness nor titles can be checked.
  Natively on Windows (P0-T13) none of the four editors registers a file association, so launch
  by argv, never `ShellExecute` on the document. RiiStudio silently opens nothing for a
  non-ASCII path: `open_in` must warn before launching it on one.
Parsers produce dataclasses/Issues; parsing code has unit tests against recordings.
**Acceptance:** unit tests with recordings; `-m integration` tests run each adapter against real tools
on the fixture.

### [ ] P2-T06 — `ctstudio doctor`
Table: tool, status (found/missing/too old/sandboxed), version, path, launcher, used for, fix hint.
`--json` for machines. Exit 0 even if optional tools are missing; non-zero only if required-for-core
tools (wszst) missing.
**Acceptance:** integration test in container; snapshot test of text layout with fakes.

### [ ] P2-T06b — How Linux users get `rszst` (first-run setup)
**Why this needs a task:** ADR-004 makes `rszst` the BRRES import backend, but RiiStudio publishes
**Windows and macOS assets only** — there is no Linux release and no package. S3a built it from
source in ~55 min (the recipe is in [SPIKES.md §S3](../dev/SPIKES.md)), which is not something a
beginner will do, and the project-wide licence is unconfirmed so CT Studio **must not redistribute
a build** (ADR-004, HC0 non-blocking answer).
Design the first-run path around that. Each option must appear in `doctor` and the Tools page with
an honest description of its cost:
1. **Detect an existing `rszst`** (PATH, standard locations, user setting) — the happy path, and
   the only one that is instant.
2. **Windows/macOS: guided download** from the official releases page, user-initiated, never
   bundled (already decided for the GUI; the CLI ships in the same archive).
3. **Linux: offer to build from source** with the pinned S3a recipe, run as a visible, cancellable
   background job with a realistic time estimate and a disk-space check, not a silent spinner.
   Record the exact pin so the build is reproducible.
4. **Linux fallback: Wine + the Windows `rszst.exe`.** Cheaper than a source build and the prefix
   machinery already exists for the editors — but **unverified**: S7 ran RiiStudio's *GUI* under
   Wine, never the CLI. Must be measured before it is offered (see P0-T13).
5. **Degrade honestly:** with no `rszst`, BRRES import is unavailable. Say which features are
   affected, do not fail deep in a build with a confusing error.
**Acceptance:** tests with fakes for each branch; the Linux build path has an integration test that
is `slow` + `realdata`-style opt-in (it takes ~1 h); `doctor --json` reports which route was used.

### [ ] P2-T07 — Tools page (GUI)
Settings → Tools: list with status chips, Browse…, Re-check (runs off the UI thread with a spinner),
"Open download page". Changes persist to user settings.
**Acceptance:** pytest-qt test with fakes: set path → re-check → status updates; screenshot artifact.

### [ ] P2-T08 — Integration CI
`integration.yml` (nightly + manual): Linux + Windows; downloads Wiimms tools + Blender (cached by
version key) using `scripts/bootstrap_tools.py`; runs `-m integration`. Windows also evaluates the
rszst prebuilt if S3 required it.
**From S3a:** Linux Alpha 5.11.5 builds, but Windows behaviour is unverified. Pin the
Windows release ZIP checksum, retain bundled DLLs, record help/version/invalid-argument
exit codes independently (Linux returns 255 for all three) and run S3b's synthetic
course/skybox tests. See [SPIKES.md S3](../dev/SPIKES.md#s3-brres-backend-bake-off-p0-t06a--p0-t06b).
**Acceptance:** green on both OSes (or blocked item if repo not on GitHub yet).

### [ ] P2-GATE — Phase review
