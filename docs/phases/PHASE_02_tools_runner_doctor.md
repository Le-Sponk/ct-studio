# Phase 2 — Tools: registry, discovery, process runner, doctor

**Goal:** the app can find, version, and safely run every external tool on Windows and Linux.
**Exit:** `ctstudio doctor` shows a correct table using real tools in `.tools/`; integration CI
runs on both OSes.

### [ ] P2-T01 — ToolSpec & registry
`core/tools/spec.py`: `ToolSpec(id, name, kind: cli|gui, exe_names per OS, version_args,
version_regex, min_version, homepage, download_page, licence, used_for)`. Registry entries: wszst,
wkclt, wkmpt, wimgt, rszst, abmatt, blender, brawlcrate, riistudio, kmp_editor_lorenzi, kmp_cloud,
dolphin, dolphin_tool, wine, winetricks. User-defined custom tools: `name, exe, args_template`
(placeholders `{file}`, `{dir}`, `{project}`).
**Acceptance:** registry is data-driven (one table); unit tests validate entries (unique ids,
regex compiles, URLs well-formed).

### [ ] P2-T02 — Discovery
`core/tools/discovery.py`: order = user setting → PATH → standard locations per OS (Wiimms:
`%ProgramFiles%\Wiimm\SZS`, `/usr/local/bin`, `/usr/bin`, `~/bin`; Blender: Program Files/Blender
Foundation/*, `/usr/bin`, `/opt/blender*`, `~/Applications`, Flatpak `org.blender.Blender` via
`flatpak run`; Steam not supported) → `.tools/` (dev only, behind a flag).
Returns `ToolLocation(path, version, source, launcher: direct|wine|flatpak)`. Version detection runs
concurrently with a short timeout. Results cached in user settings keyed by `(path, mtime)`.
Port the add-on's lessons: desktop-launched apps don't inherit shell PATH; sandboxed apps can't see
host `/usr/local`.
**Acceptance:** tests with fake directory trees and fake executables for each OS branch (use
monkeypatched platform); cache invalidation test.

### [ ] P2-T03 — Process runner
`core/tools/process.py`: `run(cmd: Sequence[str|Path], *, cwd, env=None, timeout=None,
on_line=None, cancel: CancelToken|None) -> RunResult(exit_code, duration, stdout_tail, stderr_tail,
log_path)`; `launch_detached(cmd, cwd)` for GUI editors. Reader threads for stdout/stderr, bounded
tail buffers, full output appended to a log file, UTF-8 with replacement. Kill process tree on
cancel/timeout (POSIX `start_new_session` + `killpg`; Windows `CREATE_NEW_PROCESS_GROUP` + tree
termination). `CREATE_NO_WINDOW` for CLI tools on Windows. Environment: inherit, then apply
explicit additions; never `shell=True`.
**Acceptance:** tests with fake tools: streaming order, 50 MB output without deadlock, timeout kill,
cancel mid-run, non-zero exit → `ToolFailed` with tail, unicode paths/args. Test timeouts ≤ 10 s.

### [ ] P2-T04 — Fake tools & recordings
`tests/fakes/`: small Python scripts mimicking the CLI surface we use (wszst, wkclt, wkmpt, wimgt,
rszst, abmatt, blender) — they log received args to JSON and create plausible output files.
`tests/fakes/recordings/<tool>/<version>/`: real `--help`/version/check outputs captured from `.tools/`.
Fixture `fake_tools_path` prepends fakes to PATH. Contract test: every flag an adapter emits exists
in the recorded help text for the pinned version.
**Acceptance:** contract tests pass; changing an adapter flag to a non-existent one fails a test.

### [ ] P2-T05 — Adapters
Thin typed facades; flags only from TOOLS.md:
**From S1 (P0-T04), non-negotiable for `wiimm.py`:** `wszst check` exits 2 for valid *and*
broken tracks but 0 for a corrupt file, so `check()` must parse output and raise on
`ERROR #`, never branch on the exit code. Add `analyze(szs) -> dict` (`analyze --json`)
and prefer it for status; it supersedes `slots()`.
- `wiimm.py`: `create_szs(stage, dest, compression, auto_add, extra)`, `check(szs|dir) -> list[Issue]`,
  `analyze(szs) -> dict`, `minimap_auto(file)`, `kcl_analyze(kcl)`, `kcl_flags(kcl)`, `kmp_to_text/ from_text`,
  `img_encode(png, dest, format, mipmaps)`, `autoadd_create(race_course_dir, dest)`.
  `auto_add=True` must fail loudly when no auto-add library is configured: wszst ignores
  the flag silently.
- `abmatt.py`, `rszst.py`: only the operations S3/S4/S5 proved useful.
- `blender.py`: `run_script(blend, script, args, timeout)`.
- `editors.py`: `open_in(tool_id, file)` using launch contracts; `wine.py`: prefix handling, `winepath`.
Parsers produce dataclasses/Issues; parsing code has unit tests against recordings.
**Acceptance:** unit tests with recordings; `-m integration` tests run each adapter against real tools
on the fixture.

### [ ] P2-T06 — `ctstudio doctor`
Table: tool, status (found/missing/too old/sandboxed), version, path, launcher, used for, fix hint.
`--json` for machines. Exit 0 even if optional tools are missing; non-zero only if required-for-core
tools (wszst) missing.
**Acceptance:** integration test in container; snapshot test of text layout with fakes.

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
