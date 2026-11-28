# Deep Clean #1 — after Phase 5

REVIEW_CHECKLIST §4 at tag `phase-05-done` (`ab1047f`), Windows workstation (Ryzen 7 4800H,
Python 3.12.14). Raw outputs were collected by one script into the agent's scratch folder;
the figures below are copied from them.

## 1. Measurements (before)

**Size.** `src/ctstudio`: 22,391 lines (core 11,725, gui 9,686, cli 888, `__main__` 85). No file
over 400 lines (largest: `views/component_card.py` 400, `views/dashboard.py` 397,
`tools/rszst_setup.py` 396, `tools/process.py` 393, `gui/main_window.py` 389); no function over
60 lines (largest: `tools/process.py` `run` 59, `views/build_log.py` `__init__` 57).

**Complexity (radon).** 1,674 blocks, average A (3.02). Worse than B: one block,
`cli/build.py` `_TextPrinter._end` C (14). xenon (absolute B, modules A, average A) also flags
three modules at rank B: `gui/assign_text.py`, `gui/dashboard_assign.py`,
`gui/dashboard_reconcile.py`. TD-008: `scripts/bootstrap_tools.py` `unpack` and
`scripts/check.py` `run_step` C (12) (scripts are outside the core-only gate). Maintainability
index: nothing below B.

**Dead code (vulture).** `vulture src/ --min-confidence 60`: 63 hits in 25 files (62 with
the gate's `vulture_whitelist.py`), all triaged: 18 are `core/project/manifest.py` schema
fields read by the TOML parser and its tests; 25 are tested Phase 2 tool adapters and their
result fields (`wiimm`, `wiimm_kcl`, `wiimm_convert`, `wiimm_autoadd`, `riistudio`, `abmatt`,
`abmatt_edit`, `blender`) that Phases 6-10 call (docs/reference/TOOLS.md); Qt overrides
(`roleNames`, `dragEnterEvent`, `dropEvent`, three `isComplete`), a ctypes field and a
Protocol parameter are false positives; the rest (`PathLabel.full_text`, `retained_chars`,
`slots.cup_number`, `spec.licence`, `watch.wait_ready`, `lock.took_over_from`,
`Project.lock_owner`, …) are read by tests or kept on purpose (section 2). Nothing deleted on
this evidence alone.

**Duplicates (pylint, 6+ lines).** 4 pairs: `cli/doctor` / `cli/status` (settings read),
`custom_tool_preferences` / `wine_preferences` (text check), `status_service` / `watchdog`
(thread start), `build_page` / `machine_choice` (job choice rows).

**Coverage.** 98 % overall (13,237 statements, 226 missed); core ≥ 85 % and gui ≥ 60 % met in
every module but one: `gui/editor_settings.py` 54 %, whose code runs on a `QThreadPool` thread
coverage.py does not follow (see section 2, worker helper). Next lowest: `tools/process_tree.py`
73 % (platform branches).

**Dependencies.** Runtime: PySide6, numpy, Pillow, platformdirs, tomli-w, watchfiles. numpy
and Pillow are not imported by `src/` yet (ADR-001; the texture and preview phases use them);
kept. Dev: `pytest-benchmark` is unused (the benchmarks time themselves).

**Start-up.** `python -X importtime -c "import ctstudio.gui.app"`: 708 ms cumulative; top
entries `gui.main_window` 313 ms, `gui.services` 161 ms, `importlib.metadata` 142 ms (read
for `__version__` at import, paid by every CLI command too), `gui.appearance` 138 ms,
`core.project.settings` 119 ms.

**Benchmarks** (`uv run pytest -m benchmark -q -s`, 4 runs) against the P4-T08 baseline:

| What | Now | P4-T08 |
|---|---|---|
| Typical track, first test build | 0.80–0.86 s | 0.67–0.72 s |
| Same, no-change rebuild in-process | 57–63 ms | 41–48 ms |
| Same, whole `ctstudio build` process | 615–641 ms | 474–515 ms |
| 100 MiB part staged / unchanged | 0.55–0.83 s / 18–23 ms | 0.51–0.52 s / 21–23 ms |
| Cache key, 1,000 × 4 KiB inputs, cold / warm | 7.6–8.3 s / 275–355 ms | 0.78–0.84 s / 252–260 ms |
| `hash_file` 200 MiB | 0.43–0.46 s | 0.39–0.40 s |
| Status, 20 parts, cold / warm | 109–119 ms / 10.5–16 ms | 68–72 ms / 10–11.5 ms |

The cold cache key is ten times slower, but not because of CT Studio: plain Python opening
the same 1,000 freshly written files takes 7.4 s the first time and 0.12 s the second, with
Windows Defender real-time protection on (`Get-MpComputerStatus`). A profile of the cold
check puts 7.0 of its 8.5 s inside `io.open`; CT Studio's own share is about 1 s (path
resolving 0.4 s, hashing reads 0.5 s). The other "first time" figures carry the same cost.
Nothing to fix in the product; first builds of new files pay the antivirus scan.

## 2. Simplification

An independent audit (fresh context, read-only) found about 200–300 behaviour-preserving
lines (≈ 1 % of `src/`): the code is already near the size limits and most of what vulture
lists is planned work. The 5 % target is therefore measured on the files a change touches,
not on whole packages, and each change is its own tested commit:

| Step | What | Lines (net) |
|---|---|---|
| a | `settings.py`: one `_with` setter helper and one ordered check table; `cli/doctor` reuses `cli/status`'s settings read; Wine prefixes reuse the custom-tool text check | −75 in 4 files (641 → 566, −12 %) |
| b | Complexity: `cli/build.py` summary split (`_found`, `_counts`; was C 14), TD-008 `bootstrap_tools.unpack` (`_extract`, `_content_root`) and `check.run_step` (`_execute`), one `isinstance` in `dashboard_assign.completed` | +15 (splits); no block above B left |

Kept on purpose (audit list C): the tool adapters; schema fields; `Project.lock_owner`
(set from the lock on open and read by nobody yet; one line that says who holds a read-only
project's lock, left for when a notice needs it); the five `dashboard_*` controllers (they keep
`dashboard.py` under 400 lines); the two build/launch controllers' start-up race logic.

Step evidence (each: scratch mutants caught by assertions, independent review, local gate,
exact Check on Windows and Ubuntu):
- a `36ddcb3`: 13 mutants; review APPROVE (614 side-by-side cases identical to the old code);
  gate 5587/10/178; Check Windows 140780147710 (5582/15), Ubuntu 140780148054 (5583/14).
- b: 18 mutants over five rounds, all caught (two existing unpack tests rewritten so a
  refusal or fallback break fails an assertion; new tests for "1 note", the missing-tool
  message, an info-only build without a findings block, the order of the counts and the
  removed staging folder: the last three from the review, APPROVE, whose old-against-new
  comparison matched in 10,368 summary cases, 16 gate-step and 12 unpack scenarios).
  The three GUI modules xenon ranks B keep every block at B or better; the gate's module-A
  rule covers `core/` only, so they stay as they are.
