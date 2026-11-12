# STATUS

> The agent updates this file at the end of every session. The human reads it to see progress
> and to answer "Needs human" items. Keep entries short; link to files/commits for detail.

**Current phase:** 5 — GUI dashboard (P4 gate passed, tag `phase-04-done`)
**Next task:** P5-T06c2b — Mount banner and present joined results
**Name:** CT Studio · package/CLI `ctstudio` · project data `.ctstudio/` (ADR-015)
**Last green commit:** `99268e8` (Check, Windows + Ubuntu)

## In progress
- None.

<!-- Task ID, one-line plan, acceptance criteria restated, files expected to change -->
## Done (newest first)
- 2026-11-12 `P5-T06c2a` Outside-edit banner presentation (`99268e8`). Signal-only native
  Lock/Discard widget: explicit eligibility, Cancel-default/escape/close confirmation, modal
  re-entry and generation guards, owner-driven progress, bounded plain-text outcomes with full
  accessible details, and complete reset. No disk/project/worker ownership; not mounted yet.
  Review exposed construction-only font caps; grow/shrink RED tests and FontChange fix pass.
  Independent re-review APPROVE: 52 focused tests, 11 original probes, 2 font-cause cases and
  3 assertion-caught controls. Main campaign: 35/35 assertion-caught; strict Windows/Linux
  typing checks all 3 touched Python files; budgets pass. Fresh locked install under a space /
  non-ASCII path passed a real Qt request/progress/reset smoke. Full gate: 3,785 passed / 6 existing
  skips. Exact Check: Windows 3,776/15, Ubuntu 3,777/14 (3,791 selected).
  Integration not triggered: presentation-only change. Remote workflow and both real artifact
  ZIPs verified coverage.xml only. Local light/dark widget sheets inspected at normal/150%
  fonts and 120% stretch; no screenshots/font binaries/game content committed or uploaded.
  C2b retains mounting, joined results, saved-state recovery and original full GUI acceptance;
  no new user-facing actions are exposed in c2a. Linux-desktop pixels remain unverified.
- 2026-11-12 `P5-T06c1` Joined outside-edit requests (`3377d56`). Lock/Discard run on
  the existing joined launch worker with memory-only service eligibility; captured results
  identify the action/part/project/root/manifest and retain the original error. The worker
  never publishes a saved manifest. Review found 3 inherited ownership faults (ambiguous
  native startup, replacement during idle callbacks, invalidated completion); fixed tests-first,
  re-review APPROVE: 20 original probes and 154 focused tests. Startup uncertainty retains
  the writer lock until join; it does not promise rollback. 34/34 assertion-only mutants
  (32 ownership/routing, 2 CI-upload), strict 10-file Windows/Linux typing and all budgets pass.
  Full final gate: 3,733 passed / 6 skipped. Exact CI Check: Windows 3,724/15, Ubuntu
  3,725/14 (3,739 selected). Integration not triggered: no real-tool/build/validation
  changes. CI now uploads coverage only, honoring local-only screenshots; exact remote YAML
  and both actual artifact ZIPs verified coverage.xml only. Final safety review APPROVE,
  4 workflow tests. No new visible controls or screenshots in c1; banner/confirmation,
  uncertain-start saved-state refresh, full watcher-to-card acceptance and user guide are c2.
  No copyrighted assets, fonts or screenshots committed or uploaded by this change.
- 2026-11-12 `P5-T06b` Lock as manual and Discard with backup, core (`c4e0488`).
  `core/components/edited.py`: `lock_as_manual` copies the edited output into `files/`
  (through `assign.copy_into_files`, backing up a different copy) and switches the part to
  manual; `discard_edit` moves it in one rename into `.ctstudio/backups/<UTC time>/`, so the
  next build remakes it without a second backup. Both refuse, changing nothing, unless the
  project is editable, the part is made by CT Studio and not manual, ctstudio.toml is
  unchanged and the output really was edited; each message says what was not done. Review:
  4 minor findings (unclear messages, empty folders left after a failed discard), fixed
  tests-first. 44/44 assertion-only mutants; strict 10-file Windows/Linux typing. Gate:
  3,671 passed / 6 skipped. Exact CI Check: Windows 3,662/15, Ubuntu 3,663/14 (3,677
  selected). Integration not triggered. Core only (no screens): GUI and user guide are
  P5-T06c. No copyrighted data committed.
- 2026-11-12 `P5-T06a` Project watcher and live status refresh (`097a204`). P5-T06 split
  into T06a/T06b/T06c (174 tasks). `core/project/watch.py` watches the project folder and the
  folders of outside `.blend`/supplied files (watchfiles, two daemon threads); output,
  `.ctstudio/` state and Blender backups ignored; an outside folder that goes and returns is
  re-watched; a gone project folder or unasked end is reported and stops the whole watcher.
  `gui/watcher_bridge.py` brings changes to the UI thread; a change starts a status check (not
  during a build), so an edited generated file shows "edited outside CT Studio" within 2 s;
  the dashboard has its own watching notice; Refresh retries. Review found a half-dead
  watcher kept, outside folders never re-watched and a stuck check; fixed tests-first,
  re-review no blockers. 73/73 assertion-only mutants; strict 13-file Windows/Linux typing;
  light/dark screenshots inspected. Gate: 3,608 passed / 6 skipped. Exact CI Check: Windows
  3,599/15, Ubuntu 3,600/14 (3,614 selected). Integration not triggered (no tool, build or
  validation files changed). User/architecture docs updated; no copyrighted data committed.
- 2026-11-11 `P5-T05b` Issues panel (GUI) (`7bc350c`), completing P5-T05. The status worker
  reads the saved check report on open, Refresh and after builds; no UI-thread file work.
  Groups show severity counts; selected findings show next step, file and part, with trusted
  wiki help and Copy report. Click or Enter scrolls to the card and focuses its first usable
  control. Missing/damaged reports explained, last results kept on check failure, cleared on
  project switch. Review found unsafe saved help links; HTTPS wiki-only validation/fallback
  fixed tests-first, re-review APPROVE (53 submitted cases + 52 independent probes).
  40/40 assertion-only mutants caught; strict nine-file Windows/Linux typing and budgets clean;
  light/dark screenshots inspected. Gate: 3,526 passed / 6 skipped; 2 real Wiimm synthetic
  validation tests passed. Exact CI: Check Windows 3,517/15, Ubuntu 3,518/14 (3,532 selected);
  Integration Windows 126/21, Ubuntu 130/17, all expected skips. User/architecture docs updated;
  no copyrighted data committed. Native Linux desktop appearance remains unverified.
