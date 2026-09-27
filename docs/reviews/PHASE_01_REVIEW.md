# Phase 1 review — skeleton and quality gates

**Gate:** P1-GATE · 2026-09-28 · fresh-context reviewer delegated from
`docs/reviews/PHASE_01_BRIEF.md` and `docs/process/REVIEW_CHECKLIST.md`.
The reviewer did not change the tracked tree; the implementer triaged and fixed the findings.

## Findings and disposition

### Must fix
None reported by the independent reviewer.

### Should fix — all resolved
1. `scripts/check.py:68-70` reported coverage but did not enforce the core ≥85% and
   GUI ≥60% statement-coverage thresholds. The reviewer measured 95.2% / 76.6%.
   The normal gate now parses a temporary pytest-cov JSON report and fails when
   either package is below its own threshold or missing; `--fast` intentionally
   excludes coverage. Tests verify package separation and a zero-exit pytest
   subprocess still fails the gate if its report is below threshold.
2. `src/ctstudio/__main__.py:39-43` launched the GUI without configuring the
   documented package logger. GUI startup now calls `configure_logging()` before
   `run_gui()`; `--version` stays Qt- and logging-free. A GUI entry-point test
   asserts invocation order. The logging initializer also converts folder/open
   failures into typed, actionable `ProjectError`s without touching user files.
3. `src/ctstudio/gui/app.py:21-23` wrote the final screenshot directly, leaving
   a partial PNG after a write failure. It now stages a complete same-directory
   file and publishes with a no-clobber hard link, cleaning the staging file on
   failures. Tests cover successful Unicode paths, existing work, and injected
   publish failure leaving neither a destination nor staging file.

### Consider
- `STATUS.md:9-10` named an older green commit despite newer green main CI.
  Update its pointer during gate closeout. No separate tech-debt item.

## Independent evidence and remaining scope
- Reviewer ran `uv run python scripts/check.py --all`: seven steps passed,
  **125 passed / 1 optional skip**. Integration (non-network): **71 passed /
  6 skipped**; broad non-network: **198 passed / 19 skipped**; focused GUI:
  **7 passed**. 200 MiB hash benchmark: **0.396 s**. Main CI
  [36343346249](https://github.com/Le-Sponk/ct-studio/actions/runs/36343346249)
  was green on Ubuntu and Windows before the fixes.
- Reviewer made three independent mutations in isolated scratch copies. Tests
  caught each: `test_backup_naming_and_original_revisions`,
  `test_log_file_in_unicode_path_contains_json_records`, and
  `test_offscreen_smoke_never_overwrites_an_existing_png`.
- Reviewer inspected Windows light/dark/150% dashboard and light/dark About PNGs:
  readable text with no visible truncation. The optional Mint PNG **pixels**
  remain uninspected by the user's deferral; Linux CI checks screenshot creation
  and font availability, not visual readability. Tests requiring optional
  Dolphin, Wine, Xvfb, ImageMagick or moderngl remain explicit skips. The
  scheduled nightly network job has not completed green; the prior non-green
  skip-signal probe is not presented as a completed nightly run.
- After the three fixes, local `check.py --all` passed seven steps, **130 passed /
  1 optional skip**. Non-network integration: **71 passed / 6 skipped**;
  broad non-network: **203 passed / 19 skipped**. `git diff --check` passed.

## Gate closeout
Remote CI for the fix commit, STATUS/phase update, and `phase-01-done` tag
remain pending at this point. There is **no human checkpoint at Phase 1**;
HC1 is after Phase 5 (`docs/ROADMAP.md`, `docs/process/HUMAN_CHECKPOINTS.md`).
