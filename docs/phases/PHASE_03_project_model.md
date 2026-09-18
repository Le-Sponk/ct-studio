# Phase 3 — Project model & component status

**Goal:** projects can be created, opened, and every component reports an accurate status fast.
**Exit:** `ctstudio new` + `ctstudio status [--json]` work on fixture projects; status of a
typical project evaluates in < 300 ms (benchmark).

### [ ] P3-T01 — Manifest model & TOML I/O
Dataclasses mirroring ARCHITECTURE §6 (frozen; `replace()` to edit). `load(path) -> Manifest` with
validation errors that name the key path and expected values; `save(manifest, path)` atomic.
Unknown keys preserved round-trip (keep the raw table and merge on save) with a logged warning.
`schema_version` + `migrations.py` (list of `(from_version, fn)`), even if only v1 exists.
**Acceptance:** round-trip tests (including unknown keys and comments loss documented — tomli-w does
not keep comments; say so in user docs), invalid-value tests, migration framework test with a dummy v0.

### [ ] P3-T02 — Project layout, create/open, lock
`Project.create(dir, name, blend=None, slot="beginner_course")` creates folders from ARCHITECTURE §5,
default manifest, `.gitignore` (`.ctstudio/`, `build/`). `Project.open(dir)`. Lock file `.ctstudio/lock` with pid
+ hostname; stale-lock detection; read-only open when locked.
**Acceptance:** tests for create/open/lock/stale lock; refuses to create inside a non-empty folder
unless `--force`.

### [ ] P3-T03 — Component registry
One declarative definition per component: id, display name, one-sentence plain-language description,
wiki link (mkwiiki.org), modes, stage outputs, required (bool), which tools each mode needs.
**Acceptance:** registry test (ids unique, outputs don't collide); descriptions reviewed for clarity.

### [ ] P3-T04 — Status evaluation
`core/components/status.py`: `evaluate(project, tools) -> dict[component_id, ComponentStatus]` with
reasons (`["course_model.brres missing", "Blender export older than .blend"]`).
Uses `.ctstudio/state.json` (last generated output hash + input fingerprints) and the stat fast path.
`EditedExternally` when a generated file's hash differs from state. `Manual` when mode is manual and
file exists & has the right magic bytes.
**Acceptance:** table-driven tests covering every status for every component; benchmark with 20
components' worth of files ≤ 300 ms cold, ≤ 30 ms warm.

### [ ] P3-T05 — File-type sniffing
`core/formats/magic.py`: identify Yaz0, U8, BRRES, KMP, KCL (heuristic: header offsets sanity), PNG,
DAE (XML root), OBJ (text heuristic), .blend (`BLENDER` header). Used by manual-file assignment and
status.
**Acceptance:** tests with synthetic headers; fixtures from tools where available (integration).

### [ ] P3-T06 — Slot catalogue
`core/project/slots.json` generated from recorded `wszst tracks` output (script in `scripts/`), not
typed by hand: internal file name, display name, cup, race/arena. Loader + lookup helpers.
**Acceptance:** 32 race tracks + 10 arenas; test asserts counts and that `beginner_course` exists.

### [ ] P3-T07 — CLI: `new`, `status`, `open`
`ctstudio new <dir> --name --blend --slot`, `ctstudio status [dir] [--json]` (table with status
icons + reasons), `ctstudio open <file> [--with tool]` (uses editors adapter).
**Acceptance:** CLI tests via `subprocess` against fakes; JSON schema documented in `docs/dev/CLI.md`.

### [ ] P3-GATE — Phase review