- 2026-11-11 `P5-T05a` Issue report (core) (`996be87`). P5-T05 split into T05a and T05b (172
  tasks). `core/validation/issue_parts.py` `part_of(issue, root)` names the card a finding is
  about: its part id; the model a check section names (incl. `course_d_model`, the model of
  Wiimm's `_d` tracks); one of the part's files or a folder part, judged inside the project;
  or, for whole-SZS findings only, the part its measured wszst wording names. On the 99
  retail tracks 77 of 1,048 findings stay under Whole track (extra files, effects, object
  models). `core/validation/report.py`: `group_issues` (dashboard order, whole track last,
  errors → notes, stable), `counts_text`, `report_text` (Copy report Markdown; files as exact
  code spans; text escaped, one line), `load_report(root)` (None before the first check; any
  damaged file is a plain ProjectError). Tests from recorded and measured wszst 2.42a output;
  mutants 78/78; three reviews (1: `_d` name, wording, folders, Markdown; 2: slot wordings,
  code spans; 3: approve). Local 3,473 passed; CI all green (Check win 3464/15, ubuntu
  3465/14; Integration win 126/21, ubuntu 130/17).
- 2026-11-11 `P5-T04b` Drop a file on a card or Choose file… (GUI) (`36745a6`). Cards of parts
  with a manual mode and their own table accept one dropped local file or folder (always as a
  copy, so a Shift-drag never moves the original; several files, web links or plain text are
  explained or ignored) and offer More → Choose file… / Reference file in place… (keyboard
  reachable; the chooser result is re-checked). `AppServices.start_assign` refuses from memory
  (read-only, editing, build, launch or status check busy); `LaunchController.assign` runs
  `assign_file` on the single joined launch worker, so closing and project switching wait. The
  dashboard publishes the saved manifest on the UI thread, rebinds cards and rechecks statuses;
  a stale result never overwrites. Plain per-card notes (`gui/assign_text.py`; long paths
  shortened, full path in tooltip and accessible description). Core: a `files` entry that is not
  a folder is explained. Evidence: 3,385 local tests; 52/52 mutants assertion-caught; three
  independent reviews (final APPROVE); light/dark screenshots; CI Check green on Windows and
  Ubuntu (Integration not triggered: no `core/tools`/`core/build` change). P5-T04 complete.
- 2026-11-10 `P5-T04a` Assign a supplied file (core) (`913a888`). `components/assign.py`
  `assign_file(project, part, source, *, reference=False)` refuses, before touching anything and
  with a plain reason and hint: read-only project, ctstudio.toml changed on disk, a part without
  its own manual mode, a missing or unusable path, anything inside or containing `.ctstudio/`,
  a source overlapping the copy target, and the wrong type (same check as status and build).
  Default copies into `files/<game name>` (post-effects as a folder, staged and type-checked
  again); a different existing copy is backed up first (`backups.save_copies`, which removes an
  incomplete backup), an identical one is left alone; reference in place copies nothing. A
  failed copy, swap or save (also Ctrl+C) puts the old copy back or keeps it and names where.
  Tests 49 (RED first); 34/34 assertion-only mutants caught; review: 1 must-fix (raw folder
  backup message) + 7 should-fix, all fixed tests-first, re-review APPROVED. Gate 3,320 passed /
  6 skips. Exact CI `913a888`: Check Windows 3,311 / 15 skipped, Ubuntu 3,312 / 14; Integration
  Windows 126 / 21, Ubuntu 130 / 17. One local gate run failed in `test_cli_project` when a
  Windows Application Control policy blocked the fake blender.exe; it passed 3/3 alone and in
  the next gate (environment, not code).
- 2026-11-10 `P5-T03e33b` Copy command in the live log (`4ea9b40`); this completes P5-T03.
  Each tool a build step starts shows as one bold "Ran:" row (accessible text and tooltip say
  it is a Windows PowerShell/CreateProcess command line, not cmd.exe; POSIX shell elsewhere).
  Copy command (Ctrl+Shift+C on the focused list, or right-click) copies the core command text
  exactly and is disabled and inert on ordinary output, even command-looking; Ctrl+C still
  copies the shown line. A command too long for the list is not copyable (tooltip: disk log);
  an open menu never copies a different command after its row is evicted, and offers nothing
  below the rows. RED 21 + 3 new cases first; 23/23 assertion-only mutants caught; review
  APPROVED with 6 should-fix items, all fixed, re-review APPROVED (8/9 extra mutants, the
  survivor closed by an exact tooltip assertion). Light/dark screenshots inspected. Full gate
  3,271 passed / 6 existing skips. Exact CI `4ea9b40`: Windows 3,262 / 15 skipped, Ubuntu
  3,263 / 14 skipped.
- 2026-11-10 `P5-T03e33a` Trusted command events in core (`61eeba4`). `process.run` reports
  the argv it actually starts to the build step on that thread; the runner turns reports into
  `CommandRun` events with exact command text (C runtime quoting on Windows, documented as
  PowerShell/CreateProcess and not cmd.exe; POSIX shell quoting elsewhere), written to the
  build log and `--json-events`. Values a caller marks sensitive read `<redacted>` in the argv,
  the tool's output lines, the tool log and errors. Tool output never becomes a command. Text
  round-trips through the real OS parser; 23/23 assertion-only mutants caught (reviewer 26/26);
  first review's 3 must-fixes fixed, re-review APPROVED. `progress.py` now counts multi-part
  IDs (plan 91/170). Exact CI `61eeba4`: Windows 3,234 / 15 skipped, Ubuntu 3,235 / 14
  skipped. Integration (ubuntu-latest) had been red nightly since 2026-11-06 because
  GitHub's Ubuntu 26.04 image ships Wine 10's wineserver only in
  /usr/lib/x86_64-linux-gnu/wine/; `928d4d7` finds it there (3 RED tests first, reviewer 9/9
  mutants, APPROVED). Exact CI `928d4d7`: Check Windows 3,237 / 15, Ubuntu 3,238 / 14;
  Integration Windows 126 passed / 21 expected skips, Ubuntu 130 / 17. The first Ubuntu Check
  attempt aborted the Python process ("Fatal Python error: Aborted" during garbage collection
  in an unrelated GUI service test); the job re-run passed (TD-016).
- 2026-11-10 `P5-T03e34` The dashboard now follows the newest build output (`3f7c31a`), per
  the user's decision that it should scroll automatically to show the most recent logs. From an
  eligible build request the dashboard stays at its end as queued layout grows, so the newest
  log lines, build bar and late result/error stay visible in small windows. Scrolling the
  dashboard up (or Tab to a card) pauses following until the reader returns to the end or
  starts another build; rebinding stops it; focus is never moved. RED 5/5 primary assertion
  failures; 6 tests green; 9/9 assertion-only mutants caught; gate 3,225 passed / 6 skipped
  (3,231 selected); independent review APPROVED. Exact CI: Windows 3,216 / 15 skipped,
  Ubuntu 3,217 / 14 skipped (3,231 selected each).
- 2026-11-10 `P5-T03e32` Added the collapsible live build log to the dashboard (`5455d53`,
  enlarged-font card width fix `62a1745`, footer screenshot sync fix `f47420d`). Native
  virtual list on the e31 bounded model, collapsed by default, collecting while hidden,
  literal output with plain history/truncation captions; follows new output only while the
  reader is at the end, and End resumes following. Native 256-row batched layout with
  persistent anchors: geometry clamps at the 20,000-row cap no longer move a reader.
  Current-run lines only, through existing project/context guards; cleared on new run or
  rebind, kept on same-project navigation and completion. Panel sits above the build bar in
  matching Tab order. Ubuntu CI found a 47px overflow at enlarged fonts, fixed by stacking
  each card's mode text above its Change button. Windows CI found TD-015, a test reveal
  between queued layout passes; the helper now waits for settled geometry (closed).
  42 new cases; 38 parent and 3+4 reviewer assertion mutants caught; independent reviews
  approved. Final gate 3,219 passed / 6 existing skips. Exact Check on `f47420d`: Windows
  job 129621211654 (3,210 / 15 skips), Ubuntu 129621211824 (3,211 / 14); 3,225 selected on
  both, remote main verified. Native Linux desktop look not verified; no command copying (e33).
- 2026-11-06 `P5-T03e31` Added the bounded virtual Qt log model (`9ffbb9a`, test-race
  correction `a11067b`): newest 20,000 physical rows, 2,000,000 message characters, 4,096 per
  message and 128 per step ID, visible truncation and exact whole-row omission counts. Literal
  Unicode output, CRLF/CR/LF normalization, O(1) indexed storage, bounded temporary allocation,
  coalesced Qt notifications, persistent selection and clear/reuse. Full disk log unchanged.
  All 44 new cases pass on CPython 3.12/3.13; 84 model/dashboard cases after the test correction.
  Strict four-file Windows/Linux typing, Ruff and file/function/complexity budgets clean;
  model statement coverage 100%. Final hidden-tools gate: 3,176 passed / 6 existing skips.
  All 30 isolated faults assertion-caught; strengthened exact-limit truncation coverage after
  one initial survivor. Main review approved 44 + 232 existing cases, six adversarial probes
  and six independent mutants; reference checks include 262,143 reverse-scanner comparisons.
  Initial Ubuntu CI exposed a pre-existing test race: worker entry precedes queued build-plan
  delivery. Only corrected the test wait; all overlay/navigation/reset assertions retained.
  Independent delta review: 84 + 85 cases, original race assertion fails 3/3, fixed passes 5/5;
  all production hashes unchanged. Local allocation/timing samples: docs/dev/BENCHMARKS.md.
  Exact corrective Check: Windows job 127564745161 (3,167 passed / 15 skips), Ubuntu
  127564745513 (3,168 / 14); 3,182 selected on both matches local, remote main verified.
  No visible log panel or command API yet: e32 wires the view, e33 adds trusted command copying.
  Integration not applicable: GUI model/tests/docs only; no core/adapters/dependency changes.
- 2026-11-06 `P5-T03e22` Connected dashboard builds and live part progress (`1616f99`,
  font-layout correction `731fe93`). Test/release/cancel and shortcuts use the existing joined
  owner, captured project/root/manifest guards, live overlays separate from checked statuses,
  persistent errors/warnings, retry and post-build refresh. Repeated refused closes retain
  project locks and keep results visible; same-project navigation preserves progress.
  Ubuntu CI exposed a four-pixel 150%-font header overflow: reproduced locally, fixed with
  two native action rows in unchanged keyboard order, never weakened labels or width checks.
  Nine readable light/dark/native/minimum-size/font-stress screenshots inspected. 58 focused
  cases pass on Python 3.12/3.13; ten-file strict Windows/Linux typing, lint and budgets clean.
  Main, final test-only and corrective independent reviews passed, including reentrant-worker
  probes and native Tab order. All 39 isolated regressions assertion-caught with in-run origin
  hashes and unchanged checkout. Final hidden-tools gate: 3,132 passed / 6 existing skips.
  Exact corrective Check: Windows job 127269222327 (3,123 passed / 15 skips), Ubuntu
  127269222945 (3,124 / 14); 3,138 selected on both matches local, remote main verified.
  Integration not applicable: GUI wiring/layout/tests/docs only; core/adapters unchanged.
  Native desktop appearance remains a nonblocking platform gap; bounded live log follows in e3.
- 2026-11-05 `P5-T03e21` Tested standalone build-controls view (`7ddfbe2`). Signal-only
  test/release/cancel actions (Ctrl+B / Ctrl+Shift+B / Esc), planning/known-step progress,
  deduplicated terminal events, accurate joined outcomes, persistent warnings, visible errors
  and complete accessible diagnostics. No I/O, controller changes or dashboard integration:
  the controls are tested but not yet available in the app; e22 owns wiring/live cards.
  Eight light/dark/native/150%-font screenshots reviewed; Windows offscreen tests explicitly
  register a local OS font when needed (no font binaries copied or uploaded). Full gate with
  .tools hidden: 3,074 passed / 6 existing skips; all 887 GUI tests and 33 focused cases on
  CPython 3.12/3.13 pass. Strict Windows/Linux typing, lint and budgets clean; independent
  source and final test-delta reviews passed. All 27 isolated mutations assertion-caught with
  in-run origin proofs and unchanged checkout hashes. Exact implementation Check passed:
  Windows job 127213187751 (3,065 passed / 15 skips), Ubuntu 127213188073 (3,066 / 14),
  both 3,080 selected as locally. Integration not applicable: signal-only GUI/tests/docs.
- 2026-11-05 `P5-T03e1` Safe build requests and worker ownership (`98b0c66`). AppServices
  guards current-project builds using memory only (no project/read-only/checking/editing/
  launching/building refusals), preserving test/release/force/component options. Completion
  joins before releasing ownership; startup failures and interrupts retain identity/cause.
  Review reproduced native-bootstrap-before-ident and callback-restart shutdown races; both
  fixed with real bootstrap/lock regression tests, final independent re-review passed.
  24/24 isolated mutants caught by assertions; 78 focused cases passed on Windows Python
  3.12.14 and 3.13.15; six-file strict typing clean on Windows/Linux. Final hidden-tools gate
  3,038 passed / 6 existing skips; exact-commit Check Windows 3,029/15 and Ubuntu 3,030/14,
  3,044 selected on both. No widgets or adapters changed; Integration not path-triggered.
  Dashboard buttons/progress/cards follow in e2; bounded live log/command copying in e3.
  Closeout also extends the progress counter to headings 5/6 and numbered subparts, so the
  new e1/e2/e3 checklist is counted instead of silently omitted; three RED regression cases
  now pass, including e1/e10 sibling separation. Independent counter review passed: 86/165
  (also recovers an older completed Phase-2 numbered split), three isolated faults caught.
  Closeout full gate: 3,041 passed / 6 existing skips; reviewed source hashes match.
- 2026-11-05 `P5-T03i` Dashboard launch ownership and controls (`6f76373`). Open in Blender and
  card More → Open folder run on one joined background worker owned by AppServices; switching,
  editing and closing wait for it, and a timed-out shutdown keeps the project and lock. Read-only
  projects may open folders, not Blender. A separate launch notice/busy bar never clears statuses;
  stale results are ignored; text claims dispatch only. 42/42 isolated mutants caught by
  assertion; three independent reviews (one important re-review defect fixed with a regression
  test); gate 2,987 passed / 6 skips; exact-commit Check green on Windows (2,978/15) and Ubuntu
  (2,979/14), 2,993 collected. Integration not path-triggered (GUI only). Visible-desktop Blender
  and file-manager display remain under Platform verification gaps.
- 2026-11-05 `P5-T03h` Component-folder reveal service (`b57ff16`). Current registry/manifest
  locations open through a portable core adapter: file parents, directory outputs themselves,
  external/manual paths and generated locations. Missing folders/tools and parts without one
  location are actionable errors, never directory creation or fallback to an unrelated ancestor.
  Read-only/closed snapshots remain inspectable; preparation-time root/manifest changes are
  refused. Exact receipts/errors/causes/interrupts survive; no project/settings/files/locks change.
  150 new focused cases and all 761 GUI/service tests pass. Final hidden-tools gate:
  2,945 passed / 6 existing skips / 176 deselected. Adapter/service statements 40/40 and 39/39;
  strict Windows/Linux seven-file typing, lint/complexity/budgets/security scans pass. Isolated
  controls 27/27 adapter/test and 12/12 service caught by assertions with unchanged live hashes.
  Independent review passed 395 regressions, 19 boundary probes and six isolated faults. A
  test-only longer native observation avoids CI scheduling flakiness while asserting the
  unchanged production 0.4-second watch; supplemental review reproduced the old failure and
  caught three negative controls. No security/logic findings; final reviewed hashes match.
  Native Windows Explorer 10.0.26100.8875 displayed the exact Unicode scratch folder through
  the adapter, marker unchanged; only our new matching window closed. Ubuntu native xdg-open
  1.1.3 passed exact Unicode argv/cwd and exit-0/4 checks with an isolated synthetic XFCE helper;
  downloaded JUnit confirms execution, not a real Mint file-manager window. Receipt means dispatch.
  Exact-commit Check Windows 127028566413: 2,936 passed / 15 skipped; Ubuntu 127028566076:
  2,937 / 14. Selected totals 2,951 match local. Integration Windows 127028566345: 126 / 21;
  Ubuntu 127028566065: 130 / 17; every skip expected, native folder test executed on Ubuntu.
  Remote main verified. No widget changes/screenshots; T03i wires controls and worker ownership.
- 2026-11-05 `P5-T03g` Project-aware Blender launch service (`2b4110a`). Uses the selected
  project source and freshly loaded machine settings with the existing detached editor adapter.
  Missing source, read-only/closed and preparation-time project changes are refused; damaged
  settings never fall back to a different discovered executable. Exact launch receipts/warnings
  and typed errors/causes/interrupts are preserved. No files/settings/locks are written or
  changed. This is a blocking service only: caller ownership and dashboard buttons remain
  T03i; component-folder reveal is next in T03h. No original feature is dropped by the split.
  User's add-on fork already matches the tested submodule pin and remote HEAD `ffa905f`;
  README documents that integration, including its Linux/modern-Blender export role.
  Full hidden-tools gate: 2,795 passed / 6 existing skips / 175 deselected; all 686 GUI/service
  tests, including 56 new cases. Real detached runner exercised with a synthetic executable,
  Unicode/external argv/cwd and unchanged files; this does not prove Blender loaded a document.
  Service statements 27/27; strict Windows/Linux touched typing, lint/complexity/budgets pass.
  Final isolated faults 24/24 caught; 56-case baseline/restored copies green, live hashes match.
  Independent service review passed 320 regressions, 20 boundary probes and 10 isolated fault
  controls; supplemental review observed actual runner/child dispatch. All approved hashes match.
  Exact-commit Check Windows 127003211654: 2,786 passed / 15 skipped; Ubuntu 127003212021:
  2,787 / 14. Both selected totals 2,801 match local; remote main verified. No widget, core
  adapter or pipeline behavior changed, so new screenshots/real-tool Integration not applicable.
- 2026-11-05 `P5-T03f` Dashboard mode and component controls (`49eb132`; test fix `c073c9e`).
  Registry-driven mode buttons and native overflow menus open an explicit Save/Cancel dialog.
  Loading/saving use the existing joined worker and modal project ownership; only successful
  saves publish the manifest and recheck statuses. Cancel/errors retain last-good cards and
  user files/settings. Copy path remains available read-only. User/navigation docs updated;
  file assignment remains T04/T07, editor launching T03g and build/log T03e.
  Review caught history/status overlap caching ancestor-disabled widget state. Explicit app/
  project/path eligibility fixes modes and Copy/More; four RED regressions now pass without
  extra refreshes. Independent re-review passed 14 acceptance probes, three reverted R1 faults,
  native keyboard/accessibility and UI-thread I/O instrumentation; all five source hashes match.
  Full gate without checkout tools: 2,739 passed / 6 existing skips / 175 deselected; all 630
  GUI/service tests, including 164 new cases. Card/dialog/dashboard 100% statements; Windows/
  Linux typing, scoped complexity/budgets and native light/dark/error/saving/150% visuals pass.
  Isolated faults caught: window 27/27, overview 35/35, details 25/25, card 30/30, mode 14/14,
  independent 38/38 and history 3/3 (172/172 runs); restored baselines green, source unchanged.
  Initial Windows CI exposed an older global thread-count assertion race. An Event-controlled
  unrelated helper reproduces it; the test now checks only named build workers. Five 12-test
  runs pass, a planted owned-worker leak still fails, and independent test-only review passed
  all three negative controls with the exact test hash. No build implementation change.
  Exact-commit `c073c9e` Check Windows 126947496445: 2,730 passed / 15 skipped; Ubuntu
  126947495877: 2,731 / 14. Both selected totals 2,745 match local; remote main verified.
  Integration not applicable: no adapter, pipeline or integration-fixture behavior changed.
- 2026-11-04 `P5-T03d` Component-mode persistence (`47b70f6`). Added a blocking, registry-driven
  mode service: it changes only supported modes, preserves inactive file/template/custom and
  unknown settings, and never moves user/generated files or publishes the live manifest.
  Shared snapshot commit safety with project details: read-only/closed/foreign/stale guards,
  exact backups, no-op avoidance and expected-byte staging protection stay intact. Dashboard
  controls/worker ownership follow in T03f; launch actions T03g, then build/log T03e.
  Final hidden-tools full gate: 2,575 passed / 6 skipped / 175 deselected; 466 GUI/service
  tests, including 102 new mode cases; 100% statements in both persistence modules (22 + 70).
  Windows/Linux touched-file typing, lint/complexity/budgets and whitespace checks pass.
  New isolated mutations 35/35 caught after closing two load-test gaps; previous details
  campaign 28/28 still caught. Baseline/restored green and checkout unchanged. Independent
  review passed (237 focused regressions + 96 mode cases, three negative probes); production
  hashes verified after the six added regressions. Pre-existing NaN comparison limit is TD-014.
  Exact-commit Check Windows 126472244807: 2,566 passed / 15 skipped; Ubuntu 126472245022:
  2,567 passed / 14 skipped. Both selected totals 2,581 match local; remote main verified.
  No widget, core adapter or pipeline changes: screenshots/real-tool Integration not required
  for this service-only slice; existing details dialog regressions still pass.
- 2026-11-04 `P5-T03c` Project slot and source editing (`da5b2bb`). Project details opens
  from the dashboard; choose a replacement track/arena and optional Blender source, choose/clear,
  then Save or Cancel. Loading, validation and saving run on a joined worker; only successful
  completion publishes the new manifest on the UI thread and refreshes the header/statuses.
  Edits preserve other/unknown settings, back up exact original bytes and refuse stale disk/live
  snapshots. Modal ownership blocks project switching/lock release; active work refuses closing.
  Review caught external edits during replacement staging being overwritten. Expected bytes and
  symlinks are now checked after staging/fsync/mode-copy immediately before replacement; edit,
  deletion and late-symlink regressions pass. The residual unrelated-writer race is documented.
  Full gate without checkout tools: 2,473 passed / 6 skipped / 175 deselected; 364 GUI tests;
  120 focused filesystem/service/race tests; four local real-tool build regressions. Isolated
  mutations caught: UI 25/25, service 28/28, replacement safety 15/15; prior overview 35/35 rerun.
  Restored copies green and checkout unchanged. Both-platform typing, lint/complexity/budgets,
  light/dark/error/saving images and 150% scaling pass. Independent re-review passed (144 + 47
  + 93 tests, three negative probes); all six source hashes verified. An unrelated intermittent
  stale-lock test passed five 23-test reruns; recorded as TD-013, not weakened.
  Exact-commit Check Windows 126449908500: 2,464 passed / 15 skipped; Ubuntu 126449908946:
  2,465 passed / 14 skipped; both 2,479 collected as locally. Integration Windows 126449908427:
  126 passed / 20 expected skips; Ubuntu 126449908768: 129 / 17; no failures. Added fsutil to
  Integration push paths; remote main verified. Component/launch actions are next, build/log later.
- 2026-11-04 `P5-T03b` Live project overview (`f766568`). Opening/creating a project shows
  its metadata and all eight registry-driven cards with native status icons/text, reasons,
  mode, refresh and path copying. Background checks keep the window responsive; errors and
  same-project navigation retain the last good results. Old-project results are ignored;
  read-only/build/checking states, home/dashboard navigation and visible failures are covered.
  Editing and tool actions remain P5-T03c; GUI build controls and log remain P5-T03d.
  Full gate with .tools outside checkout: 2,340 passed / 6 skipped / 175 deselected;
  all 251 GUI tests pass, including 105 new dashboard/card cases. 35/35 isolated mutations
  caught, restored copy green and checkout unchanged. Windows/Linux typing, lint, complexity,
  budgets and 150% visual tests pass; light/dark/checking/error/small-window images inspected.
  Independent review found a same-project status-reset bug; four RED regressions now pass,
  and independent re-review passed with no security/logic findings (105 + 20 navigation tests).
  Exact-commit Check Ubuntu 126419450988: 2,332 passed / 14 skipped; Windows 126419451417:
  2,331 passed / 15 skipped. Both collected 2,346 tests as locally; remote main verified.
  Integration is not path-triggered for this GUI-only change; no tool/core pipeline changed.
- 2026-11-04 `P5-T03a` Build callback failure safety; TD-012 closed (`bb2f4eb`).
  If the event receiver fails, already-submitted workers finish; queued results and logs
  are reconciled before cache/state are saved, without retrying the receiver or starting
  waiting steps. Successful parts retain their records and cache reuse. Ordinary secondary
  recording/save failures are warning-logged; other results and independent saves are still
  attempted while the original error propagates. Interrupts are not silently ignored.
  Full gate with .tools outside checkout: 2,235 passed / 6 skipped / 175 deselected;
  26 new regressions, ten repeated runs of those 26 tests, 12/12 isolated mutations caught
  with restored copy green and checkout byte-identical; 11 real-Wiimm regressions passed.
  Independent re-review and Windows/Linux typing, lint, complexity and budgets green.
  CI Check Windows 126346682773 (2,226 passed / 15 skipped), Ubuntu 126346683093
  (2,227 / 14), both 2,241 collected as locally. Integration Windows 126346682711
  (126 passed / 20 expected skips), Ubuntu 126346683811 (129 / 17), no failures.
- 2026-11-04 `P5-T02b` Welcome screen with New, Open (Ctrl+O) and recent projects.
  Recent history persists in settings (newest ten distinct folders), retains missing entries,
  marks them and offers removal without deleting project files. Settings backups and unknown
  fields are preserved; malformed settings/history are reported without overwriting them.
  Checks, opening and history writes run on a joined worker; successful creation/opening is
  remembered; an already-current project keeps its lock; shutdown closes an undelivered
  project and drops queued results. Five screenshots reviewed (empty, recent, dark, error,
  busy). `docs/user/PROJECT_NAVIGATION.md` explains the workflow. Full gate with .tools outside
  the checkout: 2,209 passed, 6 skipped, 175 deselected; 83 new tests and 47/47 mutations.
  Windows/Linux-mode typing, complexity, lint and file limits green. Commit `8d2f788`;
  CI Windows 126321647735 (2,200 passed/15 skipped), Ubuntu 126321648196 (2,201/14),
  both 2,215 collected as locally. Integration not triggered: no adapter/build changes.
- 2026-11-04 `P5-T02a` New-project wizard (`gui/views/new_project.py`, `new_project_pages.py`):
  name and folder (shown before it is made; a folder with a project or files, a file in the
  way, a relative or empty location are refused in plain words), optional .blend (missing or
  not .blend refused), track to replace (all 42 by cup, search by name, abbreviation or cup,
  Luigi Circuit by default), summary. Finish makes it off the window's thread and waits for
  it; failures show on the summary page and Finish can be tried again. File → New project…
  (Ctrl+N) opens it and then the new project; closing the window gives the lock back.
  11 screenshots looked at (light; summary and track list dark). Mutants 43/43. Commit
  `c0d6e6b`; CI Check Windows 126301434290 and Ubuntu 126301433667 green (2,132 collected
  on each, as locally); Integration not triggered (GUI-only paths).
- 2026-11-04 `P5-T01b` Part statuses in the background and the freeze watchdog
  (`gui/status_service.py`, `gui/watchdog.py`). Statuses are worked out off the window's
  thread, once per burst of requests (300 ms), with exactly one more run when asked during a
  run; they are asked for when a project opens and after every build. With `CTSTUDIO_DEV=1`
  a window freeze over 100 ms is logged once, with where the window was stuck (an injected
  0.2 s sleep is caught; idle and 0.1 s waits are not). Closing stops both and leaves no
  thread. Mutants 41/41 caught, 2 equivalent (a guard only the type checker needs; a
  "still watching" check whose two halves always stop together). 2,079 tests. Commit
  `f548f83`.
- 2026-11-04 `P5-T01a` The app's build controller and services (`gui/build_controller.py`,
  `AppServices` in `gui/services.py`). A build is planned and run on one named background
  thread (settings, finding tools and version checks included), and every build event comes
  back to the window in order. A second build at once and a read-only project are refused; a
  build that cannot start or crashes is reported; Cancel reaches the build; closing stops it
  and leaves no thread behind. The current project stays locked while open, and is not
  switched or closed during a build. 2,054 tests; mutants 31/31. Commit `6a655dd`.
- `P4-GATE` — Phase 4 review passed (2026-11-04). Fresh-context reviewer
  (`docs/reviews/PHASE_04_REVIEW.md`, brief `PHASE_04_BRIEF.md`) re-ran the gate (2,011),
  the real-tool build tests, benchmarks, the local-only disc-track checks, the CLI by hand
  and 8/8 scratch mutations; no disc data in the repo. 1 Must fix (build findings vanished
  from the cache and the report from the second unchanged build on) and 7 Should fixes
  fixed in `2f7824b` (one, reserved project settings, documented and moved to P7-T06; a
  runner edge case logged as TD-012 for P5-T03). Gate `--all` 2,027 passed; Check and
  Integration CI green on Windows and Ubuntu. A separate check of the Must fix passed (the
  new tests fail without the fix, and a made-up project kept its 7 findings over 4 builds).
- 2026-11-03 `P4-T08` Build benchmarks (`tests/benchmarks/test_build_speed.py`, numbers and
  machine in `docs/dev/BENCHMARKS.md`): typical track first test build 0.7 s (limit 10 s),
  no-change rebuild 45 ms in-process / 0.5 s as a process (limit 1 s), 100 MiB part staged
  0.5 s, 1,000-input cache key cold 0.8 s / warm 0.25 s. Found and fixed: the warm 1,000-input
  check took 0.94 s (each path now resolved once); the track check rejected Wiimm's report
  for most real tracks (summaries list only the kinds present; LE-CODE / SLOT / SUGGESTION
  lines), now re-checked on every original track by the local-only
  `tests/realdata/test_build_original_tracks.py`. Integration CI now also runs on
  `core/build/**` and `core/validation/**` changes (it missed this commit; run by hand,
  green). 2,011 tests; mutants 21/21. Commit `5831980`.
- 2026-11-03 `P4-T07b` The `ctstudio build` command (`cli/build.py`,
  `core/build/event_json.py`). Readable progress (one line per step, then what was found,
  the track and the log), `--release`, `--force`, `--only PART`, `--json-events` (schema in
  `docs/dev/CLI.md`, checked by the tests), Ctrl+C cancels cleanly, exit 0/1/2/3; refuses
  while the app has the project open. Real-process tests with the real Wiimm tools green on
  both CI systems. 1,979 tests; mutants 33/33. Commit `7e4db32`.
- 2026-11-03 `P4-T07a` Build a project, core (`core/build/project_build.py`). The build's
  steps come from the project (each hand-supplied part, then pack and check; or one part
  only), and every tool they use is found the way doctor finds it before anything runs; a
  missing one stops the build naming it. `force` rebuilds. Real tools built a made-up
  all-manual project on both CI systems, then skipped every step on the second build.
  1,942 tests; mutants 20/20. Commit `9dc27b9`.
