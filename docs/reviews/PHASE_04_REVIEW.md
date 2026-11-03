# Phase 4 review — build engine and SZS assembly

Independent fresh-context review of `503dd1e` plus the Phase 4 brief. Reviewer ran the full gate (2,011 tests, green), 10 real-tool integration tests, 5 local-only realdata tests, all 5 benchmarks, and the CLI by hand in a disposable Unicode-path project. Check and Integration CI were green on Windows and Ubuntu. Scratch mutation checks: 8/8 caught; no copyright material entered the repository. The review surfaced one Must fix, seven Should fix items and nine Consider items. Original line references below refer to `503dd1e`; the gate fixes change them.

## Must fix — resolved, independent recheck pending

1. `core/build/cache.py:167`: refreshing a skipped cache entry dropped `entry.issues`. First skip showed findings, later skips did not. Fix: retain issues while refreshing timestamps. Added a multi-skip and on-disk `cache.json` regression test (`test_build_validate.py`, `test_build_cache.py`). The new tests failed with the old code and pass after the fix. Independently recheck before the phase tag; green CI alone is insufficient.

## Should fix — resolved or explicitly deferred

1. `core/build/cache.py:97`, `validate.py:63`: identical input bytes at another path let a new slot reuse a stale validation result. Fix: include the input's project-relative path in the key. Regression tests rename a source and switch track slots while keeping bytes. Old-slot archives remain in `build/` so the user can recover them; the build only reports the current slot.
2. `cli/build.py:142`: a closed output pipe (`--json-events | head`) caused a traceback and exit 120. Fix: cancel, discard subsequent stdout and exit 1 with a short message. Unit and real-process tests close the reader after the first event.
3. `core/build/assemble.py:112–118`: replacing a hand-edited SZS discarded the edit. Fix: the runner backs up any previously recorded output whose hash changed, including the SZS, before the step runs; failed backups stop the step and keep the edit. The cache retains output records for `--force`. Tests cover the edited track, multiple backups, untouched/deleted files and no-space errors.
4. `core/tools/wiimm.py:47–51`, `runner.py:211`: a Cygwin crash was explained only in raw tool terms; private `details` were not written to the build log. Fix: a plain `ASSEMBLE_TOOL_CRASHED` issue with a re-export hint; full tool output appears only in the log. Test checks both the event and the log. A tool's own numbered ERROR still retains its specific message.
5. `core/build/project_build.py:61–63`: `--only kcl` planned unsupported auto parts before choosing KCL. Fix: the graph factory ignores all other parts, then selects the requested subgraph. Test uses an auto course model beside a manual KCL.
6. `docs/user/PROJECT_FILE.md:49`: `extra_wszst_args` claimed to work but was ignored. The documentation now labels it reserved; P7-T06 in the Phase 7 plan covers safe adapter wiring, validation and cache-key inclusion, as well as the documented but unimplemented hooks. This is deferred rather than silently pretending it works (STATUS Plan changes).
7. `tests/unit/test_build_runner.py:112,119,178`, `test_build_runner_stops.py:56,173`: sleeps and wall-clock bounds tested concurrency. Replaced with barriers/events and removed the speed assertion; the existing real benchmark covers performance. The recorder's tiny sleep only tests serialized callback delivery, not timing synchronization.

## Consider — triaged

1. `cli/build.py:79–82` lock message: changed to cover another CLI build as well as the GUI.
2. `core/tools/wiimm.py:224` stack dump: cleanup added to the assemble crash path. Normal `create_szs` still uses the stage parent as cwd because recorded invocations expect it; changing that is adapter work, not necessary for this gate.
3. `core/build/project_build.py:105–107` Wine-only tool: now says it was found but cannot be used for builds yet.
4. `cli/build.py:204–207` info noise: human output summarizes the number of info notes and leaves their text in the build log; JSON still carries all findings.
5. `graph.py`/`stage.py` overlap and file-expansion duplication: keep the small local helpers for now; moving them across layers risks entangling build graph and filesystem policy. The duplicate `BUILD_DIR` was consolidated into assemble.
6. `project_build.py:83–95` did-you-mean path: retain for direct callers (the future Build page); argparse's choices handle CLI usage errors.
7. `objects.py:37` AutoAddLibrary text parsing: moved to an adapter-owned `names` property with a unit test.
8. `runner.py:128–130` when a UI event callback raises, queued completion events may not update state.json: no state is recorded for those steps despite completed output. Defer to P5 Build page (UI callback owner), with a regression test before that page uses the runner; normal CLI output-closed abort cancels and exits instead. Record in STATUS technical debt.

## Gate evidence and release order

- Focused gate-fix unit tests: 313 passed (before the real-process closed-pipe test).
- Real-tool build and closed-pipe tests: passed locally; benchmarks: 0.69 s first test build, 41 ms unchanged, ~485 ms whole process, 100 MiB stage 0.49 s, 1,000 warm inputs 260 ms. Under §15 limits.
- Final `check.py --all` on the gate fixes: 2,027 passed, 6 skipped, 175 deselected;
  ruff, pyright (0 errors), 3 import contracts, xenon, vulture and file length green.
  Eleven relevant real-Wiimm integration tests, five local-only realdata tests on the user's
  own ignored disc copy, and 42 focused tests from a `Q:` checkout all passed.
- Windows/Ubuntu CI and independent Must-fix verification: pending when this draft was
  written; add actual results before tagging.
- No copyrighted files in the changes. Committed tests use synthetic/recorded inputs; local-only realdata reads the user's own ignored files.
