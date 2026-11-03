# Phase 4 — Build engine & SZS assembly

**Goal:** `ctstudio build` turns a project whose components are in manual mode into a valid SZS,
incrementally. This is milestone M1's engine.
**Exit:** integration test builds the fixture in manual mode, `wszst check` result stored, second
build skips every node in < 1 s.

### [x] P4-T01 — Node & graph
`core/build/node.py`: `Node(id, inputs: tuple[Input, ...], outputs: tuple[Path, ...],
params: Mapping, tools: tuple[str, ...], resources: frozenset[str], impl_version: int,
run: Callable[[BuildContext], NodeResult])`. `graph.py`: build from manifest + component registry,
topological order, cycle detection with readable error, `subgraph(targets)` for "rebuild just this".
**Acceptance:** unit tests for ordering, cycles, subgraph selection.
**Deviation (P4-T01):** an input is a plain path (a folder means every file in it), not an
`Input` class; edges come from matching outputs to inputs, and `from_manifest` takes a
`make_part(spec, mode)` factory so each later task adds its own steps.

### [x] P4-T02 — Cache
`core/build/cache.py`: key = blake2b(canonical JSON params + sorted input fingerprints + tool
versions + impl_version). Stored in `.ctstudio/cache.json` (atomic write). Hit requires identical key and
outputs whose hashes match the recorded ones. `invalidate(node_id)`, `--force`.
**Acceptance:** tests: param change → miss; touch without content change → hit (fast path re-hash
once); tool version change → miss; output deleted → miss.
**Note (P4-T02):** output paths are not in the key; a different set of output files is a
miss through the recorded outputs instead. `--force` is `clear()` / `invalidate()`, wired to
the CLI in P4-T07.

### [x] P4-T03 — Runner & events
`core/build/runner.py`: executes ready nodes with bounded parallelism respecting `resources`
(e.g. `blender`, `stage:<file>`), cancellation token, stop-on-first-error (others finish or are
cancelled cleanly), events via callback (`BuildStarted`, `NodeStarted`, `LogLine`, `NodeSkipped`,
`NodeFinished`, `NodeFailed`, `BuildFinished(summary)`). Per-build log `.ctstudio/logs/build-<ts>.log`,
keep last 20. Updates `.ctstudio/state.json` for generated outputs.
**Acceptance:** tests with synthetic nodes: parallel speed-up, resource exclusion, cancel, failure
propagation, event order; no thread leaks (thread count before == after).
**Split (2026-11-03):**
- [x] **P4-T03a — Runner & events:** `runner.py` + `events.py` (scheduling, resources, cache
  skip, cancel, stop-on-first-error, events). Acceptance: the tests above. Cancel uses the
  existing `tools.process.CancelToken` (no `cancel.py`), so one token stops tools too.
- [x] **P4-T03b — Build log & state:** `.ctstudio/logs/build-<ts>.log` (keep last 20) and the
  `state.json` update for generated outputs (needs each step to say which part it makes).
  Acceptance: log written and pruned; status reads Ready after a build, Stale after an edit.
  Done 2026-11-03: `Node.component`; `build/part_state.py` records the part with the user's
  files behind it (the `.blend`, not the export) and `build/build_log.py` writes one UTC line
  per event; an unwritable log never fails the build. Mutants 31/31.

### [x] P4-T04 — Manual-mode stage nodes (commit 4fcf8cc)
For each component in manual mode: validate file type (P3-T05), copy (or hard-link when same volume
and user enabled it) into `.ctstudio/stage/` under its canonical name; folders (posteffect) copied
recursively. Skipped when unchanged.
**Acceptance:** tests incl. wrong file type → clear Issue + failure.
Done 2026-11-03: `core/build/stage.py` (`manual_parts`, `stage_part`); the type check is
shared with the dashboard; every fixable problem is one `Issue` via `StepFailed`. Hard links
deferred (see STATUS Plan changes). Mutants 25/25.

### [x] P4-T05 — Assemble node
Split 2026-11-03 (see STATUS Plan changes):
- [x] **P4-T05a — Assemble without auto-add** (commit 267b996)**:** `wszst create` of `.ctstudio/stage/` with the
  profile's compression into `build/<slot>.szs` (temporary file, then replaced), the `_d` copy
  when enabled, and a `wszst list` post-check that every staged file is inside. Acceptance:
  fake-tool unit tests for the arguments per profile and the post-check; an integration test
  with the real wszst on synthetic files. Done 2026-11-03: `core/build/assemble.py`,
  `wiimm.list_files`/`parse_list` (format measured, TOOLS.md); mutants 26/26.