- 2026-11-03 `P4-T06` Validate node (`core/build/validate.py`). Checks `build/<slot>.szs` and
  writes `.ctstudio/issues.json`: one error per missing required part (from `wszst analyze`,
  which sees them with or without a KMP), then `wszst check`'s findings. Test builds never
  fail on findings; release builds fail on any error, still listing everything. The build
  cache now keeps each step's issues, so a step skipped as unchanged reports them again
  (closes the P4-T05b gap). Real-tool test green on both CI systems. 1,928 tests; mutants
  34/34. Commit `f0159fc`.
- 2026-11-03 `P4-T05b` Auto-add and missing objects (`core/build/objects.py`,
  `core/tools/wiimm_objects.py`, user setting `auto_add_library`). The assemble step passes
  `--auto-add` only for a library that passed Wiimm's check this build, and gives one warning
  per object whose files are in neither the track nor the library, naming the object and its
  files (Wiimm's own object list, read with wkmpt). Real-tool test green on both CI systems;
  realdata test with the user's own library passed locally. 1,904 tests; mutants 33/33.
  Commit `ad91b49`.
- 2026-11-03 README: "under development" notice and progress bar (`scripts/progress.py`,
  counted from the phase-file checkboxes; the gate fails while it is stale). Commit `df0bffe`.
- 2026-11-03 `P4-T05a` Assemble without auto-add (`core/build/assemble.py`,
  `wiimm.list_files`). The stage is packed with the profile's compression into
  `build/<slot>.szs` (and the `_d` copy) via a temporary folder; `wszst list` must show every
  staged file before the old SZS is replaced, so a failed build keeps the last good track.
  `wszst list` format measured (TOOLS.md). Real-wszst integration test green on both CI
  systems. Also: a build-log test no longer races the first step line. 1,872 tests; mutants
  26/26. Commit `267b996`.
- 2026-11-03 `P4-T04` Manual-mode stage steps (`core/build/stage.py`). A part in manual mode
  gets a step `stage:<part>` that checks the chosen file with the dashboard's own type check
  and copies it under its game name into `.ctstudio/stage/` (post-effects as a whole folder,
  so removed files go too). No file, not found, wrong type, inside `.ctstudio/` or a failed
  copy each fail the step with one clear Issue (`StepFailed`), shown in the build summary
  and log. Unchanged → skipped; a failed copy keeps the old one whole. Hard links deferred
  (Plan changes). 1,844 tests; mutants 25/25. Commit `4fcf8cc`.
- 2026-11-03 `P4-T03b` Build log & state (`core/build/part_state.py`, `core/build/build_log.py`).
  A step names the track part it makes (`Node.component`); after it runs the build records
  the part in state.json with the user's files behind it (the `.blend`, not the export), so
  status reads Ready, then Stale or edited outside CT Studio. One plain UTC log per build in
  `.ctstudio/logs/`, newest 20 kept; an unwritable log never fails the build. 1,823 tests;
  mutants 31/31. Commit `dc4fbe8`.
- 2026-11-03 `P4-T03a` Runner & events (`core/build/runner.py`, `core/build/events.py`).
  `run_build` runs ready steps in up to `jobs` threads (default min(4, CPUs)); a step waits
  for the steps it needs and for its `resources`, without holding up other ready steps.
  Cache hits are skipped and the cache is saved at the end. First failure or a cancel: nothing
  new starts, running steps finish and see the cancel through `ctx.cancel` (the existing
  `CancelToken`, so no `cancel.py`). Unexpected exceptions are logged and reported as
  `BuildError`; events are delivered one at a time on the calling thread; no thread is left.
  Gate `--all` 1,803 passed; timing tests 10/10 runs; mutants 29/29 (+1 equivalent,
  documented); commit a87bdf7, CI green (Windows + Ubuntu).
- 2026-11-03 `P4-T02` Cache (`core/build/cache.py`, `.ctstudio/cache.json`). Key = BLAKE2b over
  params, `impl_version`, the node's own tool versions and the content of every input (a
  folder by file name, a missing input as null). Fresh = same key and exactly the recorded
  output files, unchanged. Unchanged size+mtime is not hashed; a touched file is hashed once
  and its mtime recorded. A step that did not write a declared output is a `BuildError` and is
  forgotten; `invalidate`/`clear` for `--force`; `save` atomic and only when changed; damaged
  file → empty. Survives a moved project. `state.py` `parse_file`/`parse_object` now shared.
  Gate `--all` 1,776 passed; mutants 32/32 (3 first-round survivors became tests);
  commit 543c146, CI green (Windows + Ubuntu).
