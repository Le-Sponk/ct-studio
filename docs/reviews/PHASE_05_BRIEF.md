# Phase 5 review brief — GUI shell and dashboard (manual-mode MVP)
**Reviewer:** verify independently; this is orientation, not evidence.
Repository `C:\dev\ct-studio`.

## Goal and exit
Milestone M1 in the GUI: create a project, assign files, click Build, get an SZS, see issues,
open any file in the right tool. Exit (PHASE_05 header): the pytest-qt end-to-end flow passes
headless; screenshots reviewed; HC1 passed; Deep Clean #1. This gate covers P5-T01 … P5-T10
(all ticked; T10g moved to P13-T09, STATUS "Plan changes"); HC1 and P5-DEEPCLEAN follow it.

`git diff --shortstat phase-04-done..HEAD`: 377 files, +57k (src 92 files +11.5k; tests 255
files +40k; docs 23 files +3.8k). New `src/ctstudio/gui/` modules: services and threading
(`status_service`, `build_controller`, `launch_controller`, `watcher_bridge`, `gc_policy`,
`watchdog`, `crash`), the window and dialogs (`main_window`, `settings_window`, `views/*`:
welcome, new-project wizard, dashboard, component cards, build bar/log/jobs, issues panel,
outside-edit banner, Settings pages Tools/Editors/Build/Advanced/Appearance). Core additions:
`core/components/{assign,edited}.py`, `core/project/{watch,editor_preferences,…}.py`,
`core/tools/{commands,custom_editors,folders,saved_editors}.py`,
`core/validation/{issue_parts,report}.py`. User docs: `docs/user/{PROJECT_NAVIGATION,OPEN_IN,
SETTINGS}.md`. Reviews: `docs/reviews/{P5_T06_ACCEPTANCE,P5_T09_SCREENSHOTS,P5_T10_UX}.md`.

## Checks to reproduce
On this Windows git-bash host, first
`export PATH="/c/Users/admin/AppData/Local/Microsoft/WinGet/Links:$PATH"`.
- `uv run python scripts/check.py --all` (local at `6ca155c`: green, 5,547 passed, 10 skipped,
  178 deselected). Check CI on Windows + Ubuntu green at `2f032d9` (5,557 selected).
- Integration (real tools in `.tools/`): `uv run pytest -p no:cacheprovider -q -m "integration and
  not network and not slow and not realdata" tests/integration -rs`. Nightly Integration was
  green at `07b5d4c` (2026-11-26).
- The end-to-end flow and pictures: the bash block in `docs/reviews/P5_T10_UX.md`.
- Run the app: `uv run ctstudio` with no arguments opens the window; use a scratch project.
- Mutation spot-checks only in a scratch copy (`git worktree add`), never the live tree.

## Known limits to challenge
- Manual mode only builds; auto parts say they cannot be made yet (Phase 6+).
- Deferred to P13-T06 (see its notes): reviewer-copy-only `discard-*` layout failures; the
  outside-edit banner note cleared on any re-bind; no size cap on Copy details; no details for a
  step failing with a non-CTStudioError; card spacing beside a taller card; the build bar's
  message not breaking paths (cut at 150 %); capped texts without "…"; an unbuilt part's
  blocker only in its tooltip; the widest-font Settings sweep (TD-022).
- Window size/position not remembered (owner decision D5 → P13-T09).
- Linux pictures and the real desktop look are HC1's (the owner's Mint host).
- Copyright: no game data in the repo; realdata tests read the git-ignored `local_fixtures/`.
