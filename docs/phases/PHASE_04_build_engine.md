# Phase 4 — Build engine & SZS assembly

**Goal:** `ctstudio build` turns a project whose components are in manual mode into a valid SZS,
incrementally. This is milestone M1's engine.
**Exit:** integration test builds the fixture in manual mode, `wszst check` result stored, second
build skips every node in < 1 s.

### [ ] P4-T01 — Node & graph
`core/build/node.py`: `Node(id, inputs: tuple[Input, ...], outputs: tuple[Path, ...],
params: Mapping, tools: tuple[str, ...], resources: frozenset[str], impl_version: int,
run: Callable[[BuildContext], NodeResult])`. `graph.py`: build from manifest + component registry,
topological order, cycle detection with readable error, `subgraph(targets)` for "rebuild just this".
**Acceptance:** unit tests for ordering, cycles, subgraph selection.

### [ ] P4-T02 — Cache
`core/build/cache.py`: key = blake2b(canonical JSON params + sorted input fingerprints + tool
versions + impl_version). Stored in `.ctstudio/cache.json` (atomic write). Hit requires identical key and
outputs whose hashes match the recorded ones. `invalidate(node_id)`, `--force`.
**Acceptance:** tests: param change → miss; touch without content change → hit (fast path re-hash
once); tool version change → miss; output deleted → miss.

### [ ] P4-T03 — Runner & events
`core/build/runner.py`: executes ready nodes with bounded parallelism respecting `resources`
(e.g. `blender`, `stage:<file>`), cancellation token, stop-on-first-error (others finish or are
cancelled cleanly), events via callback (`BuildStarted`, `NodeStarted`, `LogLine`, `NodeSkipped`,
`NodeFinished`, `NodeFailed`, `BuildFinished(summary)`). Per-build log `.ctstudio/logs/build-<ts>.log`,
keep last 20. Updates `.ctstudio/state.json` for generated outputs.
**Acceptance:** tests with synthetic nodes: parallel speed-up, resource exclusion, cancel, failure
propagation, event order; no thread leaks (thread count before == after).

### [ ] P4-T04 — Manual-mode stage nodes
For each component in manual mode: validate file type (P3-T05), copy (or hard-link when same volume
and user enabled it) into `.ctstudio/stage/` under its canonical name; folders (posteffect) copied
recursively. Skipped when unchanged.
**Acceptance:** tests incl. wrong file type → clear Issue + failure.

### [ ] P4-T05 — Assemble node
Stage → `wszst create` via adapter using the profile's compression, `--auto-add` when enabled and
the library is configured, output to `build/<slot>.szs`; `_d` variant copy when enabled.
Post-check with `wszst list` that expected files are inside.
**Acceptance:** integration test on fixture; fake-tools unit test of argument construction per profile.

### [ ] P4-T06 — Validate node
`wszst check` → Issues (parser from S1 findings) → `.ctstudio/issues.json`. Warnings never fail test builds;
`--strict`/release profile fails on errors.
**Acceptance:** parser tests on recorded outputs (clean, warnings, errors); integration test.

### [ ] P4-T07 — `ctstudio build`
`ctstudio build [dir] [--release] [--force] [--only component] [--json-events]`; human-friendly
progress output; exit codes documented (0 ok, 1 build failed, 2 invalid usage, 3 cancelled).
**Acceptance:** CLI integration test; `--json-events` output validates against documented schema.

### [ ] P4-T08 — Benchmarks baseline
`tests/benchmarks/`: status evaluation, no-op rebuild, stage copy of 100 MB, cache key computation
for 1,000 inputs. Write numbers to `docs/dev/BENCHMARKS.md` (machine description included).
**Acceptance:** benchmarks run via `pytest -m benchmark`; budgets from ARCHITECTURE §15 asserted
where applicable (no-op rebuild < 1 s).

### [ ] P4-GATE — Phase review
