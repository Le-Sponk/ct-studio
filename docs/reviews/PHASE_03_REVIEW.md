# Phase 3 review — project model & component status

**Gate:** P3-GATE · 2026-11-03 · fresh-context reviewer delegated from
`docs/reviews/PHASE_03_BRIEF.md` and `docs/process/REVIEW_CHECKLIST.md`, reviewing HEAD a46b515.
The reviewer did not change the tracked tree (mutations ran in a scratch worktree, removed);
the implementer triaged and fixed the findings.

## Reviewer's checks (re-run independently)
- `scripts/check.py --all`: every step green, 1,670 passed / 6 skipped.
- Integration (`test_cli_status_real.py`, `test_magic_built.py`, real Wiimm tools): 4 passed.
- Benchmark: cold 72.0 ms, warm 9.6 ms for 20 parts (limits 300 / 30 ms): exit criterion met.
- CLI by hand in a non-ASCII folder: `new` with a track name, `status` table and `--json`
  (keys, part order, `/` paths, `ok`, exit 1 on `error`), misspelt slot (exit 2 with
  did-you-mean), second `new` refused, `open` on a `.toml` refused: all as documented.
- Mutation spot-check 7/7 caught: `state.compare` always same, STALE dropped from the blocker
  set, lock host not checked, BRRES size check removed, unknown TOML keys not recorded, CLI
  exit on MISSING instead of ERROR, manual `file` kept in the settings key.
- Copyright: no binary added since `phase-02-done`; the `wstrt` recording is text output of
  `version`, `tracks --long`, `arenas --long` only; `local_fixtures/` is git-ignored and the
  realdata test extracts into `tmp_path` only.

## Findings and disposition

### Must fix — resolved
1. `ctstudio status` (table and `--json`) crashed with `UnicodeEncodeError` when its output was
   redirected on Windows (ANSI code page) and the project name or path was not ASCII. Every CLI
   test set `PYTHONIOENCODING=utf-8`, which hid it. **Fix:** `__main__._cli` reconfigures
   stdout/stderr to UTF-8 (`errors="replace"`) for every subcommand; CLI.md says output is
   UTF-8. New subprocess test without `PYTHONIOENCODING`/`PYTHONUTF8`, table and JSON, in
   `Pistë 日本` (failed before the fix, passes after).

### Should fix — resolved
1. `Project.create` under a path whose parent is a file: raw `FileExistsError` traceback.
   **Fix:** `project._make_layout` turns `OSError` into `ProjectError("Could not make …",
   hint="Choose a folder you can write to.")`; test added.
2. A `state.json` that is not UTF-8 crashed `status`. **Fix:** read bytes, decode inside the
   damaged-file `try` (`UnicodeDecodeError` is a `ValueError`); test added.
3. `state.input_key` stored a relative input outside the project as relative, so it later
   resolved inside the project and read as "gone" forever. **Fix:** store the resolved
   absolute path; test added (relative path from another working folder).
4. A file changing (or vanishing) while it is hashed raised out of `evaluate` and failed the
   whole status. **Fix:** `FileRecord.compare` reads that as `changed`; test added.
5. ARCHITECTURE §3 source tree listed `project/layout.py` and missed the real modules.
   **Fix:** tree updated (project, components, tools).

### Consider — each logged or dismissed
1. `slots.CatalogueError` / `UnknownSlot` subclass `ValueError`, not `core/errors.py`.
   Dismissed for now: `UnknownSlot` is turned into an argparse error at the only caller
   (`cli/new.py`), and its message already carries the hint; `CatalogueError` means a broken
   install, a programming error. Revisit when P5-T02 (slot picker) calls `find`.
2. Public names used only by tests. Removed `slots.race_tracks/arenas` and `lock.read_owner`
   (no planned caller). Kept `slots.cups` (P5-T02 slot picker; docstring says so),
   `magic.identify_bytes` (the test seam for `_sniff` on in-memory data; `identify` reads a
   file) and `LockResult.took_over_from` (tested; the P5 dashboard reports takeovers). The
   registry fields stay (the phase file asks for them).
3. `objects` / `track_info` are special-cased by id in `status.py`. Dismissed: two fixed parts
   with no outputs; a registry flag would be a speculative layer for two entries.
4. Sleep-polling in `test_cli_project.py`'s editor test. Kept, with a comment: the detached
   fake editor gives no signal but the file it writes.
5. CLI.md did not mention the checkout `.tools/` folder and CT Studio's own tool folder.
   **Fixed.**
6. A whole `ctstudio status` process takes ~400 ms (imports ~210 ms). Not the phase limit
   (evaluation, ~70 ms). Measured in BENCHMARKS.md; logged as **TD-011 → P13-T02**.

## After the fixes
- `scripts/check.py --all`: green, 1,675 passed / 6 skipped.
- Must-fix verified by a separate short delegated review before the tag (see STATUS).