- 2026-11-03 `P4-T01` Node & graph (`core/build/node.py`, `core/build/graph.py`). A `Node`
  is checked on creation (id form, absolute paths, at least one output, plain-JSON params
  copied read-only, known tools, `impl_version` >= 1). `BuildGraph` links steps through files
  (an input equal to, inside or holding another step's output waits for it), keeps a step
  given twice once, refuses clashing ids or outputs, keeps the given order where it can,
  names a cycle step by step and gives `subgraph(ids)` for "rebuild just this" with
  did-you-mean. `from_manifest` asks a `make_part(spec, mode)` factory for each part's steps.
  Deviation (phase file): inputs are plain paths, no `Input` class. Found while committing:
  the root `build/` ignore rule hid `src/ctstudio/core/build/`; `.gitignore` exception plus a
  test that no package file is ignored. Gate `--all` 1,735 passed; mutants 39/39; commit
  70ac493, CI green (Check + Integration, Windows + Ubuntu).
- `P3-GATE` — Phase 3 review passed (2026-11-03). Fresh-context reviewer
  (`docs/reviews/PHASE_03_REVIEW.md`, brief `PHASE_03_BRIEF.md`) re-ran the gate (1,670),
  the new real-tool exit test (`tests/integration/test_cli_status_real.py`, a46b515: `new` +
  `status --json` on a fixture project), the benchmark (cold 72 ms / warm 10 ms against
  300 / 30 ms), the CLI by hand, 7/7 scratch mutations and a copyright check (no disc data).
  1 Must fix (redirected `status` output crashed on a non-ASCII name on Windows) and 5
  Should fixes fixed in 431c03f; Consider items fixed, dismissed with reasons, or logged as
  TD-011. A separate check of the Must fix passed (the new test fails without the fix).
- 2026-11-03 `P3-T07` CLI `new`, `status`, `open` (`cli/new.py`, `cli/status.py`,
  `cli/open_file.py`; `cli.COMMANDS` dispatch, still no Qt). `new` takes any slot spelling with
  did-you-mean (exit 2) and never overwrites a project; `status` reads without the lock, finds
  tools without starting any (`core/tools/availability.py`) and prints a table with icons and
  every reason, or `--json` format 1 (schema in `docs/dev/CLI.md`); exit 1 on a part in
  `error`. `open` picks the first installed editor for the file type or `--with`, and says
  that started is not loaded. 1,670 tests (subprocess runs against the fake tools in isolated
  user folders, plus a no-Qt check); mutants 33/33. Commits `a80c502`, `3073e09` (Windows CI
  caught simulated Linux PATHs built from `D:\` temp paths; fixed, skill updated).
- 2026-11-02 `P3-T06` Slot catalogue: `core/project/slots.json` generated by
  `scripts/make_slot_catalogue.py` from recorded `wstrt tracks/arenas --long` (2.42a; `wszst tracks`
  has file names only). 32 race tracks in 8 cups + 10 arenas in 2 groups, with Wiimm's English
  names and abbreviations; `find()` accepts any of them with did-you-mean errors; the loader
  re-checks the file; `--check` catches a stale file; ships in the wheel. 56 tests; mutants 29/29
  (+1 equivalent, commented). Commit `a845a14`; CI Check + Integration green on both OSes.
- `P3-T04` — Status evaluation (2026-11-02). `core/components/state.py` (`.ctstudio/state.json`:
  per made part a settings key + size/mtime/digest of its outputs and inputs; missing or
  damaged = empty, logged) and `core/components/status.py` (`evaluate(project, tools)` →
  `ComponentStatus(state, reasons)` per part). The registry gained each part's expected file
  type. 112 new tests: a 90-row table reaching all 7 statuses across all 8 parts, plus
  hash-count tests (untouched files are never hashed; a touched one once). Benchmark: 20 parts
  ~70 ms cold / ~11 ms warm (limits 300 / 30 ms, asserted) in BENCHMARKS.md. Mutants 40/40
  (one more, Linux-only, left to the Linux CI). `check.py --all` 1,561 passed; CI green — 334c69a.
- `P3-T05` — File-type sniffing (2026-11-02; taken before P3-T04, see Plan changes).
  `core/formats/magic.py`: `identify(path)` / `identify_bytes` read the first and last 64 KiB
  and recognise SZS (Yaz0), U8, BRRES, KMP, KCL, BBLM/BDOF/BLIGHT/BLMAP, PNG, DAE, OBJ and
  .blend (plain, gzip, or Blender 3+'s Zstandard form by its seek-table footer; Python
  3.12/3.13 has no zstd). Size fields must match, so cut-off files are not recognised.
  Found on real files: one original KMP (`old_mario_gc_narita`) has a shorter 0x0C header;
  accepted. `.bfg` has no magic (not recognised). Layouts in MKW_DOMAIN §11. Tests: 85 unit
  (synthetic near misses + committed real-tool files), 3 integration (wszst-built SZS/U8, both
  CI OSes), 1 realdata (every file of the user's 99 original track files, local only; nothing
  committed). Mutants 38/39; the survivor (keep trying other checks after a known magic
  fails) changes no result on any test or real file, and the code documents the rule.
  CI's first Check failed: `test_magic_files.py` read the git-ignored generated fixtures;
  now reads the committed recording inputs (72a00d3). `check.py --all` 1,445 passed; CI green.
- `P3-T03` — Component registry (2026-11-02). `core/components/registry.py`: 8 parts
  (course model, collision, minimap, skybox, course data, post-effects, objects, track info)
  with a one-sentence plain description (a test bans file-format and tool jargon), an
  mkwiiki.org page each opened on 2026-11-02 (no "Skybox" page exists; the skybox links to
  the tutorial's file overview), modes taken from the manifest, stage outputs (no clashes or
  nesting), required (all but objects) and tools per mode (all in the tool registry).
  P3-T01 gap fixed: the skybox's `template` mode + `template_track`. 44 new tests; mutants
  18/18 (P3-T01 probe re-run: 23/23). `check.py --all` 1,363 passed; CI green — d3748e8.
- `P3-T02` — Project layout, create/open, lock (2026-11-02). `core/project/project.py`
  (`Project.create/open/save/close`, §5 folders, default manifest, `.gitignore`; non-empty
  folder refused unless `force`, an existing `ctstudio.toml` always) and `lock.py`
  (`.ctstudio/lock` with pid/host/token via `O_EXCL`; dead pid on this host or damaged > 30 s
  = stale; other host respected; takeover under `lock.takeover` with a re-check; read-only
  with the holder's description). Races of 8 openers (fresh and stale lock) give exactly one
  lock on Windows and Linux CI. User doc `PROJECT_FILE.md` (folder, read-only, crash
  recovery). 41 new tests; mutants 25/25. `check.py --all` 1,320 passed; CI green — e78ca9f.
- `P3-T01` — Manifest model & TOML I/O (2026-11-02). `core/project/manifest.py` (frozen
  dataclasses for ARCHITECTURE §6), `manifest_io.py` (`load` never writes; `save` atomic via
  tomli-w), `toml_table.py` (every `ManifestError` names the key path, what is allowed and
  what was found), `migrations.py` (`(from_version, fn)` steps; v1 only, dummy v0 tested;
  newer files refused with a clear message), `slots.py` (42 `wszst tracks` names). Unknown
  keys kept per table and logged once each. User doc `docs/user/PROJECT_FILE.md` (comments
  are lost on save). 58 new tests; mutants 23/23. `check.py --all` 1,278 passed; CI green —
  commit 89cd626.
- `P2-GATE` — Phase 2 review passed (2026-11-02). Fresh-context reviewer
  (`docs/reviews/PHASE_02_REVIEW.md`, brief `PHASE_02_BRIEF.md`) re-ran the gate (1,191),
  Windows integration (113/14 listed), doctor against `.tools/`, 7/7 scratch mutations and a
  copyright spot-check (no disc-derived data). 1 Must fix (a set path the OS cannot run
  crashed `ctstudio doctor` and stuck the Tools page's Clear) fixed in bb8ef79; all 7 Should
  fixes fixed (43547f4, 02c858b): `.tools/` only in a source checkout, Integration on tool
  changes, a 400-line gate step, "required/optional" in words, typed doctor fields, a
  provenance list for all 31 retained inputs (2 rebuilt byte-for-byte on both OSes), docs.
  Consider items fixed or logged as TD-005–TD-008. Mutants 9/9 and 11/11. `check.py --all`
  1,215 passed; Integration on 02c858b: Linux 114 passed / 17 listed skips, Windows 111 / 20.
  An independent check of the Must fix confirmed it (CLI and GUI, real doctor) and found
  one Should fix, now fixed: only real "not a program" errors say so; others (too many open
  files, needs admin) give the OS reason (`ToolFailedToStart`, `process_errors.py`). Its
  three Consider items are TD-009. No human checkpoint at Phase 2 (HC1 follows Phase 5).
  Gate tag `phase-02-done`.
- `P2-T08f` — rszst adapter test and non-ASCII paths on Linux (2026-11-01).
  `test_riistudio_adapter_native` uses `tool_paths.RSZST` and runs on Linux through Wine;
  new `test_linux_paths.py` (8 tests, `latin é` / `cjk 日本`): rszst.exe through Wine keeps
  the Windows non-ASCII argv bug (exit 255, `FileNotExist`) and the cwd + bare-name
  workaround; Linux ABMatt and wszst handle both folders cleanly. All passed on Linux CI
  as first written; TOOLS.md "Non-ASCII paths on Linux". Linux Integration 112 passed /
  17 listed skips. Gate green (1,191 tests); CI and Integration green — commit c4a596f.
- `P2-T08e` — rszst/ABMatt Linux recordings (2026-11-01). `record-linux.yml` installs
  Wine, runs `wine_rszst.py` (which now records the pinned release in `installed.json`, the
  recorders' pin source; first dispatch failed without it) and records rszst and ABMatt too.
  49 rszst + 39 ABMatt cases: every file effect and input matches Windows; exit codes differ
  only in how a failure is reported (4294967295 vs 255; ABMatt crash -1 vs 1), which
  `test_linux_ops.same_exit` pins; text differences listed (ABMatt backslashes, traceback
  lines, PyInstaller wording, one helper name, rszst threaded progress order). ABMatt's
  Linux PID wording is now scrubbed. Fakes still replay Windows ops. Mutants 23/23; gate
  green (1,191 tests); CI green — commits 0b2a50e, 675cbfc, 762ec7d.
- `P2-T08d` — rszst through Wine for the Linux real-tool tests (2026-11-01).
  `scripts/wine_rszst.py` sets the pinned rszst.exe up through CT Studio's own Wine route in
  `.tools/riistudio-wine/` with a `bin/rszst` launcher; `tool_paths.rszst_path` uses it on
  Linux when no native build exists; the Linux Integration job runs it. test_brres_backends,
  test_rszst_cli, test_material_preservation and test_minimap_paths now pass on Linux CI
  (Linux Integration 101 passed / 20 listed skips, was 65/56). CI found: the launcher must
  not be `rszst` (that is the release folder), and through Wine the usage lines say
  `rszst.exe`. Windows `test_launch_watch` lower bound allows one clock tick (0.391 s read
  for a 0.4 s wait). Mutants 21/21; gate green (1,159 tests); CI and Integration green.
- P2-T08c — Wiimm/ABMatt real-tool tests and fakes on Linux (2026-11-01). The four Wiimm
  and two ABMatt integration modules no longer require Windows; their two skip-list entries
  are gone. Linux Integration on 6b8dfb1 ran all 28 of their tests green first time (65
  passed / 56 expected skips, was 37 / 84). On Linux the fakes repeat Linux help, version
  and Wiimm option-index recordings (`fake_runtime.LINUX_REPLAYED`); operation runs stay on
  the Windows recording. CI on 8ddc24d (Linux red) showed the Wiimm `version` runs must be
  compared with this OS's help reply; fixed. Mutants 10/10. Commits 6b8dfb1, 8ddc24d,
  41ec138.
- P2-T08b — Linux tool recordings from CI (2026-11-01). `record-linux.yml` (manual, and on
  pushes that change it; never pushes) recorded help for wszst/wkclt/wkmpt/wimgt, ABMatt and
  Blender, Wiimm option indexes, and ops for the four Wiimm tools (108 cases) and Blender (21)
  on ubuntu-latest. The first artifact leaked the runner's checkout folder (Linux Wiimm
  prints argv[0]; auto-add path), so the recorder now hides `.tools` as `<tools>`.
  `tests/unit/test_linux_ops.py`: same cases, exit codes, file effects and inputs as Windows;
  text differs only in five listed ways. Fakes keep replaying Windows runs on Linux
  (`fake_runtime.LINUX_REPLAYED`), as CI on 1e4470c showed they must until P2-T08c.
  Mutants 25/25. Commits b09f3b3, 9bfe396, 1e4470c (Linux CI red), fdd153f.
- P2-T08a — Nightly `Integration` workflow with real tools: both OSes bootstrap Wiimms,
  Blender, ABMatt (Windows also the RiiStudio release), generate fixtures and S2 outputs,
  Linux installs Wine 9.0 and runs the Wine rszst route; `ci_network.py --expected
  tests/integration/expected_skips.toml --os` turns any unexplained skip, failure, empty
  run or stale list entry red. First run found 3 real failures on Windows (probe stderr in
  cp1252, no GPU for editor windows) and 84 unlisted Linux skips; fixed/listed. Second run
  green: Linux 37 passed / 84 expected skips, Windows 109 passed / 12 expected skips.
  Reporter mutants 19/19 caught; gate green (1093 passed) — commits 635f82e, f765eaa
- P2-T07b — Tools page (GUI): Settings → Tools… lists every tool with a coloured status,
  details (path, how found, fix, note), Browse…/Clear (saved to settings, then re-checked),
  Re-check and Open download page; checks run in a worker behind a busy bar, newest result
  wins; damaged settings never overwritten. 25 GUI tests; 24 mutants (23 caught, the one
  survivor removed as dead code); gate green (1074 passed); CI green both jobs — commit 7a0abb6
<!-- `P0-T01` — short summary — commit abc1234 -->
- `P2-T07a` — User settings for tool paths. `core/project/settings.py`: `settings.json` in
  the user config folder (format 1, `tools` id → path); no file = nothing set; a damaged,
  unreadable or newer file is a `SettingsError` naming the file and is never overwritten;
  unknown keys (and newer tool ids) survive; every save is backed up. `diagnose(configured=)`
  puts set paths first (`source: "setting"`); one that is not a program is `missing` with
  the path and a choose-or-clear fix (no silent fallback). `ctstudio doctor` reads the file
  and warns on stderr if it is damaged. Mutants 21/21; `.tools` hidden pass; gate green;
  Ubuntu CI green, Windows CI twice missed `test_launch_watch`'s 1.1 s margin (slow runner spawn); margins
  widened (editor sleeps 4 s, watch must return < 3 s); CI green both jobs — commits bcba86f, bc583ac
- `P2-T06e` — `ctstudio setup rszst --wine` (Linux): explains the route and its 48/49
  measurement, downloads the checked release into `riistudio-5.11.5-wine/` and runs it
  through the Wine discovery finds; `--dry-run` prints the Wine commands; no Wine = exit 1
  with `sudo apt install -y wine`; refused on Windows. The default Linux build text and
  doctor's Linux "missing" fix name both routes. **[verified Mint 22.3, wine-9.0]** the
  opt-in `test_linux_wine_route_and_the_adapter_through_it` passed in 17.7 s (setup into
  `données é`, doctor `route: "wine"`, import + BRRES↔JSON + presets through Wine); the real
  CLI (isolated with `XDG_DATA_HOME`) installed, re-ran without downloading, and doctor
  showed `found 5.11.5 … (wine, installed by CT Studio)`. Mutants 12/12; gate green; CI
  green both jobs — commit a504f2c
- `P2-T06d` — Wine + `rszst.exe` route core (Linux). `rszst_wine.install_wine` makes CT
  Studio's own quiet win64 prefix (`WINEARCH=win64 wine wineboot -u`, `wineserver -w`;
  32-bit refused), downloads the checked 5.11.5 zip with the banner read through Wine and
  writes `setup.json` route `wine` last (re-running repairs, never redoes finished work).
  Discovery finds it after the native managed folder (launcher `wine`); doctor reports
  `route: "wine"`, version 5.11.5, or needs-Wine with an install-or-build fix; the rszst
  adapter runs it as `wine rszst.exe …` with `WINEPREFIX`, `WINEDEBUG=-all` and Mono/Gecko
  off, and says how to install Wine if it is gone. Unit tests with a recording Wine
  stand-in (strict absolute argv); mutants 21/21; `.tools` hidden pass; gate green —
  commit 8df8e5c
- `P2-T06c` — Linux `rszst` routes measured on Mint 22.3 (24 CPUs, wine-9.0). **Source
  build works:** `ctstudio setup rszst` built RiiStudio 5.11.5 natively (clang 19.1.1, Rust
  1.91), doctor reports `found 5.11.5 (built from source by CT Studio)`, the opt-in build
  test passed, and the probe matched the Windows recordings on 46/49 cases; the 3 others
  are the `native_only` absolute/non-ASCII path cases, which Linux handles correctly and
  Windows does not. **Wine + `rszst.exe` measured equivalent:** 48/49 (only `\` vs `/` in
  one error message), 8.9 s download + 8.6 s prefix, 12 s for all cases; it inherits the
  Windows path bugs. Enabling it as a setup route is split to P2-T06d. Recipe fixes found by
  the four Mint runs: absolute program paths for build steps, skip Ubuntu's broken cargo
  1.83–1.90 (Launchpad 2139436) and install rustc/cargo-1.91, failed steps print the log's
  error lines; probe fixes: Windows banner check through Wine, Linux stamp/program-name
  normalising. Mutants 18/18, 6/6, 8/8, 8/8. CI green both jobs — commits 052b0b2,
  bc4ea35, 81919f3, 9e56139
- `P2-T06b` — `ctstudio setup rszst [--dry-run] [--jobs N]`: Windows downloads the pinned
  official RiiStudio 5.11.5 release (size + SHA-256 while streaming, unsafe archive names
  refused, banner checked); Linux builds the pinned S3a source as six logged, cancellable
  steps after a programs/headers/disk preflight. Both land in `<user data>/tools/
  riistudio-5.11.5/` and count only once `setup.json` is written. Discovery adds the
  `managed` source; doctor reports `route` (existing/download/build) and, when rszst is
  missing, the route for this OS and what is lost. Real Windows download verified (6.7 s).
  38/38 mutants; gate 975; broad 1089. CI green both jobs — commits d92c3e4, 3e0095e
- `P2-T06` — `ctstudio doctor [--json] [--recheck]` lists every external tool with status
  (found / missing / too old / not working / needs Wine / sandboxed / not needed), version,
  path, how it was found and a plain fix hint; exit 1 only when the required `wszst` is not
  ready. Versions come from the cached P2-T02b prober; no GUI, Wine or Flatpak process is
  started. RiiStudio's GUI is now also found in the bootstrapped `.tools/riistudio/`. Real run
  on this Windows machine: Wiimm 2.42a ×4, rszst 5.11.5, Blender 5.2.2 probed; exit 0.
  27/27 mutants; gate 893; broad 1008. CI green both jobs — commit 5d361e3
- `P2-T05g2` — Windows editors run on Linux through Wine. New `core/tools/wine.py` reads the
  editor's PE architecture and the prefix's `#arch=`, refuses a 64-bit editor in a win32
  prefix before starting, converts the document with `winepath.exe -w`, and watches the
  launch for 3 s (`launch_detached(watch=)`) so `Bad EXE format` and `Wine Mono is not
  installed` (with the `winetricks -q dotnet48 win10` fix) are typed errors, not a silent
  "launched". `open_in(..., wine_prefix=, wine_executable=)` routes Wine editors and names the
  measured prefix recipe when none is given; Blender never runs in Wine, Flatpak still
  refused. Measured by the human's Mint 22.3 / Wine 9.0 probe run. 38/38 mutants; gate 847;
  broad 960; **Linux integration test 5 passed on the human's Mint desktop (27 s)**. CI green
  both jobs — commit 793e1fc (status 52f87e1)
- `P2-T05g` — new `core/tools/editors.open_in(tool_id, document)` starts BrawlCrate,
  RiiStudio, Lorenzi, KMP Cloud or Blender on one document (measured types only, path
  first, options after, detached, cwd = document folder) and returns `Launched`, never
  "opened". RiiStudio on a non-ASCII path launches with a warning; Wine/Flatpak launchers
  are refused until P2-T05g2 (split off). Probe: one window per launch for all five, either
  cwd; detached editors outlive the launcher. 22/22 mutants; gate 797 (794 passed); broad
  907; native Windows test in `dossier é 日本` 5 passed. CI green both jobs — commit 5352567
- `P2-T05f` — new `core/tools/blender.run_script(blend, script, args, …)` runs a script in
  headless Blender with `--python-exit-code 113` placed before `--python` (measured: after
  it, or outside 1..255, a failing script exits 0). Inputs are checked first, Flatpak is
  refused until verified, tool folders go first on PATH, and every nonzero exit is a
  typed `BlenderError` (script exception line, unreadable `.blend`, or exit N) with the
  output tails as details. 29/29 mutants; gate 770 (767 passed); broad 875; real Windows
  test in a `dossier é 日本` folder (arguments, failures, timeout stops Blender) 3 passed.
  CI green both jobs — commit c850029
- `P2-T05e3` — new `core/tools/abmatt_edit` (`edit_materials`, `paste_material`) sets
  translucency and cull mode, and copies one material onto another in the same or another
  archive, on staged copies. Every selector is anchored, escaped and model-qualified
  (ABMatt's are regex searches: `.` matched `matX001`); materials must exist first; no-op
  edits are skipped (ABMatt silently writes nothing); otherwise the archive must change and
  its whole `-c info` table must equal the expected one. Paste reports the textures ABMatt
  removes. 25/25 mutants (P2-T05e2 rerun 25/25); gate 739; broad 844; real Windows
  integration 3 passed in `日本` folders (edit, same-archive and minimap paste). Commit
  cf2f28e (both CI jobs green).
- `P2-T05e2` — new `core/tools/abmatt` (`convert_model`, `convert_minimap`, `parse_info`)
  stages `<model>.dae` → `out.brres` and `map.obj` → `map_model.brres` so the model name
  comes from the caller and minimap bones are made only for minimaps; puts the pinned
  wimgt on PATH; refuses missing or non-plain texture references before running; treats
  ABMatt's exit-0 `ERROR`/missing-texture texts as failures; and confirms every output with
  a fully parsed `-c info` report. Shared staging helpers moved to `core/tools/staging.py`.
  Split: material edits and copy moved to P2-T05e3. 25/25 mutants (P2-T05e still 20/20);
  gate 699; broad 800; real Windows integration 3 passed in a `日本` folder (minimap
  patched by Wiimm). Commits e887f27 (CI red: unit tests found the local wimgt) + 6ef4878
  (green on both jobs).
- `P2-T05e` — new `core/tools/riistudio` (`import_brres`, `brres_to_json`,
  `json_to_brres`, `dump_presets`) stages inputs under fixed ASCII names in a private temp
  folder (the Windows rszst mangles every non-ASCII argv path, relative too) and refuses,
  before running, missing/non-ASCII/out-of-folder textures and empty preset folders, which
  rszst silently replaces or skips at exit 0. Ten new recordings from the self-made fixture;
  replay sorts thread-ordered progress frames. Split: ABMatt moved to P2-T05e2. 20/20
  mutants; gate 653; broad 752; real Windows integration 3 passed in a folder named `é`.
  Commits 9fdf093 (CI red: staged mid-mutation-probe, a planted bug caught by CI) +
  0f3c816 (restored; both CI jobs green).
- `P2-T05d` — new `wiimm_autoadd` reads auto-add search paths, builds a library from a
  `Race/Course` folder (fails when Wiimm read no standard-named archive) and checks a
  library with `-vv` against Wiimm's list of originals. `create_szs(auto_add=)` now takes
  that report and refuses a library with no original files or any wrong file before
  running, since Wiimm silently builds without (or with wrong) objects. Recordings use
  synthetic inputs only; a `realdata` test passed against the user's own library built in
  git-ignored `local_fixtures/` (459 found, 18 missed, 0 invalid). `.gitignore` now also
  guards other disc-image formats and extracted disc trees. 18/18 mutants; gate 624; broad
  720 passed/21 skipped; real Windows 4 + realdata 1 — commits 8bbbc47, fa4c6d4.
- `P2-T05c2` — new `wiimm_kcl` reads a collision file's triangle counts, ranges and
  per-surface flag tables (both tables must agree), and patches minimap positions. Because
  Wiimm reports success when a minimap model has no position bones, that case now fails;
  a reported patch that leaves the file unchanged also fails. Gate 590 passed / 3 skipped;
  broad 681; 4 new real Windows tests; mutations 15/15 (+15/12/11 earlier probes);
  CI run 40685415799 — commit 835eb15
- `P2-T05c` — new `wiimm_convert` turns KMP files into text and back and PNGs into TEX0
  textures in eight formats with chosen mipmap counts. It refuses to overwrite files itself
  (Wiimm silently does), fails on Wiimm's exit-0 script errors, and checks each written
  file's header. P2-T05c2 (KCL + minimap) split out. Gate 557 passed / 3 skipped; broad 644;
  7 new real Windows tests; 15/15 + 12/12 + 11/11 mutations; CI run 40680107361 — commit 4462aec
- `P2-T05b` — `wiimm.analyze()` returns Wiimm's JSON analysis and fails on unsupported
  files even though Wiimm exits 0 for them; `create_szs()` builds an SZS with best/fast/no
  compression, fails on Wiimm's exit-0 "file exists"/"no folder" errors and checks the
  written file; auto-add is refused until P2-T05d. Gate 519 passed / 3 skipped; broad 599;
  7 real Windows integration; 12/12 + 11/11 mutations; Ubuntu/Windows CI run 40674591849
  green. Linux Wiimm output gap recorded — commit aaeae81
- `P2-T05a` — first adapter: `wiimm.check(szs|dir)` returns typed Issues from Wiimm's
  text report, raises on `ERROR #` even at exit 0 and on unexpected exits, checks the
  summary against parsed findings, and refuses the fake's prefix-only output as
  incomplete. New real Windows directory/empty recordings; full-SHA retained inputs.
  Gate 498 passed / 3 skipped; broad 575 passed; 4 real integration; 11/11 mutations;
  Ubuntu/Windows CI run 40669729269 green. Linux Wiimm output gap recorded — commit 1ec0ddd
- `P2-T04e` — seventh executable fake replays 16 real Blender 5.2.2 Windows headless
  runs using retained Python scripts and a known-good `.blend`. It executes exactly
  verified script bytes with the test interpreter, refuses unknown inputs (121),
  mirrors measured banner/quit/error exits and checks full input SHA-256; a `bpy` import
  fails honestly under the fake. Independent review findings fixed or documented;
  11/11 mutation assertions caught; full gate 485 passed / 3 skipped, broad suite
  558 passed / 21 skipped, real Blender subset 11 passed — commit bf90cb0
  ([CI 40660325955](https://github.com/Le-Sponk/ct-studio/actions/runs/40660325955),
  Ubuntu and Windows green). Native Linux Blender operations remain unrecorded.
- `P2-T04d` — ABMatt 1.3.2 fake replays 26 real Windows operations through the runner:
  DAE/OBJ conversion, material copy/edit, info, getopt and frozen errors. Exact inputs,
  separate texture-loss marker, verified rszst setup; unrecorded states exit 121. Review
  findings fixed; 12/12 fake and 3/3 recorder mutations caught; gate 448 passed / 3 skipped,
  broad 521 passed / 21 skipped, real ABMatt integration 8 passed — commit 78f66cc
  ([CI 40645167987](https://github.com/Le-Sponk/ct-studio/actions/runs/40645167987),
  Ubuntu and Windows green). Real Linux ABMatt operations remain unrecorded.
- `P2-T04c` — rszst 5.11.5 fake replays 39 real Windows operations through the runner;
  exact DAE/four PNG bytes, observed option combinations and strict marker contents only
  (unmodelled → 121). The generated DAE has LF in Git. 7/7 review mutations caught;
  gate 401 passed / 3 skipped, Ubuntu and Windows CI green — commits 4c9f209, 3caa5f6
  ([CI 40615110381](https://github.com/Le-Sponk/ct-studio/actions/runs/40615110381)).
  Native Linux operation output remains an explicit recording gap.
- `P2-T04b` — fake wszst/wkclt/wkmpt/wimgt replay 57 recorded real operations and 22 help
  runs; real getopt errors (110/108); anything unrecorded exits 121 with nothing written;
  `fake_tools_path` installs real launchers (Windows `.exe`, Linux sh/Python) on PATH with a
  per-call log. 18/18 mutations caught; gate 308/2, broad 381/20 — commit dd99b04
  ([CI 40595338853](https://github.com/Le-Sponk/ct-studio/actions/runs/40595338853))
- `P2-T04a` — `scripts/record_tool_help.py` records full help for wszst/wkclt/wkmpt/wimgt
  (version + `help <cmd>` for 15 used commands), ABMatt and Blender through the core
  runner (LF, install folder → `<tool-dir>`, refuses unpinned versions) into
  `tests/fakes/recordings/<tool>/<version>/windows-help.json`. `tests/fakes/help_contract.py`
  parses Wiimm/clap/ABMatt/Blender help into per-subcommand flags; all 27 TOOLS.md argv
  templates + 6 prose invocations pass, misspelt/foreign flags and unrecorded subcommands
  fail; 7/7 checker mutations caught. 17 tests; Windows `check.py --all` 215 passed /
  2 skipped. Linux help recordings (except rszst) not yet captured. Commit 9d891bf —
  [CI run 40527275382](https://github.com/Le-Sponk/ct-studio/actions/runs/40527275382)
- `P2-T02b` — `core/tools/versions.py`: documented probes only (Wine/GUI never started),
  ≤8 concurrent, 10 s timeout, exit status ignored (rszst exits -1); JSON cache in the
  user config folder keyed by tool id + resolved path + size + mtime (Flatpak: app id);
  failures not cached; `force` re-check; an unwritable cache never hides a version. Also
  fixed a P2-T03 runner bug the local gate exposed: output still queued after the tool
  exited was dropped when the line callback was slow. 14 version tests + 1 runner test
  with real fake executables and recorded rszst output; Windows `check.py --all` 198
  passed / 2 skipped; broad non-network 271 passed / 20 optional skips. First CI run
  40518987302 failed on Ubuntu (test appended a NUL byte to a script fake; fixed in
  40fbb96). No real tool version probed yet (P2-T06 checkpoint). Commits 6969b1f,
  40fbb96 — [CI run 40519561490](https://github.com/Le-Sponk/ct-studio/actions/runs/40519561490)
- `P2-T03` — `core/tools/process.py`, the only spawning module in src/: `run()` takes
  absolute argv (never a shell), adds to the inherited env, streams both pipes via
  reader threads with incremental UTF-8 replacement decoding, keeps 50-line tails,
  appends a UTF-8 log, raises `ToolNotFound`/`ToolFailed`/new `ToolTimedOut`/`Cancelled`;
  `launch_detached()` for editors. Whole-tree stop on timeout, cancel, callback error
  and leftover helpers: POSIX session + `killpg`, Windows kill-on-close job assigned
  while suspended (ADR-024, `process_tree.py`). 17 tests: live order, 2×25 MB, Unicode
  cwd/argv/env/split UTF-8, timeout/cancel/grandchild heartbeat, console window, AST
  spawn scan. Windows `check.py --all` 183 passed / 2 skipped; broad non-network 256
  passed / 20 optional skips. 12/13 Windows mutations caught; Linux branch passed CI
  but was not mutation-tested. [CI run 40448766227](https://github.com/Le-Sponk/ct-studio/actions/runs/40448766227)
  passed Ubuntu and Windows. — commit c138e66
- `P2-T02a` — filesystem-only `core/tools/discovery.py`: explicit setting → PATH →
  standard Windows/Linux locations (Wiimms, Blender Foundation newest-first,
  `/opt/blender*`, `~/Applications`) → exported Flatpak `org.blender.Blender`
  (not from inside a sandbox) → opt-in `.tools/`. `ToolLocation` records source and
  `direct|wine|flatpak` launcher; Linux GUI `.exe` editors get Wine; Linux candidates
  must be executable; the environment snapshot is copied. No process is spawned
  (ADR-023). 27 focused tests (26 on Windows + a POSIX execute-bit test on Linux).
  Windows `check.py --all` 167 passed / 2 skipped; broad non-network 240 passed /
  20 optional skips. The first Windows CI run exposed a test that put a `C:\` path in
  a simulated Linux `:`-separated PATH; fixed. Pytest failures now also emit
  sanitized public annotations, because anonymous Actions logs need admin.
  [CI run 36370497638](https://github.com/Le-Sponk/ct-studio/actions/runs/36370497638)
  passed Ubuntu and Windows. No Flatpak/Wine/tool execution is claimed.
  — commits 51ef73f, a1bda6b, d6513dc
- `P2-T01` — added typed immutable `ToolSpec` with a single 15-tool table covering
  Windows/Linux executable names, seven verified version probes, upstream URLs,
  licences and usage; unknown version floors are explicit rather than guessed.
  `CustomTool` validates `{file}`/`{dir}`/`{project}` templates and builds argv
  tokens without shell splitting, including Unicode/spaced paths. Ten tests cover
  IDs, URLs, regexes, argv and invalid placeholders. Windows `check.py` seven
  steps green (140 passed / 1 optional skip); broad non-network 213 passed /
  19 optional skips. [CI run 36356549228](https://github.com/Le-Sponk/ct-studio/actions/runs/36356549228)
  passed Ubuntu and Windows with artifacts. No real editor integration was
  claimed. See [TOOLS.md](docs/reference/TOOLS.md#p2-t01-registry-metadata-and-verified-version-probes).
  — commit 157fc62
- `P1-GATE` — independent fresh-context review recorded in
  [PHASE_01_REVIEW.md](docs/reviews/PHASE_01_REVIEW.md): no Must, three Should
  fixed with tests (per-package coverage enforcement, logging on GUI startup,
  atomic/no-clobber screenshot publication). Reviewer verified three scratch
  mutations and inspected Windows light/dark/150%/About screenshots.
  Post-fix Windows `check.py --all`: 130 passed / 1 optional skip, seven steps
  green; integration 71 passed / 6 optional skips; broad non-network 203 passed /
  19 optional skips. [CI run 36353987367](https://github.com/Le-Sponk/ct-studio/actions/runs/36353987367)
  passed Ubuntu and Windows with two artifacts. Linux Mint screenshot pixels
  remain optionally deferred; real-tool/network skips are not green integrations.
  No human checkpoint at Phase 1: HC1 follows Phase 5. — fixes 35fc071,
  gate tag `phase-01-done`
- `P1-T08` — added a truthful 13-line project description and developer quick start
  (`README.md`), short `CONTRIBUTING.md`, canonical verbatim GPLv3 `LICENSE`
  (matched GNU + mirror, SHA-256 in ADR-009), and a development inventory in
  `THIRD_PARTY_NOTICES.md` that does not assert external-tool redistribution rights.
  Expanded existing `docs/dev/BENCHMARKS.md` with baseline guidance and measured a
  second Windows 200 MiB hash at **0.397 s**; the Mint pass had no timing. Eight
  docs tests assert links, commands, dependency coverage, and exact legal text.
  `uv sync --locked`, `ctstudio --version`/`--help`, offscreen PNG, benchmark, Windows
  gate **125 passed / 1 optional skip** and full non-network suite **195 passed /
  19 optional-tool skips**. GitHub [run 36343094142](https://github.com/Le-Sponk/ct-studio/actions/runs/36343094142)
  succeeded on Ubuntu and Windows. The optional Mint screenshot inspection was
  deferred by the user and does not block the phase gate. — commit 65887f7
- `P1-T07` — cross-platform GitHub CI (`ci.yml`) with locked uv, Qt prerequisites,
  coverage and screenshot artifacts; scheduled/manual `integration.yml` selects network
  tests on both OSes. A JUnit reporter publishes exact selected-test skip reasons in logs,
  job summary and public annotations and fails instead of producing an empty green job
  (ADR-022). **Windows:** gate 117 passed / 1 optional skip; full non-network suite
  190 passed / 19 optional-tool skips; actionlint 1.7.12 clean. Main
  [run 36341555661](https://github.com/Le-Sponk/ct-studio/actions/runs/36341555661)
  passed on Ubuntu and Windows with both artifacts. A temporary branch-scoped
  [integration probe 36341608296](https://github.com/Le-Sponk/ct-studio/actions/runs/36341608296)
  ran pytest and uploaded JUnit on both OSes, then deliberately failed the reporter:
  public annotations state `wine not installed` for the selected test and a separate
  `moderngl not installed` collection skip. Probe branch removed; main retains
  nightly/manual triggers. First scheduled run has not yet occurred. See
  [remote evidence](tests/fakes/recordings/github-actions/p1-t07-remote.txt). — commit 14bc60b
- `P1-T06` — minimal Qt Widgets dashboard (no project yet), Help → About with package
  version, GPL-3.0-or-later and third-party-notices placeholder; native Qt palette reacts
  to light/dark changes. No-argument `ctstudio` launches GUI; `--offscreen-smoke <png>`
  forces offscreen, creates a valid PNG under a Unicode/spaced path and refuses to
  overwrite existing user work. `--version` and `--help` remain Qt-free (`-X importtime`
  showed no PySide6/shiboken6). Windows offscreen font database was empty, so ADR-021
  adds an installed-system-font fallback; first tofu screenshot replaced by readable
  light/dark/150% dashboard and light/dark About screenshots, inspected in
  `tests/artifacts/screens/`. **Windows evidence:** `uv run python scripts/check.py` exit 0:
  109 passed / 1 optional fixture skip / 92 deselected; pyright 0 errors, 3 import
  contracts, xenon/vulture green. Full non-network suite: 182 passed / 19 optional-tool
  skips / 1 network deselected. 7 focused GUI tests, screenshot CLI run, budgets, local
  links and `git diff --check` pass. Linux/CI offscreen fonts unverified until P1-T07.
  — commit aefa306

- `P1-T05` — OS/user-directory/sandbox probes, atomic app-managed writes, backed-up user
  replacements, resolved-path containment and lazy, cached, streamed BLAKE2b fingerprints.
  Tests cover Unicode/spaced paths, symlink escapes, failure preservation, unique backups,
  Windows concurrent writes (10 consecutive stress runs), stale hash detection and the
  metadata fast path. **Windows evidence:** `uv run python scripts/check.py` exit 0:
  102 passed / 1 optional fixture skip / 92 deselected, pyright 0 errors, 3 import
  contracts, xenon/vulture green. Full non-network, non-slow suite: 174 passed / 1
  optional moderngl skip / 20 deselected. 200 MiB streaming-hash benchmark:
  0.394 s, digest checked, Windows 11 / Python 3.12.14; see
  [BENCHMARKS.md](docs/dev/BENCHMARKS.md). 14 focused tests, function/file budgets,
  `git diff --check` and local doc links pass. Linux unverified until CI/Mint.
  — commit ba8aa1e

- `P1-T04` — `core/errors.py` adds `CTStudioError(user_message, hint, details)` and typed
  `ToolNotFound`, `ToolFailed`, `ProjectError`, `ManifestError`, `BuildError`, `Cancelled`,
  `ParseError`; `str(error)` shows an actionable next step but never raw stderr or private
  diagnostics. `core/logging.py` adds package-scoped `get_logger(__name__)` and
  `configure_logging()` with `platformdirs.user_log_dir("ctstudio")`, UTF-8 JSON-lines,
  UTC timestamps, 5 MB/3-backup rotation, optional CLI stderr, and safe reconfiguration
  that closes only CT Studio-owned handlers (Windows file handles). Xenon now **runs** on
  real core modules. **Windows evidence:** `uv run python scripts/check.py` exit 0,
  88 passed / 1 optional fixture skip / 91 deselected, 3 import contracts kept,
  pyright 0 errors, xenon + vulture green. Full suite `pytest -m "not network" tests`:
  160 passed / 19 optional-tool skips / 1 network deselected. 15 new errors/logging
  tests cover formatting, private details, Unicode paths, real JSON lines, rotation,
  console duplication and optional default path; `test_check` now asserts xenon wakes
  when core has implementation. 3/3 valid mutations caught (hint display, raw Unicode,
  rotation). Budgets and local doc links pass. Linux unverified until CI P1-T07 / Mint.
  — commit 72a4040
- `P1-T03` — Three import-linter 2.15 forbidden contracts: core↛GUI/CLI/PySide6,
  CLI↛GUI, application↛external `spikes`. Added importable `core`, `cli`, `gui` package
  markers (needed before the linter can evaluate them); no implementation moved from T04/T06.
  The gate's xenon step still says **SKIP** until core has actual modules. AST tests scan
  future `blender_bridge` sources for imports beyond stdlib/`bpy` and all app/scripts/tests
  imports for `spikes`. Gate child PATH now prefers its venv so pyright resolves packages
  when checking scratch trees. **Windows evidence:** `lint-imports --no-logo --no-cache`:
  3 kept / 0 broken, exit 0; `check.py`: 72 passed / 1 fixture skip / 91 deselected,
  0 pyright errors, exit 0; full suite: 144 passed / 19 optional-tool skips /
  1 network deselected. 12 architecture tests (seven forbidden import fixtures incl.
  relative and nested Qt, actual `check.py` rejection of `import PySide6` in core,
  Blender bridge/spike AST fixtures, repository scan) + gate PATH test; 5/5 contract/
  scanner mutations caught. `git diff --check`, budgets, and 24 local doc links pass.
  Linux unverified (CI P1-T07 or Mint). — commit 83f3184
- `P1-T02` — Real `scripts/check.py`: ruff format/check, pyright, import-linter, pytest
  (excludes `integration`, `slow`, `realdata`, `network`), xenon on core, vulture. Fail-fast by
  default, `--all` collects all failures, `--fast` skips pyright + coverage. Every step has
  duration, timeout, status and failure output; absolute venv tool paths + child `PYTHONPATH`
  support a different working tree. `pyright[nodejs]` ships Node in the dev venv (no global Node
  or network bootstrap). Folded `pytest.ini` and `ruff.toml` into `pyproject.toml` (strict marker
  registration; pyright strict on core), added root `.importlinter` (P1-T03 contracts) and an
  empty `vulture_whitelist.py` (moved from P1-T08). Xenon says **SKIP** until `core/` exists in
  P1-T04, not a false green; import-linter reports **0 contracts** until P1-T03.
  **Windows evidence:** `uv run python scripts/check.py`, `--fast`, and `--all`: exit 0;
  59 passed / 1 skipped / 91 deselected in default gate, 0 pyright errors; full suite
  `pytest -m "not network" tests`: 131 passed / 19 skipped / 1 deselected (same optional-tool
  skips as P1-T01: Dolphin, Xvfb/Wine, moderngl). 6 new gate tests cover broken sample,
  fail-fast, `--all`, `--fast`, timeout/missing tool and `network`+`integration` deselection. 3/3 mutations caught.
  `uv lock --check`, `ruff format --check`, `git diff --check` and 18 STATUS local links green.
  **Linux not run** — CI P1-T07 or Mint checkpoint. — commit 980bbd3
- `P1-T01` — `pyproject.toml` (src layout, `uv_build` backend, Python `>=3.12,<3.14`, entry point
  `ctstudio.__main__:main`), `.python-version` 3.12, committed universal `uv.lock` (51 packages:
  PySide6 6.11.2, numpy 2.5.3, Pillow 12.3.0, tomli-w 1.2.0, platformdirs 4.12.0, watchfiles 1.3.0
  + the ADR-010 dev group). Minimal stdlib-only `ctstudio/__main__.py` (`--version`; no args prints
  help until P1-T06). **ADR-020** covers `tomli-w`, `platformdirs` and the `uv_build` backend (rule 5).
  `.gitignore` gains dev-tool caches. Evidence (Windows 11, uv 0.12.19, CPython 3.12.14):
  `uv sync` exit 0 (≈23 s first time); `uv run ctstudio --version` → `ctstudio 0.1.0.dev0`, exit 0;
  fresh `uv sync --locked` in a path with a space **and** `é` → exit 0, same output; `uv lock
  --check` 0; ruff check/format 0; pyright on new code 0 errors; `git diff --check` 0. Full suite
  through the project venv: **125 passed, 19 skipped** (P0-T13 baseline 120/19 + 5 new tests); the
  skips are unchanged (Dolphin, Xvfb/Wine, moderngl). 3/3 mutations caught (eager Qt import,
  hard-coded version, wrong entry point). `pytest.ini`/`ruff.toml` intentionally stay until P1-T02
  folds them into `pyproject.toml`. **Linux not run** — see gaps. — commit dc97f92
- `P0-T13` — Re-bootstrap and re-verify on **native Windows 11**. `bootstrap_tools.py` now works
  on Windows from scratch (220 s; second run 0 s): ABMatt's Windows zip is an NSIS installer,
  now **expanded with a pinned 7-Zip 26.03, never executed**; RiiStudio's release zip is an
  optional tool (`--only riistudio`). New `scripts/tool_paths.py` gives spikes/tests one
  platform-aware tool path (`.exe`, absolute argv — Windows `CreateProcess` ignores `env` PATH).
  The fixture generator now also writes `course.kcl` (a fresh clone could not run S1/S3b/S5).
  Native results: **S1–S5 identical to Linux**; rszst's `exit(-1)` is **0xFFFFFFFF, not 255**
  (ABMatt too); **non-ASCII paths are a Windows-only failure class** — rszst refuses them (cwd +
  bare-name workaround measured), RiiStudio loads nothing silently, ABMatt crashes after writing.
  S7 native: all four editors open argv paths, **none single-instance (RiiStudio now measured)**,
  none registers a file association. `.gitattributes` LF (d194d80). HC1 now uses a fresh Mint
  clone (container workarounds demoted); HC2 has an explicit renamed-material warning item.
  120 passed / 19 skipped on Windows (Dolphin, Xvfb/Wine, moderngl absent); 5 new Windows path
  tests, 3/3 mutations caught. **Linux not re-run** (no machine/CI reachable) — see gaps.
- `P0-T12` — Phase 0 wrap-up **and gate**. Added ADR-017 (editors are launch-only) and
  ADR-018 (test launches use an extracted game folder); synced ARCHITECTURE §9; wrote the six
  HC0 questions with recommendations. **An independent fresh-context review found two
  surviving mutations**, both now fixed: ADR-018's "a bad DOL header boots as an executable"
  was **false** — the executable fallback is selected by an invalid `sys/boot.bin`, and a DOL
  with a zeroed entry point still boots as a disc — and the nine S2 tests were passing against
  a **stale gitignored findings file** (probe made unrunnable, still green in 0.02 s; S3b had
  the same trap). Also fixed: `pytest.mark.timeout` was inert project-wide (plugin never
  installed, 5 files had no mark), RiiStudio's "single instance" cell was never probed, the
  native-Windows rows over-claimed in a table headed "verified by real GUI launches", and S8's
  counts were wrong (13 tests, not 11; 5/6 mutations, not 6/6 — now genuinely 6/6).
  125 passing + 2 wine-skipped, excluding `network`. TD-002..TD-004 logged.
  [PHASE_00_REVIEW.md](docs/reviews/PHASE_00_REVIEW.md) — commit 53d432c
- `P0-T11` — Spike S8 (Dolphin test-launch options): both viable routes measured against a
  real Dolphin (`master 2503`), not its README. **Recommendation: the extracted game folder**
  — `--exec=<game>/sys/main.dol` boots as a disc and installing a build is a plain file copy
  over `files/Race/Course/<slot>.szs`. Traps: `--exec=<folder>` is rejected outright, and a
  half-extracted folder (short/missing `sys/boot.bin`) boots the DOL as a bare *executable* with
  no file system, which looks like success, so P11 must check the `Booting from disc:` log line
  rather than the exit code. Dolphin also
  has a **GUI-free Riivolution route** (its own `dolphin-game-mod-descriptor` JSON, `type`
  and `version` both enforced) — now P11-T02b, with one caveat that shapes the design: a
  patch whose XML is missing, malformed, or scoped to another game id **still boots, exit 0,
  silently**, so CT Studio must validate its own XML and never report "launched" as
  "patched". Also measured: `dolphin-emu --batch` does **not** fail cleanly on a missing file
  (it sits on a modal panic dialog), while `dolphin-emu-nogui` exits 1 with the message.
  MKW-SP "My Stuff" was not probed — it needs the MKW-SP distribution, so it stays a manual
  path. Fixture is synthetic: no MKW data exists here, so whether a patched slot actually
  loads is an HC3 item. 13 integration tests, 6/6 mutations caught.
  [SPIKES.md §S8](docs/dev/SPIKES.md#s8--getting-a-built-szs-into-a-running-game-p0-t11) — commit 754161f
- `P0-T10` — Spike S7 (external editor launch contracts): all five editors launched for
  real under Xvfb, four under Wine. **Every one opens a positional file path and none is
  single-instance**, so "Open in…" is one file and one process per launch — BrawlCrate's
  second argument is a *node path inside* the first file, Blender's replaces the first.
  Three traps: Lorenzi's editor has **no flag parsing** (an option before the path is
  opened as the file, silently showing `[New File]`); **a live process is not a loaded
  file** (RiiStudio kept an empty window up after failing on ABMatt's BRRES with the S3b
  U16 error, no dialog); and two of the five never name the file in the title. Wine is now
  measured: **win32 + dotnet48 + win10** for BrawlCrate/KMP Cloud, **win64** for RiiStudio
  and Lorenzi's Windows build. `course.kcl` auto-load confirmed by pixels.
  9 integration tests, 6/6 mutations caught.
  [SPIKES.md §S7](docs/dev/SPIKES.md#s7--external-editor-launch-contracts-p0-t10) — commit 1307833
- `P0-T09` — Spike S6 (preview rendering stack): **ADR-008 Accepted** — moderngl in a
  `QOpenGLWidget` works; headless GL is 4.5 core, a 200k-triangle VBO is 13.7 MB and
  uploads in <0.04 s. **`QT_QPA_PLATFORM=offscreen` cannot create a GL context at all**,
  so viewport tests need `xvfb-run` + `xcb` (TESTING_STRATEGY §5 and P9-T01 updated).
  ~10 fps on llvmpipe is a software-rasteriser floor, **not** a verdict on the §15
  budget — that needs real hardware at HC3. 6 integration tests, 4/4 mutations caught.
  [SPIKES.md §S6](docs/dev/SPIKES.md#s6--preview-rendering-stack-p0-t09) — commit 26a2c5e
- `P0-T08` — Spike S5 (headless minimap): KCL → `wkclt decode --kcl-script` filter →
  ABMatt is the recommended path for P8-T03; the add-on export is the Blender-authored
  alternative. **rszst cannot make minimap bones at all**, so ADR-004 gains a
  component-level exception. Key trap: ABMatt keys `posLD`/`posRU` off the **destination
  filename**, so an MDL0 named `map` is not evidence of a working minimap, and
  `wszst minimap` reports a boneless file only by printing nothing at exit 0.
  8 integration tests, 5/5 mutations caught.
  [SPIKES.md §S5](docs/dev/SPIKES.md#s5--headless-minimap-p0-t08) — commit c09be45
- `P0-T07` — Spike S4 (preserving external material edits): **ADR-012 Accepted** —
  capture with `rszst dump-presets`, reapply with `import-brres --preset-path`. All three
  candidate routes restore the edit, so failure modes decided it: ABMatt copy/paste
  **deletes the orphaned texture** on a renamed material at exit 0 and its `-a` flag
  cannot disable that in 1.3.2. Presets miss silently, so P7-T07 must report orphans
  itself. 10 integration tests, 5/5 mutations caught.
  [SPIKES.md §S4](docs/dev/SPIKES.md#s4--preserving-external-material-edits-p0-t07) — commit eae0ba3
- `P0-T06b` — Spike S3b (BRRES backend bake-off): **ADR-004 Accepted** — rszst imports,
  ABMatt post-processes, both platforms. Decided by a one-way interop wall: rszst cannot
  read an ABMatt BRRES. 14 integration tests, 4/4 mutations caught.
  [SPIKES.md §S3b](docs/dev/SPIKES.md#s3b-fixture-bake-off-and-backend-decision-p0-t06b) — commit 5f96d10
- `P0-T06a` — built RiiStudio Alpha 5.11.5 CLI on Linux without source patches;
  pinned build recipe, nine CLI recordings and ten integration tests. 68 tests pass,
  ruff clean, overwrite mutation caught. [SPIKES.md S3](docs/dev/SPIKES.md#s3-brres-backend-bake-off-p0-t06a--p0-t06b).
  Help and argument errors both exit 255; conversion/default decision stays in S3b.
  Overall redistribution licence unconfirmed. — commit 08bf2dd
- `P0-T05` — Spike S2 (headless Blender exports): add-on pinned as a submodule at
  v1.12.0; all six exports (KCL x2, DAE x2, OBJ, minimap BRRES) run headlessly via
  operators. [SPIKES.md §S2](docs/dev/SPIKES.md). 10 integration tests, 2/2 mutations
  caught. Minimap BRRES verified by `wszst minimap`. — commit 3a6a453
  **Follow-up (2026-09-19):** the two accepted wishlist items were implemented upstream
  and merged as add-on PR #1 (`ffa905f`); submodule pin bumped and P6-T01 rewritten to
  use the callable API. Also fixed five latent add-on defects — `os.popen` shell
  injection in KCL encoding, ABMatt exit codes ignored (stale BRRES republished),
  child collections skipped by active-collection minimap export, non-mesh objects
  counted in selection-only KCL, and the `blender -b` scripts exiting 0 on failure.
  Verified on Blender 4.2.23 LTS **and** 5.2.2 LTS.
- `P0-T04` — Spike S1 (Wiimms assemble & check): `spikes/s1_wszst.py` +
  [SPIKES.md §S1](docs/dev/SPIKES.md) + adapter command table in TOOLS.md.
  Found that `wszst check`'s exit code is not pass/fail and that `analyze --json`
  supersedes `slots`. 11 integration tests, 3/3 mutations caught. — commit 5688ad1
- `P0-T03` — synthetic fixture track: `scripts/fixtures/` generates two `.blend` variants,
  7 PNGs and a valid `course.kmp` in 0.85 s (budget 60 s), deterministically. Proved with
  the real tools: add-on exported 5 KCL objects / 292 triangles, `wkclt flags` confirmed
  all five flag types. 38 unit tests, 3/3 mutations caught. — commit 1d44633
- `P0-T02` — `scripts/bootstrap_tools.py` + `scripts/tool_catalogue.py` install Wiimms
  2.42a, Blender 5.2.2 LTS and ABMatt 1.3.2 into `.tools/` with checksum verification.
  Fresh run 55 s, second run 0.35 s no-op; 22 unit tests, 3/3 mutations caught.
  [TOOLS.md](docs/reference/TOOLS.md) — commit cbbb5f4
- `P0-T01` — environment audit: Debian 13.4 x86_64 container, root apt works, all four
  download origins reachable, Mesa llvmpipe gives GL 4.5 core via surfaceless EGL and
  Xvfb, no Python 3.12 yet. [ENVIRONMENT.md](docs/dev/ENVIRONMENT.md) — commit b69cc17

## Plan changes
- P5-T06c2 split into c2a (signal-only banner presentation) and c2b (mounting, joined results,
  uncertain-start recovery and full original GUI acceptance). Existing card/dashboard files
  are 368/396 lines; the remaining work exceeds one small task. No acceptance removed.
- P5-T06c split into c1 (joined requests) and c2 (card banner and results), preserving the
  full original watcher → card → Lock/Discard acceptance and screenshots in c2.
- 2026-11-11: P5-T06 split into P5-T06a (project watcher and live status refresh), P5-T06b
  (core Lock as manual / Discard with backup) and P5-T06c (the card banner). 174 tasks.
- 2026-11-11: P5-T05 split into P5-T05a (core issue report: grouping by part and severity,
  counts, issues.json loading, Copy report text) and P5-T05b (the dashboard panel). 172 tasks.
- 2026-11-10: P5-T04 split into P5-T04a (core assignment: checks, copy or reference,
  backups, manifest) and P5-T04b (card drop and Choose file… UI). Progress total grows by 2.
- `P5-T03e33` split into `P5-T03e33a` (trusted command events in core) and `P5-T03e33b` (Copy
  command in the live log); total planned tasks becomes 170.
- `P5-T03e34` added (user decision after e32): the dashboard follows the newest build output
  while the reader stays at its end. Done before e33; total planned tasks becomes 169.
- `P5-T03e3` split into `P5-T03e31` (bounded Qt log model), `P5-T03e32` (collapsible live
  dashboard view) and `P5-T03e33` (trusted structured command entries and safe exact copying).
  Existing LogLine events contain only step/text, not command provenance; ordinary output must
  not be mistaken for a command. This session completes e31 only; e32/e33 retain the remaining
  original acceptance, and the full existing disk log remains unchanged.
- `P5-T03e2` split into `P5-T03e21` (signal-only controls/progress view) and `P5-T03e22`
  (AppServices wiring, lifecycle guards and live cards) to keep each review bounded. These
  two numbered IDs are pieces of e2 and run before e3; no original acceptance is removed.
  e21 is deliberately not connected to the dashboard. This session completes e21 only.
- 2026-11-05: Split remaining T03e into T03e1 (safe build requests/worker ownership), T03e2
  (dashboard controls and live part progress) and T03e3 (bounded live log/command copying).
  Existing BuildController has no AppServices start guard, drops its thread before joining on
  completion and misses interrupt/startup failures. Prove that boundary before exposing buttons;
  the combined ownership/UI/log work exceeds one session. All original T03e scope is retained.
- 2026-11-05: T03g's project/settings checks, portable folder adapter and GUI launch ownership/
  controls exceed the session budget together. Keep T03g as the project-aware Blender service;
  add T03h for component-folder reveal and T03i for dashboard launch ownership/controls, before
  T03e build/log. No feature is dropped. The user's add-on fork is already the pinned submodule;
  its current upstream HEAD is the same `ffa905f`, so no dependency change is needed.
- 2026-11-04: P5-T03d's persistence, card controls and launch lifecycles exceed the session size
  budget together. Keep T03d as component-mode persistence; add T03f for dashboard mode/overflow
  controls and T03g for Blender/basic launch actions, before the unchanged T03e build/log task.
  File assignment and configurable editor mappings remain T04/T07. No feature is dropped.
- 2026-11-04: P5-T03c's persistence dialog and component/launch controls each need a separate
  service lifecycle and extensive failure tests. Keep slot/source editing as T03c; move actions
  to T03d and the unstarted build/log slice to T03e. No original feature is dropped.
- 2026-11-04: P5-T03b narrowed to the integrated live overview, refresh and path copying.
  Header editing and component actions exceed the session budget with card/status/navigation
  tests: P5-T03c now owns those controls; the unstarted build/log task moves to P5-T03d.
- 2026-11-04: P5-T03 split into P5-T03a (runner callback-error safety / TD-012),
  P5-T03b (dashboard header and component cards), P5-T03c (build controls and live log).
  Combined scope is larger than one session; the recorded safety prerequisite comes first.
- 2026-11-04: P5-T02 split into P5-T02a (new-project wizard) and P5-T02b (welcome screen
  and recent projects), each about 500 changed lines with tests.
- 2026-11-04: P5-T01 split into P5-T01a (services container, build controller) and P5-T01b
  (status service, UI stall watchdog): about 650 changed lines with tests, over one session.
- 2026-11-03: P4-GATE review deferred the `[build] extra_wszst_args` runtime support and
  `[hooks]` scripts to P7-T06. Both fields already parse into the manifest but the current
  build does not run them; PROJECT_FILE.md now says so. P7-T06 will validate options, pass
  them via the adapter, include them in the cache key and test hooks. The UI callback error
  / missing state.json case is tracked as TD-012 for the P5 Build page before it uses the
  runner. No Phase 4 exit criterion depends on these optional settings.
- 2026-11-03: P4-T07 split (about 700 lines in one go). P4-T07a = the core "build this
  project" (`core/build/project_build.py`: steps, tools, versions, auto-add library,
  `force`, `only`), shared later by the Build page. P4-T07b = `ctstudio build`, its human
  output, `--json-events` with the schema in `docs/dev/CLI.md`, Ctrl+C, exit codes and the
  CLI integration test.
- 2026-11-03: P4-T05b design notes. The object → file table is Wiimm's own (`wkmpt
  objects`), read at build time, not a table copied into CT Studio, so it stays as current
  as the pinned tools. The auto-add library is a per-computer user setting
  (`auto_add_library` in settings.json); nothing passes it to the build yet: P4-T07
  (`ctstudio build`) reads the setting, and P5 adds the Build page control. Object warnings
  are lost when the cache skips the assemble step (the runner keeps issues of steps that ran
  only); P4-T06 (validate node / issues.json) must keep them. [Done in P4-T06.] The dashboard Objects card
  still says "added automatically" whenever auto-add is on; P8-T07 makes it check the library.
- 2026-11-03: P4-T05 split. P4-T05a = assemble, `_d` copy and the `wszst list` post-check,
  never with auto-add. P4-T05b = the auto-add library setting and check, `--auto-add`, and
  the warning naming missing KMP objects (needs a KMP object → file table, a task of its own).
  Until P4-T05b the Objects card's "added automatically" is not yet true.
- 2026-11-03: P4-T04 deviation. Manual files are always copied, never hard-linked. The
  manifest has no setting to turn links on, and a hard link would let a later build step
  that edits a staged file in place write into the user's own file. Revisit in P13 if
  copying large files proves slow.
- 2026-11-03: P4-T03 split. P4-T03a = runner and events. P4-T03b = the per-build log file and
  the `state.json` update, which needs each step to name the part it makes.
- 2026-11-03: P4-T01 design deviation. Build inputs are plain paths (a folder means every file
  in it), not the phase file's `Input` class; steps are linked by matching outputs to inputs,
  and `from_manifest` takes a `make_part(spec, mode)` factory so P4-T04 to P4-T06 each add
  their own steps without changing the graph.
- 2026-11-02: P3-T05 (file-type sniffing) done before P3-T04 (status evaluation): P3-T04's
  `Manual` status needs "the file has the right magic bytes", which is what P3-T05 builds.
- 2026-11-01: P2-T08e split. P2-T08e = rszst/ABMatt Linux operation recordings and their
  comparison with Windows. P2-T08f = the rszst adapter test on Linux (through Wine) and the
  Linux non-ASCII path measurement written into TOOLS.md.
- 2026-11-01: P2-T08d split. P2-T08d = rszst through Wine in `tool_paths` and the rszst-using
  integration tests on Linux CI. P2-T08e = rszst/ABMatt Linux ops recordings, the native
  rszst adapter test and the Linux non-ASCII path measurement.
- 2026-11-01: P2-T08b split again. P2-T08b = Linux help/options/ops recordings for Wiimm
  and Blender from a CI recording job. P2-T08c = run the Windows-gated Wiimm/Blender
  integration tests and fakes on Linux using them. P2-T08d = `tool_paths.RSZST` through
  Wine on Linux (rszst + ABMatt ops recordings, rszst real-tool tests) and the Linux
  non-ASCII path measurement.
- 2026-11-01: P2-T08 split. P2-T08a = nightly integration workflow with tool bootstrap,
  fixtures and a strict expected-skips list. P2-T08b = Linux help/ops recordings from CI,
  Linux real-tool rszst tests (`tool_paths.RSZST` via the Wine route) and the Linux
  non-ASCII path measurement.
- 2026-11-01 (P2-T07): split. P2-T07a = user settings for tool paths + doctor honouring
  them (core/CLI); P2-T07b = the Tools page itself (list, chips, Browse…, Re-check off the
  UI thread, download page, pytest-qt + screenshot).
- 2026-10-31 (P2-T06d): split. P2-T06d = the Wine route's core (setup, discovery, doctor,
  adapter); P2-T06e = `ctstudio setup rszst --wine`, doctor's Linux fix text, the opt-in
  real-Wine integration test and the Mint run.
- 2026-10-31 (P2-T06c): the Wine + `rszst.exe` route passed its measurement (48/49 vs the
  Windows recordings) but offering it needs new code (a Linux `setup rszst --wine` choice,
  a Wine launcher for the rszst adapter with path conversion), so it is split out as
  P2-T06d. The native source build stays the Linux default route.
- 2026-10-30 (P2-T06b, CI): the Windows CI job failed once on a test that put a Windows
  drive path into a Linux-style PATH; fixed in 3e0095e.
- 2026-10-30 (P2-T06b): split into P2-T06b (setup routes, download, build runner, doctor)
  and P2-T06c (measure the Linux source build and Wine + `rszst.exe` on the Mint machine,
  then fix the recipe / enable the Wine route). Neither Linux route can run on this
  Windows machine.
- 2026-10-29: P2-T05g split. Editor launch stays P2-T05g; the Wine adapter (PE-architecture
  prefixes, `winepath -w`, `launcher=wine` in `open_in`) becomes P2-T05g2, because Wine is
  Linux-only and nothing about it can be measured on the Windows dev host.
<!-- Date · what changed · why (evidence link) · affected ADR/phase files -->
- 2026-10-29 (P2-T05e2): split into P2-T05e2 (ABMatt conversion + info parser) and
  P2-T05e3 (material edits + copy). Probes found unanchored regex selectors, silent
  texture loss and silently ignored keys (`drawpriority` not shown by info), each needing
  its own recordings and guards.
- 2026-10-29 (P2-T05e): split into P2-T05e (rszst adapter) and P2-T05e2 (ABMatt
  adapter). Probes found new rszst failure modes (any non-ASCII argv, missing textures at
  exit 0) that need their own recordings; both tools together exceed one session.
- 2026-10-28 (P2-T05c): split into P2-T05c (KMP text + image encoding) and P2-T05c2
  (KCL analysis + minimap). Image encoding alone needs eight measured formats, mipmap
  counts and TEX0 output verification; KCL tables and the silent minimap no-op need their
  own parsers. Phase 2 scope is unchanged.
- 2026-10-28 (P2-T05): split the seven-adapter scope into P2-T05a–g (Wiimm check,
  analyze/create, KCL/KMP/image/minimap, auto-add; rszst/ABMatt; Blender; editors/Wine).
  Its recorded-output parsing, library-content guard, Windows ANSI-path workaround and
  platform-specific launch contracts cannot fit one ~400-line session; each subtask has
  its own real/fake acceptance and both-OS CI. Phase 2 scope is unchanged.
- 2026-10-28 (P2-T04c): split into P2-T04c (rszst), P2-T04d (ABMatt) and P2-T04e (Blender),
  one tool per task. Measuring the three real tools on Windows found three unrelated
  behaviours (clap with -1 for help too; a frozen-Python script that exits 0 on "already
  exists"; Blender framing script output), and rszst first needs a DAE fixture.
- 2026-10-28 (P2-T04b): split again into P2-T04b (Wiimm fakes + real operation recordings +
  `fake_tools_path`) and P2-T04c (rszst/ABMatt/Blender fakes). Measuring the real tools
  showed per-tool error behaviour the fakes must copy (e.g. `wszst create` keeps an existing
  file but exits 0, `wkclt`/`wimgt` exit 64, `wkmpt` overwrites silently), which doubles
  the work per tool.
- 2026-10-28 (P2-T04): split into P2-T04a (real help recordings + flag contract checker)
  and P2-T04b (fake CLI scripts + `fake_tools_path`), because recordings for seven tools plus
  seven fakes exceed one session. The fakes in b reuse a's checker to reject unknown flags.
- 2026-09-28 (P2-T02): Discovery's concurrent version subprocesses precede
  P2-T03's sole permitted spawning adapter, violating AGENTS.md rule 3 and
  ARCHITECTURE §9. Split into P2-T02a (filesystem-only), P2-T03 (runner),
  P2-T02b (version probing + persistent path/mtime cache), keeping Phase 2
  user-visible scope. See ADR-023 and PHASE_02 task acceptance.
- 2026-09-28 (P1-T07): `pytest -m network` exited 0 with its only selected test skipped
  (`wine not installed`), plus an unrelated module-level collection skip. A plain scheduled
  pytest command would falsely report green. Added a JUnit-based job-summary reporter that
  names both reasons and fails for selected skips/zero selected tests; full tool/bootstrap
  coverage remains P2-T08. ADR-022 and PHASE_01 P1-T07 updated; local recording in
  `tests/fakes/recordings/github-actions/p1-t07-windows.txt`.

- 2026-09-28 (P1-T06): native Windows Qt 6.11 offscreen had zero font families and initially
  captured unreadable box glyphs despite a valid PNG. Added a system-font-only fallback for
  offscreen runs, visual light/dark/150% screenshot review, and Linux font availability to
  the P1-T07 CI check. See ADR-021, PHASE_01 P1-T06/T07 and TESTING_STRATEGY §5.

- 2026-09-27 (P1-T03): import-linter 2.15 **fails** with `Module 'ctstudio.core' does not
  exist` if a named source package is absent; a failed linter is not an enforced boundary.
  Created empty `core`, `cli`, `gui` package markers in P1-T03, before their planned code.
  Xenon itself exits 0 on an empty core, so `check.py` now explicitly skips until P1-T04
  adds an implementation module. The application↛external `spikes` contract needs
  `include_external_packages = True`; AST scan also checks scripts/tests, which sit outside
  import-linter's `ctstudio` graph. Pyright also needs the active venv at the front of the
  child PATH: in a copied tree without `.venv`, it otherwise picks a system Python and
  falsely reports PySide6 missing before import-linter runs. Docs: ARCHITECTURE §2,
  TESTING_STRATEGY, PHASE_01, TOOLS.md.
- 2026-09-27 (P1-T02): the pre-P1 `pytest.ini` and `ruff.toml` stand-ins moved to
  `pyproject.toml`; `vulture_whitelist.py` moved forward from P1-T08 because the real gate
  needs the path, but it contains no whitelist entries. `pyright[nodejs]` includes a Node
  wheel so CI needs no global Node and the gate cannot silently bootstrap one over the
  network. Xenon returns 0 on a missing path, so `check.py` must report an explicit SKIP
  until P1-T04 adds `core/`; import-linter reports 0 contracts until P1-T03.
- 2026-09-22 (HC0 answers): **Windows and Linux become equal targets (ADR-019)** — native Windows is
  the reference for the Windows editors, Wine is the Linux reference, and single-platform facts are
  tracked under "Platform verification gaps". Development moves to a Windows machine, so **P0-T13**
  is inserted before P1-T01 to re-bootstrap and redo S3 (Windows prebuilt `rszst`) and S7 (native
  editor launching). Three follow-ups became tasks: **P2-T06b** (how Linux users get `rszst`),
  the preset-coverage table under ADR-012, and **P11-T02c** (Wheel Wizard / Retro Rewind Patches as
  a test route). ADR-009 (GPL-3.0-or-later) is now Accepted. Affects ADR-009/012/019, PHASE_00,
  PHASE_02, PHASE_11, HUMAN_CHECKPOINTS.
- 2026-09-22 (P0 gate): **two Phase 0 claims were wrong and are corrected in place.** (1) The
  Dolphin executable-fallback is triggered by an invalid `sys/boot.bin`, **not** a bad DOL header —
  a DOL with a zeroed entry point still boots as a disc — so ADR-018, SPIKES §S8, PHASE_11 and the
  mutation harness now name the real cause. (2) `pytest.mark.timeout` was inert project-wide
  (`pytest-timeout` was never installed), so TESTING_STRATEGY's "every test file sets a timeout"
  was untrue; the plugin is now in every documented run command and the five unmarked files have
  marks. Both found by the independent review, not by me.
  Evidence: [PHASE_00_REVIEW.md](docs/reviews/PHASE_00_REVIEW.md).
  Affects ADR-018, ARCHITECTURE §9, SPIKES §S8, TOOLS, TESTING_STRATEGY, PHASE_00, PHASE_11.
- 2026-09-22 (S8): **"Build & launch" is the extracted game folder, and launching is not proof.**
  P11-T01 now names `dolphin-tool extract` + `<game>/sys/main.dol` explicitly (the folder itself is
  rejected), and P11-T02 must confirm `Booting from disc:` rather than an exit code, because a
  half-extracted folder boots the DOL as a bare executable with no file system. A GUI-free Riivolution route exists and
  became **P11-T02b**, gated on CT Studio validating its own XML: Dolphin skips an invalid patch
  silently at exit 0. `dolphin-emu --batch` is unusable for error detection (modal panic dialog);
  use `dolphin-emu-nogui`. MKW-SP "My Stuff" stays a documented manual path, not automation.
  Evidence: [SPIKES.md §S8](docs/dev/SPIKES.md#s8--getting-a-built-szs-into-a-running-game-p0-t11).
  Affects TOOLS, PHASE_11 (T01/T02/T02b) and HC3.
- 2026-09-22 (S7): **external editors are one-file, one-process, and cannot be asked whether they
  opened anything.** "Open in…" must never pass two paths (BrawlCrate's second argument selects a
  node *inside* the first file; Blender's replaces the first) and must not infer success from a live
  process or a window title. Lorenzi's editor parses no flags, so options must follow the path.
  Wine prefixes are dictated by executable architecture: win32 + dotnet48 + win10 for
  BrawlCrate/KMP Cloud, win64 for RiiStudio and Lorenzi's Windows build. Evidence:
  [SPIKES.md §S7](docs/dev/SPIKES.md#s7--external-editor-launch-contracts-p0-t10).
  Affects TOOLS, P2-T05 (`editors.py`/`wine.py`), P5-T07, ENVIRONMENT and HC1.
- 2026-09-22 (human auto-add recording): **auto-add does not gate P4.** Synthetic fixture builds
  omit it; `--auto-add` is opt-in and only emitted after a separate library usability check. Status
  output is path discovery, not health: absent, empty and populated paths all return 0 with the same
  basic lines. P2 must parse the reported `CURRENT AUTO-ADD PATH` / `SEARCH PATH[N]` grammar and the
  create form's 47 `ANALYZE YAZ0.U8:<path>` lines using fakes. P4-T05 must warn with the names of KMP
  objects missing from both the stage and library. The real end-to-end test is `realdata` at HC1.
  Affects TOOLS, P2-T05, P4-T05, TESTING_STRATEGY and HC1.
- 2026-09-21 (S6): **GL/preview tests cannot use `QT_QPA_PLATFORM=offscreen`** — it
  cannot create a GL context at all. They must run under `xvfb-run` with
  `QT_QPA_PLATFORM=xcb`; plain widget tests keep using offscreen. TESTING_STRATEGY §5,
  P9-T01 and ADR-008 updated. **AGENTS.md line 49 still says GUI tests run offscreen
  without this caveat — that file is yours to edit, see "Needs human".** Evidence:
  [SPIKES.md §S6](docs/dev/SPIKES.md).
- 2026-09-21 (S6): ARCHITECTURE §15's preview budget (≥60 fps at 200k tris) is
  **not measurable in this container**. llvmpipe gives ~10 fps, a software floor with no
  GPU; upload is ~0.03 s so the CPU path is not the constraint. Recorded as an HC3 item
  rather than treating the budget as met or missed.
- 2026-09-21 (S5): **ADR-004 gains a minimap exception** — that component uses ABMatt,
  not rszst, because rszst produces no `posLD`/`posRU` bones. P8-T03 rewritten with the
  verified recipe plus a mandatory post-conversion bone check (a boneless minimap is
  otherwise silent: `wszst minimap` prints no rows and exits 0). MKW_DOMAIN §5 corrected
  — it said "ABMatt creates the `map` bone automatically on import", but the bones
  actually key off the destination filename. Evidence: [SPIKES.md §S5](docs/dev/SPIKES.md).
- 2026-09-19 (S4): **ADR-012 names a concrete mechanism** (rszst presets) and explicitly
  rejects ABMatt copy/paste, which the plan had listed as an equal candidate. Evidence:
  its autofix silently deletes an orphaned texture and `-a`/`--auto-fix` is unusable in
  1.3.2. ARCHITECTURE §8, P7-T07 and HC2 updated; P7-T07 gains an explicit
  "diff captured presets against regenerated materials" requirement because no tool
  reports an unmatched preset.
- 2026-09-19: **P6-T01 rewritten** for the merged add-on export API (`ffa905f`). The
  bridge now calls `export_kcl` / `export_collada` / `export_minimap_brres` and reads
  counts from the returned dictionary; the planned stdout parsing and the pre-flight
  ABMatt / material checks are dropped, because the add-on returns a typed reason.
  `export_scene.objkcl` still goes through `bpy.ops` (no extracted form). Evidence:
  [SPIKES.md §S2 wishlist](docs/dev/SPIKES.md), TOOLS.md "Callable export API".
  Affects PHASE_06, TOOLS.md, SPIKES.md, submodule pin.
- 2026-09-19: Blender **4.2.23 LTS** added to `scripts/tool_catalogue.py` as an optional
  tool (`--only blender-4.2`). It is the add-on manifest's declared floor, so
  compatibility runs need it reproducibly rather than by hand. Published checksum
  verified on download.
- P0-T06 split under the task-loop size rule: P0-T06a obtains/probes the CLI;
  P0-T06b runs the fixture bake-off and decides ADR-004. The six-hour total is unchanged.
  Native build troubleshooting plus both backends' material/JSON round-trips is too
  large for one bounded change. No backend recommendation is inferred from CLI help.
- 2026-09-17: ADR-016 adds the pre-P1-T02 evidence gate because the mandatory script
  does not exist yet (real invocation exited 2). Evidence: ENVIRONMENT.md, quality gate
  section. Phase 0, WORKFLOW and AGENTS rule 6 now reference this bounded exception.
- 2026-09-17: human rewrote AGENTS rule 3 — `subprocess` is confined to
  `core/tools/process.py` inside `src/ctstudio/`, while `scripts/`, `spikes/` and
  `tests/` may spawn processes directly with argv lists, explicit timeouts and exit-code
  handling; never `shell=True`; spike code is never copied into `src/`. P0-T02 onward
  follows this. No ADR needed (it tightens the wording of an existing accepted rule).
- 2026-09-17: name settled as **CT Studio** (ADR-015 now Accepted). Docs renamed:
  package/CLI `trackstudio` → `ctstudio`, manifest `ctstudio.toml`, app folder
  `.ts/` → `.ctstudio/`, `TRACKSTUDIO_DEV` → `CTSTUDIO_DEV`, `TrackStudioError` →
  `CTStudioError`. Done before any code exists, so P1-T01 writes the new names directly.
- 2026-09-17: **Lorenzi's KMP Editor has no Linux build** — only a Windows `.exe` and a
  macOS arm64 zip, in every release back to v0.7.0 (GitHub releases API). P0-T02 planned
  to install it; it now isn't installed at all and P0-T10 must drive it through Wine like
  BrawlCrate. Affects P0-T02/P0-T10 and the Linux launch contract in TOOLS.md.
- 2026-09-17: bootstrap installs **3 tools, not 5**. uv itself is already present and
  Python 3.12 comes from `uv python install 3.12` (3.12.13, ~4 s), so neither needs a
  catalogue entry. Recorded in TOOLS.md; P0-T02 wording updated.
- 2026-09-18: fixture KMP is complete **except the `[CAME]` opening camera**, which needs
  the four-lines-per-camera layout; compiling therefore reports 2 expected camera warnings
  (asserted by the generator and a test, so a third warning fails the build). P0-T03 allowed
  this deferral; the note landed on **P10-T01**, not P10-T05, because P10-T05 is about
  editor round-trips while P10-T01 is where KMP sections are actually handled.
- 2026-09-18: added `pytest.ini` (marker registry from TESTING_STRATEGY §1) and extended
  `ruff.toml`, both pre-P1 stand-ins that P1-T01/P1-T02 fold into `pyproject.toml`.
- 2026-09-18 (S1): **`wszst check` exit codes are not a pass/fail signal** — valid track,
  warning-laden track and empty archive all exit 2 (`DIFFER`), but a corrupt file exits
  **0** while printing `ERROR #39`. The adapter must parse output and treat `ERROR #` as
  failure. Affects P2-T05 (`wiimm.py`) and P4-T06 (validate node); both updated.
- 2026-09-18 (S1): `check --sections` and `slots --sections` are rejected; **only
  `analyze` is machine-readable** (`--json`/`--sections`). `analyze --json` carries
  `slot_info`, `lap_count`, `n_ckpt0`, coordinate ranges and per-component SHA1s, so
  `slots()` is dropped from the P2-T05 adapter surface in favour of `analyze()`.
- 2026-09-18 (S1): `wszst create` never validates (it builds from an empty directory),
  and `--auto-add` is a **silent no-op** without a library. The app must guard both.
- 2026-09-18 (S2): **calling the add-on's operators is enough** — no context juggling
  needed headless, so the P6 bridge does not need internal-function access. ARCHITECTURE
  §12 and P6-T01 updated with the confirmed entry points.
- 2026-09-18 (S2): `export.minimap` reports a **missing ABMatt as `poll() failed, context
  is incorrect`**, which points at the wrong cause, and it refuses meshes without
  materials. The bridge must check both itself. This also **changed the P0-T03 fixture**:
  KCL meshes now carry a material (collision has no appearance; it is purely for ABMatt).
- 2026-09-18 (S2): `daeExportMethod=AUTO` equals `BUILTIN` on Linux because the bundled
  FbxConverter is a Windows binary. **DAE bytes will differ on Windows CI** — no
  cross-OS byte-comparison tests.
- 2026-09-18 (S3b): **rszst cannot read an ABMatt BRRES** (`Invalid quantization for
  normal data: U16`, exit 255) while ABMatt reads rszst output fine. This one-way wall,
  not a preference, fixes the pipeline order in ADR-004 (now Accepted) and is recorded
  in P7-T01.
- 2026-09-18 (S3b): **`set_texture_formats` is dropped from the ABMatt backend** —
  `set tex0 format:` exits 0 and changes nothing. ADR-004's interface list and P7-T01
  updated; the operation must raise the typed unsupported error instead.
- 2026-09-18 (S3b): ABMatt takes the MDL0 name from the **source filename stem** (no
  flag) and rejects a `<slot>_model.brres` destination that disagrees; `abmatt -c`
  mangles multi-word commands, so command files (`-f`) are the supported route.

## Human checkpoint results
### HC0 — answered 2026-09-22
1. **Licence:** GPL-3.0-or-later **approved** → ADR-009 Accepted; `LICENSE` lands in P1-T08.
2. **GitHub Actions enabled, direct push allowed** → P1-T07 is unblocked, Windows CI is real.
3. **Host visibility:** the workspace is at `~/.hermes/sandboxes/docker/default/workspace` on Mint.
   HC1 now carries host run instructions using a **separate** `UV_PROJECT_ENVIRONMENT`
   (`~/.venvs/ctstudio-host`) so the container's `.venv` is not clobbered. **Found and fixed a real
   blocker:** 303 tracked files and `.git/index` were root-owned, which would have broken `git` on
   the host — the tree is now `chown`ed to uid 1000, and every future session must end the same way.
4. **Real track files in `local_fixtures/`:** not for now. Synthetic fixtures stay the default;
   `realdata` tests remain opt-in.
5. **Platform parity:** Windows and Linux are **equal targets** → **ADR-019**. Native Windows is the
   reference for the Windows editors (the human runs BrawlCrate natively); Wine is the reference on
   Linux. Single-platform facts are flagged under "Platform verification gaps" below.
6. **Spike scope changes approved**, with three follow-ups, all now planned:
   - *How do Linux users get `rszst`?* → **P2-T06b**: detect → Windows/macOS guided download →
     Linux source build (pinned S3a recipe, visible cancellable job) → Wine fallback (unverified,
     must be measured first) → honest degradation. No redistribution (licence unconfirmed).
   - *What does preset capture preserve?* → table in DECISIONS.md under ADR-012. `.rspreset` is a
     **binary BRRES fragment** (`bres`/`MDL0`/`TEX0`), so coverage is probably broad, but only
     xlu/blend/cull/one SRT0 are **measured**; TEV, indirect, multi-layer, PAT0/CLR0 and
     LightSet/FogSet are **unverified** until HC2. A **renamed material loses its capture
     silently** — measured, and the reason P7-T07 must diff preset names.
   - *Wheel Wizard as a test route?* → **P11-T02c**, alongside (not instead of) the extracted-folder
     route. Retro Rewind uses the **Patches** loose-file system (supersedes My Stuff), matched by
     base name — but **Retro Rewind renames tracks**, so a vanilla slot name may silently do
     nothing, and Patches can be disabled in-game with no error. Both are "looks fine, track
     absent" failures.
7. **Moving to a dedicated Windows machine with native Hermes before P1** → **P0-T13** runs first on
   the new machine: re-bootstrap, redo **S3** (Windows `rszst` prebuilt — no 55 min source build)
   and **S7** (native editor launching, plus the single-instance probe S7 never ran), update the
   decisions. Linux stays fully supported via CI and Mint checkpoints; the Wine evidence is kept as
   the Linux reference, not deleted.

## Platform verification gaps (ADR-019)
<!-- Fact · verified on · missing on · who closes it -->
- **P5-T03e32 native desktop appearance.** Local readable light/dark/native/150%-font log
  screenshots and full-cap native Qt behavior tested offscreen on Windows; actual visible Mint
  desktop, native theme and OS-DPI rendering remain unverified. Ubuntu runtime CI is required
  before closeout but does not establish desktop pixels. Nonblocking; no user run requested.
- **P5-T03e22 native desktop appearance.** Windows/Ubuntu headless tests and local readable
  light/dark/150%-font screenshots pass, including the Ubuntu-width regression. These do not
  establish a visible Mint desktop, native theme or actual OS-DPI scaling. This is nonblocking;
  no additional user run is requested for the dashboard-wiring step.
- **P5-T03h Linux file-manager display.** Native Windows Explorer opened the exact scratch
  folder through the adapter. Linux CI measures actual xdg-open dispatch to an isolated
  synthetic XFCE helper, not a Mint/Cinnamon window, desktop association or late rejection.
  A receipt only means dispatch. A future desktop spot-check can close the visible-window
  gap when T03i adds the action; no user run is required for this blocking-service step.
Updated by P1-T07. Automated P1-T01–T06 Linux parity passed in
[Ubuntu CI run 36341555661](https://github.com/Le-Sponk/ct-studio/actions/runs/36341555661):
`uv sync --locked`, seven-step `check.py` (including all three import contracts, GUI,
errors/logging, filesystem tests), coverage and screenshot artifact uploads succeeded.
The human also ran `uv sync`, `ctstudio --version` and the broader non-network suite
on Mint (Python 3.12.3 / Qt 6.11.2): **141 passed, 60 optional-tool skips, 1 network
deselection**, including all seven GUI tests and the 200 MiB hash benchmark. Those
numbers are for the pre-P1-T07 checkout; CI covers the P1-T07 tests and workflow.
- **P2-T06 doctor on Linux with real tools.** Windows real-tool output is measured
  (`tests/integration/test_doctor_real.py`, 2 passed); Linux runs only fake trees in CI.
  Partly closed in P2-T06c: `ctstudio doctor` on Mint found Wiimm 2.42a ×4 in
  `/usr/local/bin`, the built rszst 5.11.5, Wine and winetricks, reported Flatpak Blender as
  sandboxed, exit 0. Still open: `test_doctor_real.py` with a bootstrapped `.tools/` and the
  Wine editor rows.
- **P2-T05a–d Wiimm check/analyze/create/KMP/image/KCL/minimap/auto-add evidence is Windows-only.** The adapters' real
  SZS/stage-directory/empty/corrupt/missing integration tests ran against native Windows
  Wiimm 2.42a; Ubuntu CI exercises only the recorded parser and the prefix-only fake
  (which the adapter must refuse). To close: on Linux bootstrap Wiimm and fixtures, run
  `uv run python scripts/record_tool_outputs.py --only wiimms-szs-tools`, commit the
  `linux-ops.json` files and run `tests/integration/test_wiimm_adapter.py` and
  `test_wiimm_convert_adapter.py`/`test_wiimm_kcl_adapter.py`/`test_wiimm_autoadd_adapter.py` with their `os.name` skips relaxed to accept Linux. Nonblocking for the Windows-derived contract.
- **P2-T04e Blender operation recordings are Windows-only.** Sixteen Blender 5.2.2
  invocations exercise the pinned scripts and known-good `.blend`. Ubuntu CI replays
  Windows diagnostics with deliberate path-separator translation through the no-`bpy`
  executable fake; it does not verify real Linux Blender's Python embedding, output,
  GPU/headless setup or file loading. To close: bootstrap Blender 5.2.2 and fixtures
  on Linux, then run `uv run python scripts/record_tool_outputs.py --only blender`,
  commit `linux-ops.json` and adjust `test_fake_blender.py` to replay the native Linux
  evidence (including `--python-exit-code` and `.blend`). This is nonblocking for the
  fake's Windows-derived contract.
- **P1-T06 screenshot pixels:** Linux Qt GUI tests assert an installed font family and
  generate screenshots; CI uploaded them, but their pixels were not downloaded for visual
  inspection. Human Mint spot-check remains: `git pull && uv run ctstudio --offscreen-smoke
  /tmp/ctstudio-smoke.png`, then open the PNG and report whether text is readable.
  ADR-021 documents Windows' empty offscreen font database, not a Linux issue.
- **P1-T05 performance/platform detail:** the 200 MiB benchmark completed on Mint, but
  its elapsed time was not in the report; sandbox detection outside the unit fakes was
  not exercised on Linux. These are not P1-T07 CI acceptance blockers.

- **P2-T04d ABMatt operation recordings are Windows-only.** The 1.3.2 Windows binary's
  banner differs from the same-tag Linux build (which reports 1.3.1); neither Linux
  help nor real operations have been captured. Ubuntu CI replays Windows outputs
  through the executable fake with LF/status translation, but that does not verify Linux
  ABMatt's timing, diagnostics or file effects. To close: on Linux bootstrap the pinned
  ABMatt and fixtures, run `uv run python scripts/record_tool_help.py` and
  `uv run python scripts/record_tool_outputs.py --only abmatt`, commit the Linux
  recordings, and update the replay to use them. Nonblocking for this Windows-pinned task.

- **P2-T05g/g2 editor launches.** Native Windows evidence is Windows 11 only. The Linux side
  is now measured on one machine (Mint 22.3 Cinnamon X11, Wine 9.0 Ubuntu): RiiStudio,
  Lorenzi and BrawlCrate (win32 + dotnet48) start through `open_in` on a `dossier é 日本`
  path, and the wrong-prefix / missing-.NET errors are real (`test_wine_editors.py`, 5 passed).
  Still unmeasured: KMP Cloud under Wine, other Wine versions/distros, Wayland sessions, and
  Linux-native Blender through `open_in`.
- **P2-T05f Blender script adapter evidence is Windows-only.** Flag order, exit codes and
  the unreadable-`.blend` report are measured on Windows 5.2.2; Flatpak Blender is refused,
  not run. Closing it: on Linux record the `BLENDER_ADAPTER_CASES` rows and run
  `tests/integration/test_blender_adapter_native.py`; verify Flatpak path access before
  allowing it.
- **P2-T05e3 ABMatt material edit/paste evidence is Windows-only.** Selector semantics,
  the silent no-op edit and paste's texture removal are measured on the Windows 1.3.2
  binary. Closing it: record the P2-T05e3 rows of `ABMATT_ADAPTER_CASES` on Linux and run
  `tests/integration/test_abmatt_edit_native.py` there with the skip lifted.
- **P2-T05e2 ABMatt conversion adapter evidence is Windows-only.** The CJK print crash,
  texture-loss texts and staging names are measured on the Windows 1.3.2 binary only (its
  banner says 1.3.2, the Linux build 1.3.1). Closing it: record `ABMATT_ADAPTER_CASES`
  on Linux and run `tests/integration/test_abmatt_adapter_native.py` there with the
  skip lifted.
- **P2-T05e rszst adapter evidence is Windows-only.** The ASCII staging, texture and
  preset refusals are proven against the Windows build (non-ASCII argv mangled through the
  ANSI code page; missing textures replaced by a 32x32 placeholder at exit 0). The Linux
  build may accept UTF-8 argv; staging stays because it is harmless there. Closing it: on
  Linux, run `tests/integration/test_riistudio_adapter_native.py` with the skip lifted and
  record the adapter cases in `linux-ops.json`.
- **P2-T04c rszst operation recordings are Windows-only.** Ubuntu CI exercises the
  fake's Linux executable and compares the Windows runs after translating the independently
  verified help/version differences and the runner's LF progress-line normalization.
  That does not prove the Linux real converter's progress or file effects. Closing it:
  on a Linux checkout with the pinned source-built rszst 5.11.5 and generated fixtures,
  run `uv run python scripts/record_tool_outputs.py --only riistudio` and commit
  `linux-ops.json`; then make `test_fake_rszst.py` replay the native recording. No
  Mint action needed for this task.
- **P2-T04b operation recordings are Windows-only.** The Linux fakes replay the Windows runs
  of Wiimm 2.42a (path display differs: the Cygwin build prints `/` for `\`). Closing it:
  on Linux run `scripts/record_tool_outputs.py` after bootstrap + fixtures, commit
  `linux-ops.json`, and make `test_fake_wiimm.py` replay it (it loads `windows-ops.json` today).
- **P2-T04a help recordings are Windows-only** (except rszst, recorded on both). Linux
  builds of Wiimm 2.42a, ABMatt 1.3.2 and Blender 5.2.2 may list different flags; the
  contract assumes they match. Closes when someone runs `uv run python
  scripts/record_tool_help.py` on a Linux checkout with bootstrapped tools (Mint spot-check
  or P2-T08 CI) and commits the resulting `linux-help.json` files.

- **P0-T13 changes on Linux — mostly closed.** Human ran a fresh clone on Mint 2026-09-27
  (Python 3.12.3, repo path containing a space): bootstrap, fixture generation (incl. the new
  `course.kcl` export) and tests → **79 passed, 60 skipped, 0 failed**. Skips: 36 need `rszst`,
  which a fresh Linux clone does not have (S3a source build, not bootstrapped); 13 Dolphin; 5
  Xvfb/Wine; 5 Windows-only paths; 1 moderngl. **Still unexercised on Linux since P0-T13:** the
  36 rszst tests (their only changes are the shared path and exit constants, which resolve to
  the same values as before on Linux). P1-T07's quality CI does not install rszst;
  this closes when anyone builds it on Linux (S3a recipe) or the P2-T08 tool bootstrap
  runs these real-tool tests.
- **Non-ASCII paths**: Windows measured (rszst/RiiStudio fail, ABMatt partial, Wiimms/BrawlCrate/
  Lorenzi fine). Linux/Wine unmeasured. P2-T08 or HC1.
- **Editor file-association / double-click launch**: nothing registered on this Windows machine;
  untested on both. HC1.
- **Editor save behaviour** (Lorenzi, BrawlCrate): neither platform. HC1.
- **BrawlCrate model preview**: **works natively on Windows** (human, 2026-09-27, on a real
  track's `course_model.brres`); Linux/Wine not working under llvmpipe, real GPU untested. HC1.
- **Lorenzi `course.kcl` auto-load, KMP Cloud tree pane**: Wine pixels only; native not captured.
- **S7 Wine contracts** (Linux): unchanged since P0-T10, not re-run (container not used).
- **Dolphin launch routes (S8)**: Linux only; Windows Dolphin not installed. HC3 / P11.
- **Preview stack (S6)**: llvmpipe only; no GPU measurement on either platform. HC3.
- **`rszst` on Linux**: source build (S3a), unchanged. Windows prebuilt verified (P0-T13).
- Closed by P0-T13: Windows bootstrap, Windows S1–S5, native editor argv/single-instance
  (incl. RiiStudio's first real single-instance measurement).

## Needs human — BLOCKING
<!-- Question · options · agent's recommendation · what is blocked -->
_none_ — GitHub `workflow` permission fixed; P1-T07 workflows pushed 2026-09-28.

## Needs human — non-blocking
<!-- Answered 2026-09-27: BrawlCrate preview renders natively on Windows (recorded in gaps and
TOOLS.md); non-ASCII plan approved — rszst adapter always uses cwd + bare names, and "Open in
RiiStudio" warns before launching on a non-ASCII path (PHASE_02 P2-T05/P2-T08). -->
- **Nightly `Integration` is green (P2-T08a, run on f765eaa).** On Linux 84 tests still skip
  for listed reasons, mostly Windows-only recordings and rszst through `tool_paths`; P2-T08b
  shrinks that list. Both workflows warn that `actions/*@v4` target deprecated Node 20 and
  that `ubuntu-latest` moves to Ubuntu 26; neither has failed a job yet.
- **Optional Mint GUI pixel spot-check — deferred by the human:** CI verified Linux
  font families and screenshot generation, but its pixels were not inspected.
  When convenient, `git pull && uv sync && uv run ctstudio --offscreen-smoke
  /tmp/ctstudio-p1t07.png`; open the PNG and report whether the text is readable.
  Choose a new output name if it exists. Do not prompt again until the human
  volunteers the result; this is not a phase gate.
- ~~RiiStudio licence / bundling~~ **answered 2026-09-18: never bundle it.** Ship
  detection + a link to the official releases page + an optional user-initiated
  download from the upstream URL; keep it out of the installer. Asking the maintainer
  for an explicit LICENSE is a **Phase 12** question, not a blocker. Recorded in
  ADR-004 and P12-T01/T03.
- ~~S2 add-on wishlist~~ **answered and closed 2026-09-19.** (1) minimap poll message and
  (2) callable export functions returning result dictionaries: both **merged** as add-on
  PR #1 (`ffa905f`); the submodule pin is updated and P6-T01 now specifies the callable
  API with no stdout scraping. (3) a module-name-safe package directory: **declined**;
  the bridge keeps the copy-to-`mkw_utilities` step.
- ~~Auto-add library/output~~ **answered 2026-09-22.** The user's library is built and working.
  `wszst autoadd <Race/Course dir>` emits 47 `ANALYZE YAZ0.U8:<path>` lines and no summary;
  status emits current/search paths but no health/count signal. P2 parser/fakes and P4's optional
  behavior are now specified; the real end-to-end test is `realdata` at HC1. Not a P4 gate.
- **One-line AGENTS.md edit for you** (I am not permitted to write that file): line 49
  reads "GUI tests run headless with `QT_QPA_PLATFORM=offscreen`". S6 proved that is
  false for GL/preview tests — offscreen cannot create a GL context. Suggested wording:
  "GUI tests run headless with `QT_QPA_PLATFORM=offscreen`; GL/preview tests instead need
  `xvfb-run` + `QT_QPA_PLATFORM=xcb` (offscreen cannot create a GL context — S6)".
  Not blocking: TESTING_STRATEGY §5, ADR-008 and P9-T01 all carry the correct rule.
- **S7 editor unknowns for HC1** (added 2026-09-22, nothing to answer now — they need your
  machines): ~~native-Windows launch behaviour~~ and ~~non-ASCII paths on Windows~~ (measured
  in P0-T13); whether a file-association launch differs from an argv one (no editor registers
  one here); non-ASCII paths on Linux; how Lorenzi's editor and BrawlCrate
  **save** (in place, temp+rename, or backup?), which P5-T06's change detection depends on;
  and whether BrawlCrate's model preview works in your setup. Listed as HC1 step 9.
- **S8 game-file unknowns for HC3** (added 2026-09-22, nothing to answer now — they need your
  own game copy): whether an installed SZS actually loads (a `Booting from disc:` line proves the
  disc mounted, not that your track is in it); whether a Riivolution-route patch really lands,
  given Dolphin skips a broken one at exit 0 in silence; real `dolphin-tool extract` time and disk
  use; and whether you use MKW-SP, which would make "My Stuff" worth automating rather than
  documenting. Listed as HC3 step 6.

## Tech debt
- **TD-001 · P5-T07/editor-launch adapter · RiiStudio load output has an undeclared network
  precondition.** `File: <path>` appears only after RiiStudio's mandatory GitHub update check
  completes; when the endpoint is unreachable the line never appears. Upstream Alpha-5.11.5 has no
  usable disable switch: `UpdaterView` constructs `Updater` unconditionally; the unused
  `setCheckUpdate(false)` would suppress only drawing, not the request; no flag/env/config/build
  define exists. The adapter must report only "launched" and never consume this line as proof.
  `test_riistudio_reports_the_file_it_opened_only_on_a_tty` now carries `network` and precisely
  skips if `https://api.github.com/repos/riidefi/RiiStudio/releases/latest` is unreachable;
  `check.py` must exclude `network` (P1-T02), nightly integration must include it (P1-T07). The
  no-tty observability question remains HC1.
- **TD-002 · P8-T03/minimap · the KCL filter fixture exercises 2 of its 7 conditions.** The
  drivable-surface filter removes types 0x0c, 0x0d, 0x0f, 0x10, 0x14, 0x1e, 0x1f, but the synthetic
  fixture contains only 0x00, 0x03, 0x06, 0x0c, 0x10 — so deleting `t == 0x1f` survives while
  deleting `t == 0x0c` is caught (the logic is right, the fixture is thin). P8-T03 must extend the
  P0-T03 generator to emit one triangle of each filtered type, and move the filter script to a
  single shared file: it is currently duplicated verbatim between `spikes/s5_minimap.py` and
  `tests/integration/test_minimap_paths.py` with only a comment holding them in step.
- **TD-003 · P2/P9 · spike-script tests assert on source text, not behaviour.**
  `test_the_spike_script_is_runnable_and_self_describing` (in `test_editor_launch.py` and
  `test_preview_stack.py`) greps the spike source for identifiers; it passes on a completely broken
  script and its name overpromises. Rename to `..._still_parses` and use `ast.parse`, or delete
  them — spikes are throwaway per AGENTS.md rule 3. Same visit should revisit the fixed
  `SETTLE = 14.0` sleeps, which exist only because Wine GUIs give no readiness signal.
- **TD-004 · P1 docs pass · TOOLS.md marker convention has four spellings.** The header defines
  `[doc]`/`[unverified]`/`[verified vX, run]`, but the file also uses `[verified S7]`,
  `[verified S8, run]`, `[verified S7 + source …]`, `[verified S7 + IL of …]`, and there is no
  marker for "read the source at a pinned tag" — which is how several of the strongest claims were
  established. Define `[run S<n>]`, `[source <file>@<tag>]`, `[doc]` and apply them uniformly so
  the next phase review can grep instead of read.
- **TD-005 · P5-T01 · closing the Tools page can wait for a running check.** Its
  `QThreadPool(self)` is waited for when the page is deleted, so closing the dialog during a
  forced Re-check can block for up to the probe timeout (10 s). P5-T01 (GUI services and
  threading) should give version probes a `CancelToken` and cancel/clear on close. Found in
  the P2-GATE review (Consider).
- **TD-006 · P13-T07 · GitHub Actions pinned by tag; Node 20 deprecation warnings.** `ci.yml`,
  `integration.yml`, `record-linux.yml` use `actions/checkout@v4`, `cache@v4`,
  `upload-artifact@v4`, `astral-sh/setup-uv@v7`. Pin each by commit SHA and move to the Node 24
  releases in the security review. Permissions are already least-privilege. (P2-GATE.)
- **TD-007 · P5-T09 · Tools page screenshots are small.** Only 900×520 with a 3-tool stub;
  add 1280×720 with the full registry and one at 150 % scaling in the GUI screenshot review
  (REVIEW_CHECKLIST 5). (P2-GATE.)
- **TD-008 · Deep Clean #1 · two gate scripts at complexity C.** `scripts/bootstrap_tools.py`
  `unpack` and `scripts/check.py` `run_step` are C(12); xenon only gates `core`. Split them in
  the next Deep Clean. (P2-GATE; pre-existing.)

- **TD-009 · P5-T01 · start-failure edges from the P2-GATE verification.** (a) A command line
  too long for Windows (error 206) arrives as `FileNotFoundError` and reads "… was not found";
  check for 206/E2BIG first. (b) The Tools page test for a non-program set path uses a fake
  doctor; add one that runs the real `diagnose` limited to Blender with a scratch cache.
  (c) doctor's `not_working` fix for a *set* path could say "choose another file or Clear".
- **TD-010 · P5-T01 · `test_launch_watch` still flaky on Windows under full-suite load.**
  On 2026-11-02 (`check.py --fast`, docs-only change on 54b5937) the detached child of
  `test_a_launch_still_running_after_the_watch_returns_its_pid` never wrote `opened.txt`
  within 4 s + 12 s; the file passed 5/5 alone right after. Not the clock bound fixed in
  P2-T08d: find whether the child is slow to start or ended early (log its pid/exit), then
  make the test wait on a signal, not a sleep.
- **TD-011 · P13-T02 · `ctstudio status` start-up.** P3-GATE measured a whole `status --json`
  run at ~400 ms on this workstation: ~110 ms Python start, ~210 ms imports (`ctstudio.cli`
  imports `cli.doctor` and so `core.tools.doctor`; `importlib.metadata` for `__version__`
  ~70 ms), ~75 ms work. The 300 ms exit limit is for evaluation (~70 ms, met). Import each
  subcommand module lazily from `COMMANDS` and read the version only for `--version`.
- **TD-013 · Deep Clean #1 · stale-lock takeover concurrency test intermittently has no winner.**
  During P5-T03c's pre-commit fast gate on Windows, all eight openers returned read-only in
  `test_openers_racing_to_take_over_a_stale_lock_get_exactly_one_lock`; no lock code changed.
  The complete 23-test project-lock file passed five consecutive reruns afterward. Measure
  takeover-guard contention and the dead-process test fixture under full-suite load before
  changing the lock algorithm or test bounds. Keep this visible at the Phase 5 review.
- **TD-014 · Deep Clean #1 · unknown TOML NaN values falsely look like stale state.**
  P5-T03d review reproduced this in both the new mode service and ProjectDetailsService
  loaded from HEAD: separately parsed NaN values compare unequal, so an otherwise unchanged
  manifest is refused by the live-snapshot guard. It fails closed and retains all disk data;
  not introduced by this refactor. Add nested NaN/positive-negative NaN comparison regressions
  before choosing a NaN-aware snapshot equivalence rule; do not drop other stale-state guards.
- **TD-016 · Deep Clean #1 · one Ubuntu 26.04 CI test process aborted during garbage collection.**
  `928d4d7` Check (ubuntu-latest) attempt 1 (job 129709015756) died at ~27% with "Fatal
  Python error: Aborted" while collecting garbage inside
  `test_save_backs_up_and_preserves_all_other_settings_without_publishing` (a TOML read; the
  loaded extensions were PySide6 and yaml). No assertion failed; the re-run (job 129711998985)
  passed 3,238 / 14. First seen on the new Ubuntu 26.04 runner image. Likely a Qt object
  freed off its thread by a cyclic collection; if it recurs, run the GUI suite with
  faulthandler and `gc.collect()` after each test to find the owning test.
## Blocked tasks
<!-- Task ID · what was tried · what's needed -->
_none_

## Tech debt (each item has a task ID or "Deep Clean #N")
_none_

## Human checkpoint results
<!-- HC0..HC4: date · outcome · issues filed as task IDs -->
- HC0 supporting input · 2026-09-22 · Auto-add library built successfully from the user's own
  `Race/Course/`; output contract supplied and incorporated. Real-data use deferred to HC1 as
  requested; no P4 blocker.
