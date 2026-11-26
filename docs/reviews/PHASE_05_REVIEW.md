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
   grab still fails the test (`test_e2e_stall_filter.py`).
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
Fixes: scratch mutants of the changed lines, all caught by assertions (two first survived
and gained tests: build refusing a read-only project, and the watchdog actually running);
strict pyright adds no error on Windows or Linux (the older ones in the changed files are
on untouched lines of `test_shell.py`). Two independent delta re-reviews found the watchdog
flake, the timeout overlap, the Back gap, the order change and a too-lenient stall filter;
all fixed above. Then: the local gate, an
independent recheck of the Must fix and the fixes, exact-SHA CI on Windows and Ubuntu, and the
`phase-05-done` tag. HC1 (the owner's hands-on checkpoint) and Deep Clean #1 follow the tag.
