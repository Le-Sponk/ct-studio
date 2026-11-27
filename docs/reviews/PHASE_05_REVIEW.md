# Phase 5 review — GUI shell and dashboard (manual-mode MVP)

Independent fresh-context review of `6ca155c` plus `docs/reviews/PHASE_05_BRIEF.md`, in a
detached worktree. The reviewer ran `scripts/check.py --all` (5,535 passed, 3 failed: two need
the vendor submodule a fresh worktree lacks, one was the timing flake below; ruff, pyright,
import contracts, complexity, dead code and file lengths all passed; coverage 98 %), the
real-tool integration selection (129 passed, 17 skipped: Linux-only, Wine desktop, moderngl,
and two hand-installed editors), the screenshot block of `P5_T10_UX.md` (31 passed, 174
pictures, a representative set judged by eye) and the offscreen smoke start. Scratch mutations:
3/3 caught by assertions (a stale status result kept after Clear, `build/` watched, a status
refresh during a build). No copyright material entered the repository. Line references are to
`6ca155c`.

## Must fix — resolved, independent recheck pending

1. `tests/gui/test_dashboard_reconcile.py:105` `[error6-lock]` timed out under full-suite load:
   its bounded wait was a fixed 5 s (`reconcile_helpers.py:55`), and three copies of the wait
   helper had 5 s and 10 s limits. Fix: one shared `tests/gui/waits.py` `settled` with a 20 s
   limit measured in elapsed time; the three copies re-export it. It never raises, so a broken
   condition is an assertion failure, only later; the one file whose pytest-timeout was 20 s
   (`test_error_details.py`) now allows 60 s, so the timeout cannot fire first. The 5 s limit also sat inside the known whole-process
   stall of TD-018 (P13-T06), which the longer limit tolerates without hiding real hangs.

## Should fix — resolved or explicitly deferred

1. `gui/views/build_controls.py:133`: the build bar said "Build succeeded" when the check had
   found errors that stop the game loading the track. Now: "Build finished in … s, but the
   check found N errors: the track may not load in the game yet. See Issues." Warnings, hints
   and info leave a success; a failed build still says failed. Tests:
   `test_build_result_issues.py`; the end-to-end flow (its fixture track has check errors) now
   expects the new wording. `PROJECT_NAVIGATION.md` explains it.
2. `gui/views/new_project_pages.py:117,188`: the wizard's pages checked the disk on every
   keystroke and again in every `isComplete` call (Qt asks often). Fix: one check per edit,
   kept for `isComplete` and checked again when a page is shown again after Back
   (`test_new_project_disk_checks.py` counts the calls and covers Back). Deferred to
   P13-T06: moving that one remaining check per edit off the GUI thread with a short delay;
   it matters only on a slow or sleeping network drive, and project creation itself already
   runs on the wizard's worker and refuses a used folder there.
3. `gui/services.py:179-311`: the same refusals were pasted five times. Fix: one `_ready()`
   helper with the shared order (no project, building, read-only when named, statuses being
   checked); messages and hints unchanged. One order changed on purpose: opening an editor
   in a read-only project while statuses are being checked now says read-only (waiting cannot
   fix that) instead of "still being checked" (`test_editor_requests.py` pins it). New tests:
   build and outside-edit requests refuse a read-only project (`test_assign_requests.py`).
4. Checklist §3 asks for a clean stall-watchdog log during GUI tests; nothing produced one.
   Fix: the end-to-end studio fixture runs `StallWatchdog` at developer mode's 100 ms limit
   from the first idle welcome page until shutdown begins and asserts no report (six repeated
   runs clean; the fixture also asserts the watchdog is running). Closing joins workers on
   purpose, so it is not watched. Only a stall inside a test screenshot's grab and PNG
   encoding is excused (it passed 100 ms in 2 of 18 runs on a loaded machine); a stall while
   the test waits in the event loop, in a product slot, or in the events processed before the
   grab still fails the test (`test_e2e_stall_filter.py`). The check assumes a machine
   that is not saturated: clean in 12 of 12 runs beside 8 CPU-heavy jobs on 16 cores, but 4 of
   10 failed with all 16 cores busy, where the OS starves the UI thread anywhere. Tests run one
   at a time locally and in CI; do not run the end-to-end tests beside CPU-saturating jobs.
5. `docs/ARCHITECTURE.md` §3: the source tree listed packages that do not exist and missed
   24 GUI modules. Rewritten as built at the end of Phase 5, with planned packages marked.
   Trimming the per-task notes in the rest of the file belongs to P5-DEEPCLEAN step 5.

## Consider — triaged

1. Six ways to run background work (thread relays, `QThreadPool`), with uneven handling of a
   thread that fails to start (`status_service.py:139` has none): P5-DEEPCLEAN, one shared
   joined-worker helper.
2. `main_window.py:360,368` called the private `dashboard._sync()`: now public `sync()`.
3. Menu order File · Settings · Help · View: Help is now last (`test_shell.py` pins it).
4. `getattr(manifest.components, part_id)` in `edited.py:127` and `services.py:272`: now use
   `spec.manifest_table`, like every other caller.
5. A build error with its own "Next:" step also got "Review the problem and retry the build":
   the general step is now added only when the error has none (tested both ways).
6. `main_window.py:56-75` offscreen-font code is test support in the window module:
   P5-DEEPCLEAN.
7. Wizard summary label and value columns nearly touched in the dark, enlarged picture:
   horizontal spacing 16 px.

Not re-reported (already deferred, P13-T06): the build-bar message cut at 150 %, card spacing,
capped card text without "…".

## Gate evidence and release order
Fixes committed as `ed47f48` after three independent delta re-reviews (NEEDS_REVISION: the
watchdog flake, the timeout overlap, the Back gap, the refusal order, doc wording; then
NEEDS_REVISION: the stall filter too lenient; then APPROVE). The Must-fix recheck was part of
the first re-review: the shared 20 s wait fails as an assertion inside its module timeouts.
Scratch mutants of the changed lines: 26 over six rounds, all caught by assertions; strict
pyright adds no error on Windows or Linux (the older ones in the changed files are on untouched
lines of `test_shell.py`). Local gate green: 5,570 passed, 10 skipped, 178 deselected; real-tool
integration selection on `ed47f48`: 129 passed, 17 skipped (Linux-only, Wine desktop, moderngl,
two hand-installed editors). Exact Check on `ed47f48`: Windows 140751413380 (5565 passed / 15 skipped),
Ubuntu 140751413761 (5566 passed / 14 skipped), 5,580 selected; artifacts 15234106604 / 15233945946, coverage.xml
only. The Integration workflow did not trigger (no change under its paths; core/tools, build
and validation untouched); the nightly at `07b5d4c` was green. Tag `phase-05-done` on the
closeout commit after its Check CI. HC1 (the owner's hands-on checkpoint) and Deep Clean #1
follow.
