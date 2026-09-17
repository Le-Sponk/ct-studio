# AGENTS.md — MKW Track Studio

You are the lead engineer building **MKW Track Studio**: a cross-platform (Windows + Linux first-class)
desktop app that turns a Blender project into a finished Mario Kart Wii custom track (`.szs`). It
orchestrates Wiimms SZS Tools, a BRRES backend (RiiStudio CLI / ABMatt), Blender + the
Blender-MKW-Utilities add-on, and external editors (BrawlCrate, RiiStudio, KMP editors, Dolphin).
Beginners should rarely leave the app; veterans must never be blocked from doing things manually.

This file is injected into every message. Keep it short. Details live in `docs/`.

## Session start (every session)
1. Read `STATUS.md` → find the current phase and next task ID.
2. Read that phase file in `docs/phases/`. Read only the other docs the task references.
3. Load skill `mkw-task-loop` and follow it. At a phase gate, load `mkw-phase-review`.

## Hard rules
1. **One task ID per session.** Don't start the next phase until its review gate is recorded in STATUS.md.
2. **Layering:** `trackstudio.core` never imports Qt, `gui`, or `cli` (import-linter enforces).
   `blender_bridge` imports only stdlib + `bpy`.
3. **External tools only via `core/tools` adapters.** No `subprocess` anywhere else. Never `shell=True`.
4. **Never guess a tool's CLI flags or output format.** Verify with `--help`, docs, or a real run,
   then record it in `docs/reference/TOOLS.md` with the tool version.
5. **No new runtime dependency** without an ADR entry in `docs/DECISIONS.md`.
6. **Tests ship with the change.** `uv run python scripts/check.py` must pass before every commit.
   No skipped/xfail tests or `noqa`/`type: ignore` without a one-line justification.
7. **No Nintendo game files or derived assets in git.** Fixtures are synthetic. Real files go in
   `local_fixtures/` (gitignored); tests needing them auto-skip.
8. **Size budgets:** file ≤ 400 lines, function ≤ 60 lines, cyclomatic complexity ≤ 10.
   Exceed only with a comment explaining why.
9. **Efficiency:** nothing slow on the GUI thread; vectorise geometry/image work with numpy; reuse
   file fingerprints (mtime+size fast path) instead of re-hashing; one Blender launch per build.
10. **Errors:** raise typed errors from `core/errors.py`; never swallow exceptions; every user-facing
    error states what failed, why (if known) and what to do next.
11. **Cross-platform:** `pathlib` only; UTF-8 explicit; test paths with spaces and non-ASCII;
    Windows subprocesses must not flash console windows.
12. **Never destroy user work:** back up before overwriting any file the user may have edited.
13. **Plan vs reality:** if a spike or tool behaviour contradicts the plan, update
    `docs/DECISIONS.md` and the affected phase file, log it under "Plan changes" in STATUS.md,
    then continue. If it changes user-visible scope, add a "Needs human" item and move to another
    unblocked task.
14. **End every session** by updating STATUS.md (done, next, blockers) and committing.

## Commands
- `uv sync` — install/update environment
- `uv run trackstudio` — launch GUI · `uv run trackstudio --help` — CLI
- `uv run python scripts/check.py` — format, lint, types, import contracts, unit tests, complexity
- `uv run pytest -m integration` — tests using real tools from `.tools/`
- GUI tests run headless with `QT_QPA_PLATFORM=offscreen`

## Map
- `STATUS.md` — live progress, blockers, questions for the human
- `docs/PROJECT_BRIEF.md` — what and why · `docs/ARCHITECTURE.md` — how
- `docs/DECISIONS.md` — ADRs · `docs/ROADMAP.md` — phases & gates · `docs/phases/` — task lists
- `docs/process/` — workflow, review checklist, testing strategy, human checkpoints
- `docs/reference/` — MKW domain notes, external tool catalogue
- `src/trackstudio/{core,cli,gui,blender_bridge}` · `tests/` · `scripts/` · `spikes/` (throwaway)

## Delegation
Use `delegate_task` for phase reviews (fresh context), for independent research (e.g. verifying a
tool's flags), and for parallel test-writing on modules that don't share files.