- [x] **P4-T05b — Auto-add and missing objects** (commit ad91b49)**:** the library setting and its usability check,
  `--auto-add` only then, and the warning naming every KMP object missing from both the stage
  and the library (needs the KMP object → file table); the `realdata` test. Done 2026-11-03:
  the table is Wiimm's own (`wkmpt cat` + `wkmpt objects`, `core/tools/wiimm_objects.py`),
  not one kept by CT Studio; `core/build/objects.py`; user setting `auto_add_library`;
  realdata test passed locally with the user's own library; mutants 33/33.

Stage → `wszst create` via adapter using the profile's compression. Auto-add is optional: fixtures
and the default manual-mode path do not require it; pass `--auto-add` only when the user enabled it
and the library passed the adapter's usability check. If the staged KMP references objects that are
absent from both the stage and the configured library, emit a clear warning naming every missing
object; never silently accept wszst's no-op behavior when the library is unavailable. Output to
`build/<slot>.szs`; `_d` variant copy when enabled.
Post-check with `wszst list` that expected files are inside.
**Acceptance:** integration test on the synthetic fixture with no auto-add library; fake-tools unit
tests for argument construction per profile, unavailable/empty-library behavior, and named
missing-object warnings. Add a `realdata` test for a user-owned library and run it at HC1; it skips
when the local library/game fixtures are absent.

### [x] P4-T06 — Validate node
`wszst check` → Issues (parser from S1 findings) → `.ctstudio/issues.json`. Warnings never fail test builds;
`--strict`/release profile fails on errors.
**From S1 (P0-T04):** severities come from the line prefixes `+ WARNING:` / `- HINT:` /
`* INFO:`, with a `=> N warnings, M hints and K info for …` summary line. Missing
components appear as `+ WARNING: Missing file:    ./course_model.brres (or '_d' variant)`
but **only when a KMP is present**, so do not rely on `check` alone to detect a missing
component — use the empty `sha1_course`/`sha1_vrcorn`/`sha1_minimap` fields from
`wszst analyze --json`. Never treat `check`'s exit code as pass/fail (see TOOLS.md).
**Acceptance:** parser tests on recorded outputs (clean, warnings, errors); integration test.
Done 2026-11-03: `core/build/validate.py`; missing parts from `analyze`, the rest from
`check` (recorded real output); release = strict unless told otherwise; the cache now keeps
each step's issues, so a skipped step reports them again (closes the P4-T05b gap). Real-tool
integration test (missing parts → release fails; complete stand-ins → passes). Mutants 34/34.

### [x] P4-T07 — `ctstudio build`
`ctstudio build [dir] [--release] [--force] [--only component] [--json-events]`; human-friendly
progress output; exit codes documented (0 ok, 1 build failed, 2 invalid usage, 3 cancelled).
**Acceptance:** CLI integration test; `--json-events` output validates against documented schema.
Split 2026-11-03 (STATUS "Plan changes"):
- [x] **P4-T07a — Build a project (core)****:** `core/build/project_build.py`: the steps
  (manual parts, then assemble and validate; `only` = one part's steps), the tools they use
  found as doctor finds them (missing → stop before anything runs), versions for the cache,
  the auto-add library, `force`. **Acceptance:** plan tests with fake tools; a real-tool
  build of a synthetic manual project. Done 2026-11-03: `core/build/project_build.py`
  (`plan_build`, `build_project`); a tool that would run only through Wine is not used yet;
  real-tool build of an all-manual synthetic project, then a full skip; mutants 20/20.
- [x] **P4-T07b — The `ctstudio build` command****:** human output, `--json-events` (schema in
  `docs/dev/CLI.md`), Ctrl+C cancels, exit codes 0/1/2/3. **Acceptance:** CLI integration
  test; every `--json-events` line validates against the documented schema. Done
  2026-11-03: `cli/build.py`, `core/build/event_json.py`; the schema is a JSON Schema block in
  CLI.md that the tests read (a small checker, no new dependency); real-process tests with
  the real Wiimm tools (build, rebuild with `--json-events`, a wrong file, `--only`,
  `--release`); mutants 33/33.

### [x] P4-T08 — Benchmarks baseline
`tests/benchmarks/`: status evaluation, no-op rebuild, stage copy of 100 MB, cache key computation
for 1,000 inputs. Write numbers to `docs/dev/BENCHMARKS.md` (machine description included).
**Acceptance:** benchmarks run via `pytest -m benchmark`; budgets from ARCHITECTURE §15 asserted
where applicable (no-op rebuild < 1 s).
Done 2026-11-03: `tests/benchmarks/test_build_speed.py` (typical track first build < 10 s,
no-change rebuild < 1 s in-process and as a process, 100 MiB stage, 1,000-input cache key);
numbers in BENCHMARKS.md. Found and fixed: a warm 1,000-input check took 0.94 s (one
`resolve` per file now, 0.25 s); the track check rejected most real tracks' reports (summary
shapes, LE-CODE / SLOT / SUGGESTION lines; `tests/realdata/test_build_original_tracks.py`
checks every track of the user's own disc). Mutants 21/21.

### [x] P4-GATE — Phase review
