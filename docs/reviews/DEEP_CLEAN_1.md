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
| c | Start-up: `ctstudio.version()` reads the package metadata on first use (module `__getattr__` keeps `__version__`); `--version` reads it only when asked; Help → About is built when first shown | `importlib.metadata` no longer imported by a CLI command or a window start (was 142 ms) |
| d | `gui/views/plain.py`: `plain_label` (plain text, wrapped; `fill`, `selectable`) and `busy_bar` (`slim`) replace the same 4–8 setup lines in 17 view files | −43 in 18 files (3,925 → 3,882) |
| e | The offscreen font loader leaves `MainWindow` for `gui/offscreen_font.py`: `run_gui` calls it before the window (smoke frames), a GUI-test fixture once per test; the last two hand-built labels use `plain_label` | +9 in 5 files (920 → 929; `main_window.py` 397 → 372) |
| f | Five copies of "run one job on a thread, hand the result back after the thread ended" (welcome page, build settings, project details, new-project wizard, status checker) become `gui/joined_worker.py`; a thread that cannot start now reports in the status checker (it stayed busy for good), the wizard and the welcome page (the error escaped; the page stayed busy) | −63 in the 5 users (1,195 → 1,132), +93 for the shared helper with its docs |

Kept on purpose (audit list C): the tool adapters; schema fields; `Project.lock_owner`
(set from the lock on open and read by nobody yet; one line that says who holds a read-only
project's lock, left for when a notice needs it); the five `dashboard_*` controllers (they keep
`dashboard.py` under 400 lines); the two build/launch controllers' start-up race logic.

Step evidence (each: scratch mutants caught by assertions, independent review, local gate,
exact Check on Windows and Ubuntu):
- a `36ddcb3`: 13 mutants; review APPROVE (614 side-by-side cases identical to the old code);
  gate 5587/10/178; Check Windows 140780147710 (5582/15), Ubuntu 140780148054 (5583/14).
- b `d682f5d`: gate 5591/10/178; Check Windows 140794116190 (5586/15), Ubuntu 140794115864
  (5587/14). 18 mutants over five rounds, all caught (two existing unpack tests rewritten so a
  refusal or fallback break fails an assertion; new tests for "1 note", the missing-tool
  message, an info-only build without a findings block, the order of the counts and the
  removed staging folder: the last three from the review, APPROVE, whose old-against-new
  comparison matched in 10,368 summary cases, 16 gate-step and 12 unpack scenarios).
  The three GUI modules xenon ranks B keep every block at B or better; the gate's module-A
  rule covers `core/` only, so they stay as they are.
- c: 12 mutants over three rounds, all caught (new tests: a parsed command does not import
  `importlib.metadata` nor carry a `version` value; `--version=x` is still refused; other
  missing names still raise; About is not built until shown, and is the same dialog after).
  Review NEEDS_REVISION, all fixed: the window built About (so read the metadata) at start;
  `version=None` appeared in parsed arguments; pyright stopped flagging unknown package
  names. Its comparison of 325 command lines was byte-identical except at 12 columns, where
  argparse used to wrap `ctstudio 0.1.0.dev0` onto two lines and now prints one. Median
  wall time old/new: `status --help` 476/400 ms, `import ctstudio.gui.app` 789/630 ms,
  `--offscreen-smoke` 936/820 ms (before the About fix).
- c `04cb3b1`: gate 5603/10/178 (after the wait repair `83f6c4e`, Check Windows
  140813740900 5595/15, Ubuntu 140813740677 5596/14: two gates had failed on a 5 s
  `qtbot.waitUntil` default under load).
- d: 14 mutants over two rounds, all caught (new `test_plain_widgets.py`; the issues
  panel's texts are selectable and the Tools busy bar thin, both untested before). Found,
  not changed here: the new-project wizard's problem label is not plain text, so a message
  that looks like HTML would be formatted (fixed separately).
- d `9aba151`: gate 5607/10/178; review APPROVE (309 labels and bars in nine real windows,
  old and new identical); Check Windows 140910864126 (5602/15), Ubuntu 140910864354
  (5603/14). Its finding became two fixes: `09c6a2e` (12 labels that repeat typed names or
  paths are plain text; Check 140917736606 / 140917736876) and `699e76d` (a file name's
  "&" in the editor-choice heading).
- e: 9 mutants, all caught (`test_offscreen_font.py`: loaded only offscreen and without
  fonts, the platform's font file, refused or missing fonts change nothing, the smoke run
  loads it before the window).
- e `bfb536e`: gate 5621/10/178; review APPROVE; Check Windows 140926153489 (5616/15),
  Ubuntu 140926153285 (5617/14).
- f: 9 mutants, all caught (no join before delivery, expected refusals logged, faults not
  logged, a start failure raised, a result delivered after shutdown, shutdown ignoring a
  running job, the thread kept after its result, the status checker dropping a start
  failure, the wizard logging user refusals). New tests: `test_joined_worker.py`,
  `test_new_project_start_failure.py`, and a status-service start-failure case; both
  start-failure tests fail on the old code.
  Review NEEDS_REVISION: (1) a stop was permanent, but a refused window close keeps the status
  checker in use, which then stayed on "Checking…"; each start now has a serial, `shutdown`
  drops only results already on their way, and the worker starts again (tests: restart after
  shutdown, a queued result dropped, the status checker answering after a shutdown).
  (2) the welcome page's start-failure handling had no test; added. (3) a re-run that cannot
  start is now reported after the older run's result, not before it. (4) the shutdown test
  flushes queued events instead of waiting 100 ms. An older refused-close problem in the
  welcome page went to Phase 13 (P13-T06). The first full gate then caught a fault of this
  step: the welcome page announced "busy" before the worker counted as busy, so the window
  left Open project on while a project was opening (`test_dashboard_window.py`); the page now
  starts the worker first. After the fixes: 14 mutants, all caught (rounds 7 and 8; adds a
  stale result delivered, the serial not bumped by shutdown, a permanent stop, the re-run
  reported first, "busy" announced too early, the welcome start failure lost). Delta review:
  all four findings fixed; one gap closed (busy must stay on during `updated` while a re-run
  is queued: a test and a 15th mutant, round 9, caught).
