# Phase 5 — GUI shell & dashboard (manual-mode MVP)

**Goal:** milestone M1 in the GUI — create a project, assign files, click Build, get an SZS, see
issues, open any file in the right tool.
**Exit:** pytest-qt end-to-end flow passes headless; screenshots reviewed; HC1 passed; Deep Clean #1.
UI style: clean, calm, native-feeling Qt; few colours (status colours only); generous spacing;
every control has a tooltip in plain language. Consistent spacing scale, one accent colour, no
decorative clutter. Status must never be conveyed by colour alone (icon + text too).

### [x] P5-T01 — GUI services & threading
`gui/services.py`: holds current Project, ToolRegistry, BuildController (QObject running the core
runner on a dedicated worker thread, re-emitting core events as signals), StatusService (evaluates
status on a worker, debounced), WatcherBridge (P5-T06). Dev-mode UI stall watchdog (> 100 ms logs a
stack). Rule: views never call blocking core functions directly.
**Acceptance:** unit tests for signal marshalling with fakes; watchdog test that detects an injected
`time.sleep(0.2)` on the UI thread.
Split (2026-11-04, size check: about 650 changed lines with tests):

#### [x] P5-T01a — Services container and build controller (commit 6a655dd)
`gui/services.py` gains `AppServices` (current Project, tools, build controller) and
`gui/build_controller.py` a `BuildController` QObject: it plans and runs a build on one dedicated,
named worker thread (finding tools and probing versions happens there too), re-emits every core
event as a signal on the UI thread, cancels, refuses a second build and a read-only project, and
reports a build that could not start. `shutdown()` cancels and waits, so no thread outlives it.
**Acceptance:** tests with a fake planner and runner: events arrive in order on the UI thread,
planning and building run on the worker, cancel reaches the runner, start-up errors and unexpected
exceptions arrive as a `failed` signal, second start and read-only project refused, no thread left.

#### [x] P5-T01b — Status service and UI stall watchdog (commit f548f83)
`StatusService` (debounced status evaluation on a worker, newest result wins, a request during a
run re-runs once after it) and the dev-mode watchdog (`CTSTUDIO_DEV=1`: a UI stall over 100 ms logs
the UI thread's stack once per stall).
**Acceptance:** debounce/coalescing tests with a fake evaluator; watchdog test that detects an
injected `time.sleep(0.2)` on the UI thread and stays quiet when idle.

### [x] P5-T02 — Welcome & new-project wizard (commits c0d6e6b, 8d2f788)
Welcome: New, Open, Recent (with missing-folder handling). Wizard pages: name + folder; source
(.blend optional, can be added later); slot picker (search by display name; default Luigi Circuit);
summary → create.
**Acceptance:** pytest-qt flow creates a project on disk; screenshot artifacts of each page.
Split (2026-11-04, size check: the wizard and the welcome screen with recent projects are each
about 500 changed lines with tests):

#### [x] P5-T02a — New-project wizard (commit c0d6e6b)
`gui/views/new_project.py`: four pages (name + location, with the project folder it makes; .blend,
optional; track to replace, searched by display name, abbreviation or cup, default Luigi Circuit;
summary). Create runs off the UI thread with the core `Project.create`; a failure is shown on the
summary page and nothing is half made by the wizard. File → New project… in the main window opens
it and opens the new project. **Acceptance:** pytest-qt flow creates a project on disk with the
chosen name, slot and .blend; each page's checks (empty name, folder that already has a project or
other files, missing .blend, no track found); screenshots of each page (light) and the summary
(dark).

#### [x] P5-T02b — Welcome screen and recent projects (commit 8d2f788)
Welcome screen in place of the empty card: New (the wizard), Open (folder chooser), Recent (from
the user settings, newest first, at most 10; a missing folder is marked and can be removed, never
silently dropped). Folder checks run off the UI thread. **Acceptance:** recent list kept in
settings across restarts (with backup, unknown keys kept); missing-folder handling; opening from
the list; screenshots light and dark.

### [x] P5-T03 — Dashboard (all parts done; last commit 4ea9b40)
Split (2026-11-04: header/cards, build controls and log together exceed one session):

#### [x] P5-T03a — Build callback failure safety (TD-012) (commit bb2f4eb)
Before adding GUI build controls, fix the runner's callback-error cleanup. After its workers
finish, record every successful queued result before saving state/cache; never call the failed
receiver again. **Acceptance:** deterministic callback-error tests prove completed parts are
recorded, failed/unstarted parts are not, no new work starts, the original error propagates,
workers end, the disk log retains completed work and the next build reuses the cache correctly.

#### [x] P5-T03b — Live project overview (commit f766568)
Read-only header (project name, folder, slot and Blender source); all component cards with
status icon/text, reasons and mode; refresh and path copying. Show it after create/open, with
welcome/dashboard navigation. **Acceptance:** live StatusService results, old-project results
ignored, last good statuses retained on error, read-only/build/checking states, keyboard and
light/dark/small-window screenshots; no filesystem checks on the UI thread.

#### [x] P5-T03c — Project slot and source editing (commit da5b2bb)
Project details dialog with the original track/arena selector and optional Blender source,
including choose/clear, explicit Save/Cancel and no writes until Save. **Acceptance:** loading,
validation and saving run off the UI thread; backed-up atomic saves preserve other/unknown
settings and refuse external changes, read-only/build/busy guards hold, errors leave the dialog
open and project unchanged, successful saves refresh the header/statuses; keyboard and screenshots.

#### [x] P5-T03d — Component-mode persistence (commit 47b70f6)
Blocking service to load exact manifest snapshots and change only a registry-supported mode.
**Acceptance:** all legal modes, unsupported component/mode refusal, backed-up atomic saves,
unknown and inactive settings/files retained, no-op avoidance, stale live/disk/root and
read-only/closed guards, final staging-window conflict protection, no worker-side publication.
Reuse project-details commit safety without changing its behavior. Split again for size: the
persistence, card controls and launch lifecycles each need independently proven failure tests.

#### [x] P5-T03f — Dashboard mode and component controls (commits 49eb132, c073c9e)
Wire component mode/primary/overflow controls to the service layer; file assignment and the
configurable editor framework remain T04/T07. **Acceptance:** joined background work, busy/
read-only guards, cancellation/errors, last-good-state retention, keyboard and screenshots.

#### [x] P5-T03g — Project-aware Blender launch service (commit 2b4110a)
Split again for size: project/settings safety, platform folder opening and GUI worker/control
lifetimes together exceed one session. This slice adds a blocking Blender launch service using
the existing measured core editor adapter; it does not add dashboard buttons yet.
**Acceptance:** current project source and configured executable, no-source/read-only/closed
refusal, fail-closed damaged settings, preparation-time project changes refused, actionable
errors and detached launch result/warnings preserved. No project/settings writes. Caller must
hold project ownership and run it off the UI thread; T03i wires that lifecycle.

#### [x] P5-T03h — Component-folder reveal service (commit b57ff16)
Resolve current component locations and open their folders through a portable core adapter.
**Acceptance:** measured Windows/Linux launch contracts, missing paths/tools, read-only-safe
inspection and no document editing or user-file changes. File outputs open their containing
folder even before the file exists; directory outputs open that directory. Missing directories
are errors, not created or replaced by an unrelated ancestor. Closed snapshots stay readable;
root/manifest changes during preparation are refused. A dispatch receipt is not a guarantee
that a desktop window displayed. Configurable editors remain T07; widgets/ownership remain T03i.

#### [x] P5-T03i — Dashboard launch ownership and controls
Wire Open in Blender and reveal-location actions through joined background work.
**Acceptance:** off-thread discovery/launching, current-project/lock ownership through completion,
busy/read-only rules, visible failures without clearing last-good cards, keyboard and screenshots.
Delivered as `gui/launch_controller.py` (one joined worker; typed/unexpected/interrupt results;
timed-out shutdown keeps the lock), `AppServices.start_launch` in-memory guards, a separate
dashboard launch notice/progress and card More → Open folder. Read-only projects may open
folders but not Blender; stale project/root/manifest results are ignored.

#### P5-T03e — Build controls and live log (split into e1–e3)
The ownership boundary, live controls/cards and bounded log exceed the session budget together.
Complete these in order; TD-012 is already closed by T03a. No original scope is removed.

##### [x] P5-T03e1 — Safe build requests and worker ownership (commit 98b0c66)
Add an AppServices build-start boundary for the current project: refuse no-project, read-only,
status-checking, editing, launching or already-building states without I/O. Pass test/release,
force and component options unchanged. Join before publishing completion; report interrupts
and thread-start failures without leaking running state. **Acceptance:** event-held worker,
lock lifetime, startup failure, queued delivery and interrupt tests; no new dashboard widgets.

##### P5-T03e2 — Dashboard build controls and live part progress (split into e21/e22)
The view plus project-aware wiring/card updates exceed the task-size budget. Complete e21,
then e22, before e3; these numbered IDs are two pieces of e2, not extra product scope.

###### [x] P5-T03e21 — Tested build-controls view (commit 7ddfbe2)
Signal-only test/release/cancel controls, step-count progress, last result and independent
warnings/errors. **Acceptance:** synthetic event/summary tests, safe cancellation and failure
recovery, keyboard shortcuts (Ctrl+B / Ctrl+Shift+B / Esc), native light/dark/minimum-size and
150%-font screenshots. No disk work or dashboard wiring yet; the controls are exercised in
GUI tests but are not exposed in the app until e22.

###### [x] P5-T03e22 — Dashboard wiring and live part progress (commit 731fe93)
Route the e21 controls through the e1 ownership boundary for the current writable project.
**Acceptance:** fake-build events update cards live while preserving last-good statuses;
busy/read-only/navigation guards, cancel/startup-failure/retry, stale-project suppression,
post-build refresh and integrated light/dark/minimum-size screenshots. No log scope (e3).

##### P5-T03e3 — Bounded live build log (split into e31/e32/e33)
The retained-data model, collapsible dashboard view and trustworthy command provenance exceed
one bounded task. Complete these in order; the full existing disk log remains unchanged.

###### [x] P5-T03e31 — Bounded virtual log model (commit a11067b)
A Qt list model for existing LogLine events, with row/text/per-line/step-ID limits, newest-tail
retention, explicit truncation and eviction counts. **Acceptance:** real Qt model data/signals,
multiline/Unicode/oversized inputs, stable surviving indexes, clear/reset and bounded storage.
No dashboard widget, command parsing/copying, disk I/O or new core event in this subtask.
Verified: 44 new cases on CPython 3.12/3.13, real list selection/model protocol, bounded allocation,
strict Windows/Linux typing and budgets; 30 assertion-caught mutants and independent reviews.
Final gate 3,176 passed / 6 existing skips; exact corrective Check Windows/Ubuntu green, 3,182
selected on both. CI also exposed and verified a test-only queued-plan synchronization fix.

###### [x] P5-T03e32 — Collapsible live log view and dashboard wiring (commit 5455d53)
Expose the virtual model through a collapsed-by-default list, keep collecting while collapsed,
follow new output only when appropriate, and reuse current-run context guards and reset rules.
Keep expansion on a new accepted run, collapse on rebind, retain on same-project navigation
and completion; a refused request must not erase the last output. No command inference/copying.
**Acceptance:** live fake-build lines, history-cap feedback, keyboard access, usable build
controls while collapsed, and light/dark/minimum-size/enlarged-font screenshots.
Verified: 42 new cases, full-cap reader-anchor regressions, keyboard and themed/150% screenshots;
fixes `62a1745` (enlarged-font card width) and `f47420d` (footer screenshot sync, TD-015).
Final gate 3,219 passed / 6 skips; exact Check Windows/Ubuntu green, 3,225 selected on both.

###### [x] P5-T03e34 — Dashboard follows the newest build output
User decision after e32: in a small window the newest log lines, build bar and a late result or
error must not end up below the visible dashboard. Follow the end while the reader stays there;
scrolling up stops following until they return to the end or start another build. Done before e33.
**Acceptance:** auto-reveal during and after a fake build as queued layout grows, reader scroll
respected, no scrolling before a build or after rebind, focus unchanged, light/dark screenshots.
Done in `3f7c31a`; exact Windows/Ubuntu Check green.

##### P5-T03e33 — Trusted command entries and safe exact copying (split into e33a/e33b)
Existing LogLine text has no structured command provenance. Add the command-reporting boundary
before offering Copy command; never guess commands from arbitrary tool output. Preserve argv
boundaries/quoting and redact designated sensitive arguments. **Acceptance:** trusted synthetic
commands copied exactly after documented redaction, non-command output cannot enable copying,
keyboard/screenshot coverage, and the existing full disk-log behavior remains intact.

###### [x] P5-T03e33a — Trusted command events (core) (commits 61eeba4, 928d4d7)
The one process-spawning boundary (`core/tools/process.run`) reports the argv it actually
starts, with caller-designated sensitive arguments replaced by a documented marker, to the
build step running on that thread; the runner turns reports into a structured `CommandRun`
event. Exact platform command text (CreateProcess quoting on Windows, POSIX shell quoting
elsewhere) is a core function. **Acceptance:** synthetic tools run by a build step produce
`CommandRun` events with exact redacted argv; command text round-trips through the real OS
parser (spaces, quotes, backslashes, empty and Unicode arguments); tool output that looks like a
command stays a `LogLine`; runs outside a build report nothing; sensitive values never reach
events, the tool's output lines, the tool log, the build log, JSON events or
`ToolFailed`/`ToolTimedOut` details (argument values; not the executable path, folder or
environment); the
disk build log gains one `command:` line per run, and JSON events document a `command` event.

###### [x] P5-T03e33b — Copy command in the live log (GUI) (commit 4ea9b40)
Show `CommandRun` entries as distinct command rows in the live log and offer Copy command only
for them, copying the core command text exactly; say plainly that on Windows it is a
PowerShell/CreateProcess command line, not cmd.exe. **Acceptance:** keyboard and context-menu copy
of a trusted synthetic command, ordinary output (even command-looking) cannot enable copying,
light/dark screenshots, existing log behaviour unchanged.

Original combined scope:
Header: project name, slot selector, source file + "Open in Blender". Component cards (status icon +
colour + text, one-line summary, primary action, "Open in ▾", overflow: Reveal in file manager, Copy
path, Mode: Auto/Manual/Template, Settings…). Footer build bar: Build test SZS, Release build,
Cancel, progress, last result. Collapsible virtualised log panel with "Copy command" on command lines.
**Acceptance:** cards reflect status changes live during a fake build; keyboard navigation works;
screenshots in light and dark themes. Before the Build page uses the core runner, close TD-012:
prove a failed UI event callback cannot leave cached outputs with missing part-state records.

### [x] P5-T04 — Manual file assignment
Drag & drop onto a card or "Choose file…". Validate type (magic). Copy into `files/` by default, or
"reference in place" option. Replacing an existing manual file backs up the old one.
**Acceptance:** tests: wrong type rejected with explanation; backup created; manifest updated.
Split (2026-11-10, size check: the core file work and the card's drop/chooser UI together
exceed one session; no original scope is removed):

#### [x] P5-T04a — Assign a supplied file (core)
`core/components/assign.py` `assign_file(project, part, source, *, reference=False)`. Before
touching anything it refuses: a read-only project, a part without a manual mode, a missing
source, a source inside `.ctstudio/`, a folder copy into itself, and the wrong type (the same
check status and build use), each with a plain explanation and hint. By default the file (a
folder for post-effects) is copied into `files/<game name>`; "reference in place" records the
source path instead (project-relative when inside the project) and copies nothing. Replacing a
different existing copy backs it up first into `.ctstudio/backups/<UTC time>/files/…`. The
part's mode becomes manual with that file, saved to ctstudio.toml with its usual backup and a
check that the file was not changed on disk meanwhile.
**Acceptance:** tests: wrong type rejected with explanation and nothing changed; backup created
when replacing (an identical file is left alone); manifest updated and reloads equal; reference
in place copies nothing; failed copies and saves leave the old file and manifest intact.

#### [x] P5-T04b — Drop a file on a card or Choose file… (GUI)
A component card accepts one dropped file or folder and offers "Choose file…" with a "Reference
in place" option; assignment runs on a worker, a refusal shows its reason, and status refreshes.
**Acceptance:** GUI tests with synthetic drops and the keyboard chooser path, read-only and busy
projects refused, wrong type explained on the card, light/dark screenshots.

### [x] P5-T05 — Issues panel (commit 7bc350c)
Grouped by component and severity; hint text; wiki link; "Copy report". Clicking an issue focuses
the component card.
**Acceptance:** populated from recorded `wszst check` outputs in tests.
Split (2026-11-11, size check: the report model and the panel widget together exceed one
session; no original scope is removed):

#### [x] P5-T05a — Issue report (core)
`core/validation/report.py`: group issues by the track part they belong to (its card), in
dashboard order with the whole-track ones last; within a part, errors first, then warnings,
hints and notes, otherwise as found. A finding names its part by the part's id, by one of its
files (`map_model.brres` → Minimap; files inside a folder part, judged inside the project), by
the model a check section names (including `course_d_model` of Wiimm's `_d` tracks), or by
the part its measured wszst wording names. Extra files, effects and object models stay under
the whole track. Each group carries the part's wiki page. Severity counts in
plain words. `load_report(root)` reads `.ctstudio/issues.json` (None before the first check; a
damaged file is a plain `ProjectError`). `report_text` is the "Copy report" text (Markdown:
track, counts, one section per part with hints, files and wiki links).
**Acceptance:** tests from the recorded `wszst check` output and an `issues.json` written by
the validate step: every finding lands under its part's card, ordered by severity; counts and
report text exact; damaged or missing files handled.

#### [x] P5-T05b — Issues panel (GUI) (commit 7bc350c)
A dashboard panel shows the report (loaded off the UI thread on open and after each build),
grouped by part with severity counts, hint text and a wiki link; "Copy report"; clicking an
issue scrolls to and focuses that part's card.
**Acceptance:** GUI tests populated from recorded `wszst check` output; keyboard path; light
and dark screenshots.

### [x] P5-T06 — File watching & external-edit detection (commit 872b1cc)
WatcherBridge wraps core watcher (watchfiles thread) → debounced status refresh. When a generated
stage file changes externally → `EditedExternally` banner on the card with the three choices from
ARCHITECTURE §8 (the capture mechanism itself arrives in P7; here implement Lock-as-manual and
Discard-with-backup).
**Acceptance:** test modifies a generated file → banner appears within 2 s → Lock-as-manual copies to
`files/` and switches mode.
Split (2026-11-11, size check: the watcher and its Qt bridge, the two core actions and the card
banner each need their own failure tests; together well over one session; no scope removed):

#### [x] P5-T06a — Project watcher and live status refresh (commit 097a204)
`core/project/watch.py`: a watchfiles watcher on named background threads for the project folder
(recursive) and the `.blend` and supplied files outside it (their folder, not their inode, so
atomic saves are seen). Ignored: CT Studio's own `.ctstudio/` files except the generated stage,
`build/`, `.git/`, Blender's `.blend1…` backups and `.blend@` save files. `gui/watcher_bridge.py`
`WatcherBridge` brings changes to the UI thread (stale watchers' changes dropped) and follows
the current project; `AppServices` asks for a status check on a change (not while building:
the build's own refresh follows), so an outside edit of a generated file shows as "edited
outside CT Studio" on its card. **Acceptance:** real-watcher tests: an edited stage file shows
EditedExternally within 2 s; atomic save and an outside `.blend` noticed; ignored files trigger
nothing; switching/closing projects stops the old watcher and drops its late changes; shutdown
leaves no watcher thread; a folder that cannot be watched is reported, not raised on the UI thread.

#### [x] P5-T06b — Lock as manual and Discard with backup (core) (commit c4e0488)
Core actions for a part whose generated file was edited outside CT Studio: Lock as manual copies
the edited file into `files/` (reusing `assign_file`) and switches the part to manual; Discard
backs the edited file up into `.ctstudio/backups/<UTC time>/` and removes it so the next build
makes it again. **Acceptance:** tests: both actions, backups made, manifest saved, refusals
(read-only, part not edited, file gone) change nothing.

#### [x] P5-T06c — Edited-outside banner on the card (GUI) (commit 872b1cc)
The card of an EditedExternally part shows a banner with Lock as manual and Discard (the capture
choice arrives in P7), run on the joined launch worker. **Acceptance:** the original P5-T06
acceptance (edit → banner within 2 s → Lock-as-manual copies to `files/` and switches mode);
keyboard path; light/dark screenshots.
Split (size check: worker/service ownership, result routing, card layout, keyboard and real-watcher
GUI tests together exceed 400 changed lines; no original acceptance removed):

##### [x] P5-T06c1 — Joined outside-edit requests (commit 3377d56)
`AppServices.start_reconcile` checks current-project eligibility using memory only;
`LaunchController.reconcile` runs Lock or Discard on the existing joined launch worker.
Receipts identify the action, part and captured project/root/manifest; only the later UI
receiver publishes a saved manifest. **Acceptance:** real core actions on synthetic edited
files; off-UI execution, joined completion, error/interrupt identity, one-at-a-time requests,
read-only/busy/invalid refusals without disk work; switching/closing retain the project lock.
No new buttons in this leaf.

##### [x] P5-T06c2 — Card banner and joined-result presentation (commit 872b1cc)
Wire those requests to the EditedExternally banner with Lock as manual / Discard controls,
confirmation for Discard, per-card progress/results and stale-result guards. Retain all original
P5-T06c acceptance: real edit → banner within 2 s → Lock copies to `files/` and switches mode;
Discard backup and refreshed status; re-read saved state after interrupted startup rather than
assuming the action did not run; keyboard path, minimum width/enlarged fonts, light/dark
screenshots, user guide. Completing c2 completes P5-T06c and P5-T06.
Split (size check: card/dashboard are already 368/396 lines; banner presentation, joined-result
routing, uncertain-start disk recovery and full GUI acceptance exceed one small task):

###### [x] P5-T06c2a — Outside-edit banner presentation (commit 99268e8)
A signal-only native-palette widget for the card: Lock as manual / Discard, safe-default Discard
confirmation, explicit eligibility, progress and bounded accessible result text. No disk work or
worker ownership here. **Acceptance:** status/eligibility matrix, exact action signals, cancelled
or invalidated confirmation does nothing, busy/reset and keyboard behavior, minimum-width and
enlarged-font light/dark widget screenshots. Dashboard mounting is c2b; no unconnected actions
are exposed in the application in this leaf.

###### [x] P5-T06c2b — Mount banner and present joined results (commit 872b1cc)
Mount the widget on each eligible card; dispatch through c1, publish only fresh joined results,
refresh saved state after uncertain startup, and preserve all original c2 acceptance above:
real watcher edit → banner within 2 s → Lock copies/switches mode; confirmed Discard backs up
and refreshes status; stale/error/refusal behavior, keyboard path, whole-dashboard minimum width
and enlarged fonts, light/dark screenshots and user guide. Completes c2, c and P5-T06.
Split (size check: safely recovering a saved manifest after ambiguous native startup needs
joined-worker failure tests of its own; combining it with dashboard routing, card layout and
end-to-end visual acceptance exceeds 400 changed lines; no original acceptance removed):

###### [x] P5-T06c2b1 — Joined saved-state recovery (commit 7919540)
After each Lock/Discard attempt, read the saved manifest on the same worker, retaining exact
bytes and any separate read error even when startup acknowledgement was interrupted. Return
this snapshot only after joining, without changing the live project. **Acceptance:** real core
Lock/Discard, post-write failure and native-start interruption; off-UI reads, unchanged original
error identity, read failure reported separately, no disk read for requests that never ran or
for assignment/editor/folder requests; invalidated completion remains suppressed.

###### [x] P5-T06c2b2 — Dashboard wiring and full outside-edit acceptance (commit 872b1cc)
Mount the banner, route requests and fresh joined results (including b1 recovery), refresh
statuses/watch plans, and retain all c2b acceptance above: real watcher → banner → Lock copies
and changes mode; confirmed Discard backup; safe recovery/read failure/refusal/stale results;
keyboard, whole-dashboard minimum width/enlarged fonts, local light/dark screenshots and user
guide. Completes c2b, c2, c and P5-T06; b1 alone exposes no new application controls.
Also clarify the inherited start() docstring: False can follow already-dispatched work;
routing must respect busy ownership and joined completion, not assume rollback.
Split after reading the live dashboard (396 lines) and recovery matrix: publication, controls,
and complete visual/end-to-end coverage exceed one 400-line leaf. All acceptance above stays open.

###### [x] P5-T06c2b2a — Publish joined outside-edit saved state (commit a5e1b26)
Route fresh joined Lock/Discard results separately from folder launches; publish the worker's
saved snapshot even after action/startup faults, never a receipt's guessed state. Rebind cards,
refresh statuses/watch plans, and show honest outcomes. Keep a stale live manifest unchanged;
if saved state cannot safely be published, retain the write lock but make the project read-only
until closed/reopened. **Acceptance:** real Lock/Discard and failure recovery, joined/UI-only
publication, exact saved state, stale/project/root guards, actionable plain-text results,
read-failure/stale write refusal and lock retention. No new controls exposed in this leaf.

###### [x] P5-T06c2b2b — Mount and route outside-edit controls (commit d70a533)
Mount the c2a banner on eligible cards; route Lock and confirmed Discard through the joined owner
and b2a publication. Explicit status/read-only/check/build/edit/launch eligibility, busy/results,
modal invalidation, refusal and rebind behavior. **Acceptance:** real watcher edit to visible
banner within 2 s, Lock copies and changes mode, confirmed Discard backs up, Cancel changes
nothing, keyboard access and no UI disk work. Keep the original acceptance above intact.

###### [x] P5-T06c2b2c — Complete outside-edit dashboard acceptance (commit 872b1cc)
Whole-dashboard minimum-width/enlarged-font light/dark local screenshots and geometry checks,
full watcher-to-action recovery/refusal/stale regression coverage, user guide and honest Linux
desktop gap. Completes c2b2, c2b, c2, c and P5-T06 only after every original criterion passes.
Split after sizing the populated-window/font matrix, local inspection, user guide and real-
watcher failure matrix: together these exceed one small acceptance leaf; no criteria removed.

###### [x] P5-T06c2b2c1 — Whole-dashboard outside-edit presentation and guide (commit 5d5a443)
Minimum-window and enlarged-font geometry, light/dark local images of actual joined actions,
readable complete controls and outcomes, user guide and start()/False wording. Keep render,
real-action, hosted Linux runtime and unverified Linux desktop appearance claims separate.
**Acceptance:** populated dashboard width/label/scroll/keyboard checks; actual working and
joined-result screenshots in both themes/font sizes; guide matches native choices and recovery.
All parents remain open until c2b2c2 checks every original criterion.

###### [x] P5-T06c2b2c2 — Final outside-edit watcher failure acceptance (commit 872b1cc)
Real watcher-to-action recovery, refusal and stale-result matrix, including native-start
uncertainty and post-write rebind, using actual saved files and writer-lock protection.
Combine with prior timing/Lock/Discard/Cancel/keyboard and c1 whole-dashboard evidence;
complete c2b2c and all P5-T06 parents only after every original criterion passes.
Final audit found two additional executable-evidence gaps beyond the 360-line watcher/action
failure matrix: canonical-resolution fault combinations and real watcher switch/close. Split
again at the size check; no original criterion is waived and every parent stays open.

###### [x] P5-T06c2b2c2a — Real-watcher native-action failure matrix (commit dac5481)
Actual edit after real watcher readiness, mounted native Lock/confirmed Discard, creation/core
refusal/post-write/read faults, native-start uncertainty and post-write same/replaced-memory
rebind. **Acceptance:** exact saved bytes/manual files/backups, joined UI delivery, original and
independent error identities, retained writer lock, write refusal and editable reopen; prove
new acceptance tests with assertion-caught source controls. Parents remain open for c2b.

###### [x] P5-T06c2b2c2b — Canonical recovery and real watcher lifecycle closure (commit 872b1cc)
Add committed canonical-resolution failure coverage armed only after real actions, including
relative/absolute roots and independent startup/action/recovery errors; prove worker-only
resolution, no saved reader after failed canonicalization, protection/lock retention and reopen.
Add real watcher project switch/close coverage alongside deterministic late-event tests.
**Acceptance:** resolve acceptance-audit G02/G03, re-run all original criteria plus the new
failure matrices, and close P5-T06 parents only after final independent review and exact CI.

### [x] P5-T07 — "Open in…" framework (closed by g map, `0acdf00`)
Mapping file-type → preferred tools (defaults: brres → BrawlCrate, RiiStudio; kmp → Lorenzi, KMP
Cloud; szs → BrawlCrate, RiiStudio; blend → Blender; folders → system file manager; any → custom
tools). Configurable in settings. Missing tool → dialog linking to Tools page. Uses launch contracts
from TOOLS.md (Wine on Linux for Windows-only tools).
**From S7 (P0-T10):** one file per launch and a new process every time — never offer "open both"
and never expect an existing window to pick up a second file. The UI must not claim the file
*opened*: RiiStudio keeps an empty window up after a failed load. **TD-001:** its `File:` stdout line
is not a receipt — it disappears whenever the mandatory GitHub update check fails, and upstream
offers no flag/setting/config to disable that check. The adapter must never parse or depend on the
line; report only "launched". The network-marked characterization test is nightly-only, while HC1
owns the no-tty observability question. Before offering "Edit KMP" with Lorenzi's editor, make sure
`course.kcl` (that exact lowercase name) sits beside the KMP, or the user silently edits against a
blank box.
**Acceptance:** tests with fake GUI tools verifying argument construction per OS, including that
options follow the path and that two files produce two launches; manual run noted for HC1.

#### [x] P5-T07a — Built-in editor catalogue and saved preferences (commit `d5a5164`)
Add pure ordered defaults for .brres/.szs (BrawlCrate, RiiStudio), .kmp (Lorenzi, KMP Cloud),
.blend (Blender) and folders (system file manager). Store preferred built-in choices in the
machine settings; preserve unknown settings, tool paths and backups. Malformed recognized
preferences must raise SettingsError, never silently select another editor. No dispatch/UI.
**Acceptance:** exact defaults/order, override/reset, immutable projections, Unicode-path
round-trip/backups, invalid load/save with unchanged bytes, and unknown-field preservation.
Catalogue intent for .szs is not executable support until T07b. Parent P5-T07 remains open.
As built: 53 new cases, 150 focused; six assertion-caught source controls, independent APPROVE
(76 settings plus 39 extra boundary cases), strict three-file Windows/Linux checks and 76 fresh-
install cases. Full local gate 4,109 passed / 6 existing skips / 176 deselected; exact code
Check Windows/Ubuntu selected 4,115, both actual artifacts coverage.xml only. No dispatch/UI.
Documentation closeout c6f175b failed Windows job 131990126837 at the unchanged 1200-second
limit. Captured case: component-mode dialog supported spec0/auto, inside dialog.open(); worker
stack in project_details.load/root.resolve and watcher path preparation. Cause not established.
Ubuntu passed. Nine bounded local probes, including the 510-case hosted prefix, did not
reproduce the hang. Matching runner/code/lockfile; one controlled same-SHA rerun passed:
Windows 4100/15, Ubuntu 4101/14, 4115 selected, coverage-only ZIPs. No code repair or known
host-flake diagnosis is claimed. Original failed log retained; no tests/time limits waived.
Final closeout 5cbf183 passed full local and exact Windows/Ubuntu Check, with coverage-only
artifacts and clean matching main. P5-T07a is complete; the original timeout remains unexplained.

#### [x] P5-T07b — Built-in file dispatch and collision prerequisite (closed by g map, `0acdf00`)
Extend existing adapters for .szs, preserve OS argv/Wine/warnings/one-file/new-process rules,
and enforce exact lowercase sibling course.kcl before offering Lorenzi. No process-liveness,
window-title or RiiStudio stdout claim of successful document loading.
**Acceptance:** fake tools on both OS branches, options after path, two files/two dispatches,
missing files/editors/prefixes and collision prerequisites leave user files unchanged.
Split below after native capability measurement and a >400-line combined estimate; every
original criterion remains required. P5-T07b stays open until both leaves and the original
before-offering collision check (worker/menu proof in P5-T07d/e) are verified.

##### [x] P5-T07b1 — Exact Lorenzi collision prerequisite (commit `38d0fab`)
Refuse Lorenzi dispatch unless a regular sibling file is named literally course.kcl, including
on case-insensitive Windows filesystems. Inspect only the document's own folder, before editor
lookup, Wine or process launch; turn inspection errors into actionable typed errors. Preserve
existing eligible-editor, Unicode, Wine-prefix and argument-order regression assertions.
**Acceptance:** missing/wrong-case/directory/uninspectable sibling, no working-directory
fallback, independent documents and fresh dispatch checks, two eligible requests/two detached
launches, unchanged user bytes; independent review, assertion-caught controls, strict actual-
file Windows/Linux typing, fresh install, full gates and exact Check/Integration.
Menu eligibility and worker-thread preparation remain T07d/e, not completed by this adapter guard.
As built: 27 new / 91 focused + 8 independent boundary cases; 36 legacy assertion ASTs
unchanged, 6/6 source controls assertion-caught (3 independently repeated), strict 6 actual
files per Windows/Linux target and 91 fresh locked-install cases. Native synthetic Lorenzi
adapter launch passed. Full local gate 4136/6/176; exact code Check + Integration both
platforms passed, selected 4142; actual Check ZIPs coverage.xml only. No loading/save claim.
At b1 closeout only b1 was complete; b/b2/T07 remained open. Final closeout 47fb5f0 passed its full local gate
and exact Windows/Ubuntu Check, selected 4142, with coverage-only actual artifacts.

##### [x] P5-T07b2 — Measured SZS dispatch (commit `bd7398b`)
Enable BrawlCrate/RiiStudio .szs using their existing verified positional argv. Native Windows
capability is measured with synthetic data; Linux/Wine SZS document loading remains unmeasured.
**Acceptance:** both OS argv branches, options after path, one file/new process per request,
two requests/two real-runner dispatches, missing document/editor/prefix refusals and unchanged
bytes. Preserve launch-only receipts and Unicode warnings; never infer document loading from
process/window/stdout. Retain HC1 manual-run requirement and all parent acceptance.
As built: 24 new unit / 122 focused cases, plus 2 real-Wiimm synthetic archive/real-runner
integration cases. Six source controls assertion-caught; independent APPROVE, four
independent controls and 19 boundary cases, immutable 578-file snapshot.
Strict 7 actual Python files per Windows/Linux target; 122 fresh locked Unicode-install cases
plus 11 gate self-tests. A later nested-gate Vulture failure was reproduced: required parser
Protocol keyword help= needed the existing whitelist's documented name-use entry; checker
thresholds stayed unchanged. The final metadata delta has separate independent approval.
Exactly two legacy expectations updated for SZS; the other 87 assertion ASTs preserved.
Pinned native adapter dispatch/owned windows/unchanged bytes measured, not new loading/save
or HC1 proof. Local gate 4160/6/178; exact code Check + Integration both OSes passed,
selected 4166, both new integration cases executed per OS, actual Check ZIPs coverage.xml only.
Initial full gate stopped at collection: duplicate unit/integration module basenames.
The byte-identical integration rename fixed collection; original failure evidence retained.
First local closeout gate hit Windows Application Control WinError 4551 on fake wszst.exe:
111 failed / 4049 passed / 6 skipped. Failed run retained; three fresh focused
test_fake_wiimm.py runs then passed (144 cases each), with source/tests/security
unchanged. The policy inconsistency is unexplained, not a code or security repair.
Final closeout 72b4c6f passed the unchanged full local gate and exact Windows/Ubuntu Check,
selected 4166, coverage-only actual artifacts and clean matching main. P5-T07b2 is complete.
Only b2 adapter scope is delivered; parent b/T07 remain open for worker/menu eligibility
and release.

Parent closure boundary: b1/b2 adapter tests cover dispatch/refusal, not menu eligibility.
The original requirement to check course.kcl **before offering** Edit KMP still needs executable
worker/menu proof in P5-T07d/e. Completing b2 alone leaves P5-T07b and P5-T07 open; next is
P5-T07c. Final T07g acceptance must rerun b1/b2 plus every original argv, refusal,
two-request/real-runner and byte-preservation case. Native automated probes do not complete HC1.

#### [x] P5-T07c — Custom-tool and Wine-prefix preferences and dispatch (closed by g map, `0acdf00`)
Persist custom editors using existing CustomTool argv templates and machine-specific Wine
prefix choices. Validate damage, preserve unknown fields/backups, and execute only through
core adapters with argv tokens, never shell parsing or another process owner.
**Acceptance:** safe placeholders/Unicode argv, explicit custom choice, native/Wine routes,
malformed/stale preferences fail closed; independent launch receipts and separate processes.
Split below: combined persistence, validation and dispatch tests exceed one ~400-line leaf.
Every original criterion remains required; c/T07 stay open until all leaves and original
joined/menu/configuration acceptance are verified.

##### [x] P5-T07c1 — Validated custom-tool machine preferences (commit `7d65fa4`)
Persist named CustomTool executable/argv templates under machine settings, not projects.
Reuse its existing {file}/{dir}/{project} token validation (including harmless empty-spec
spellings such as {file:}); preserve the two-argument
UserSettings constructor, unrelated tools/preferences, unknown record fields and exact backups.
Recognized damaged data fails closed on load, projection, update and before any save write.
**Acceptance:** Unicode/token/escaped-brace round trips, immutable projected argv,
malformed types/placeholders/NUL/unencodable text, pure projections without filesystem work,
unknown-field retention, reset/nonmutation, prior file and backups unchanged on refusal.
No custom default, executable discovery, Wine routing, launching or GUI is delivered by c1.

Delivered c1 only: 226 focused/final locked-install cases (140 new),
48 independent behavior probes plus origin, 12 parent and
10 independent final assertion-caught source controls; strict 3 actual files per platform.
Original/final 580-file review trees unchanged; original and additive test/doc delta approved.
Full local gate 4300 passed / 6 skipped / 178 deselected; exact implementation Check Windows/Ubuntu,
selected 4306, both actual artifacts coverage.xml only. Pure settings paths do not
trigger/require real-tool Integration; no adapter, process, Wine, GUI or loading claim.
Original reviewer probe 46 passed/1 failed (wrong empty-spec refusal expectation) retained;
corrected 49 checks pass, no product behavior changed. Existing empty specs
characterized in committed tests; earlier API-absence RED and harness errors not behavioral proof.
c/c2/c3/T07 remain open; custom choices, fresh native/Wine dispatch and usable UI still pending.
Documentation closeout bdc3609 passed its separate full local 4300/6/178 gate and exact
Windows/Ubuntu Check (4306 selected), coverage-only actual ZIPs and clean matching main.
P5-T07c1 is complete; no parent closure or custom dispatch is implied.

##### [x] P5-T07c2 — Machine-specific Wine-prefix preferences (commit `80b22b5`)
Persist/reset per-editor Wine-prefix choices with strict recognized-data validation,
unknown fields/backups and old constructor compatibility. Prefix existence/architecture
are rechecked by adapters at dispatch, not inferred from saved metadata.
**Acceptance:** Unicode round trips, native defaults unaffected, malformed data refuses
before writes, independent choices and no filesystem work in pure projection.
Machine schema: `wine_prefixes: {editor_id: {prefix: text, ...future fields}}`, with exact
lowercase slug IDs for built-in/custom/future editors. `wine_prefixes()` projects copied
Path metadata; `with_wine_prefix(id, path_or_none)` copies an update/reset, retaining siblings
and extensions. Recognized malformed records refuse load/projection/update/save before
writes/backups. Prefix text must be nonblank, UTF-8 encodable and NUL-free; relative/missing
paths are allowed metadata. No resolve/stat/discovery, architecture checks, Wine invocation,
launch-mode/default change or UI in c2; actual dispatch/validation stays c3 and adapters.

Delivered c2 only: 390 focused/locked fresh-install cases (155 new),
29 independent checks, 14 parent and 5 independent assertion-caught
source faults; strict 3 actual files per Windows/Linux target. Final 582-file snapshot unchanged,
independent APPROVE; c1 source and legacy assertions unchanged. Per-editor prefix metadata,
updates/reset, nested extension isolation, Unicode and byte-exact backups are covered, not
Wine installation or dispatch. Full local 4455/6/178; exact implementation Windows/Ubuntu
Check selected 4461, both actual ZIPs coverage.xml only. Integration not applicable:
pure settings paths, no process/adapter/real-tool behavior change. Worker tool-limit exit1,
API-absence RED and initial Windows-separator test-oracle failure retained, not approvals;
parent completed final verification, no production repair claimed for that harness error.
Initial Anthropic review hit HTTP429 before pytest execution; it was not an approval.
The separate alternate-provider review supplies the independent checks recorded above.
Original Ubuntu job 132579884831 timed out at 1200.1s in the existing canonical-recovery
GUI case (none/KeyboardInterrupt/lock/absolute), during dashboard signal connection. Its one
60s trace also shows a watcher resolving paths, not a proven filesystem cause or persistent
stack. GUI/watch/test code, lockfile and runner image match the last green baseline.
Three fresh Windows case probes, the 48-case file and 1135-case GUI predecessor prefix pass;
these are nonreproduction, not Linux evidence or a repair. Sole same-SHA Ubuntu rerun passes;
original failure is retained and cause remains unexplained. No tests/limits were weakened.
c/c3/T07/b and original d/e/f/HC1 remain open; next c3. Documentation closeout requires its
own full local gate, exact hosted Check and artifact/remote readback before final delivery.

##### [x] P5-T07c3 — Explicit configured custom/native/Wine dispatch (commit `fd8b690`)
Use saved CustomTool argv tokens only for an explicit custom choice; keep built-in defaults.
Route through existing core process/Wine owners, not shell parsing or a new executor.
**Acceptance:** fresh preferences, safe placeholders and Unicode argv, two independent real
launch receipts/processes, native/Wine routes, stale executable/document/prefix refusals,
unchanged user bytes, original built-in behavior/warnings and launch-only wording.

###### [x] P5-T07c3a — Native custom-editor dispatch (commit `231180e`)
Explicitly dispatch a supplied CustomTool through the existing detached process owner.
Keep each argv token intact, substituting canonical document/directory/project paths with
existing safe placeholder rules (including escaped braces and empty specs). No discovery,
default selection, settings writes, CLI/menu/UI wiring or Wine startup in this leaf.
**Acceptance:** two actual fake-editor processes/atomic receipts with distinct launch and
writer PIDs, exact Unicode/space/empty/metacharacter argv and document-parent cwd; freshly
refuse missing/non-file documents/executables and invalid project directories, unsafe text
and filesystem inspection failures before dispatch. Preserve typed errors/causes, user bytes,
unchanged built-in adapters/warnings and launch-only receipts. Linux .exe requires Wine and
is refused here; c3b adds that route. An explicit custom id may equal a built-in id without
implicitly applying that built-in's options or changing defaults.

Delivered c3a only: supplied CustomTool native dispatch through the existing detached owner;
544 focused/locked Unicode fresh-install cases (62 new), 22 independent boundaries,
15 parent plus 6 independent primary-assertion source controls, strict 2 actual files
per Windows/Linux target, and immutable 584-file APPROVE. Two real fake-editor
launches prove exact argv/cwd, separate launch/writer PIDs and unchanged source bytes, not
editor loading. Original built-in source/tests/defaults/warnings remain unchanged.
Full local 4517/6/178; exact Windows/Ubuntu Check (4523 selected) plus both
Integration jobs, including the existing two-case real-Wiimm synthetic archive dispatch suite.
Both actual Check artifact ZIPs contain coverage.xml only; no game assets/fonts/screenshots.
API-absence RED and retained parent/reviewer harness failures are not product proof; final
behavioral checks and source controls are separately verified. No Wine execution, saved-choice
facade, menu/UI or real-editor loading/save claim. c3/c/b/T07 and d/e/f/g/HC1 remain open;
next c3b. Documentation closeout requires its own full local gate, exact hosted Check and
artifact/remote readback before final delivery.

###### [x] P5-T07c3b — Custom Wine argv and fresh runtime validation (commit `fd8b690`)
Route explicit Windows custom tools on Linux through the existing Wine/process owners.
Convert file/directory/project substitution values using verified winepath behavior, not
shell parsing or conversion of literal user tokens. Validate executable/prefix architecture
and prefix existence for both 32- and 64-bit programs at every dispatch; retain native behavior.
**Acceptance:** exact Wine argv/cwd/environment, safe placeholders and Unicode, independent
requests, stale/malformed/missing-prefix/executable/document refusals and unchanged user bytes.
Exercise the actual Wine adapter and process boundary with controlled fakes; distinguish that
proof from real Wine/editor loading, which remains unmeasured unless explicitly exercised.

###### [x] P5-T07c3b1 — Checked complete-argument Wine launch boundary (commit `5a139bf`)
Add a complete-token argv entrypoint to the existing Wine owner and share its detached
startup/watch/error handling with the existing document-first entrypoint. Validate Wine,
PE executable and prefix freshly for every request, including prefix inspection for 32-bit
programs; preserve typed actionable failures and inspection causes without swallowing interrupts.
**Acceptance:** PE32/win32, PE32/win64 and PE32+/win64 success; PE32+/win32, missing/malformed/
stale prefixes and executables refused before helper/editor processes. Opaque Unicode/space/
empty/metacharacter tokens, exact cwd/WINEPREFIX/watch and early-error explanation are retained;
an actual synthetic Wine executable reaches the real process boundary with an atomic receipt
and unchanged input bytes. Existing built-in argument/warning behavior remains unchanged.
This boundary does not substitute custom placeholders or wire custom settings/UI; b2 does
custom Wine dispatch. Re-run all original b acceptance across b1/b2 before closing b.

Delivered b1 only: fresh canonical Wine/PE/prefix checks for both architectures, complete
opaque argv/cwd/WINEPREFIX/watch and one shared detached startup/error owner. Unknown startup
failures keep their identity/cause; inspection failures are typed and interrupts escape.
644 focused/locked Unicode fresh-install cases (68 new), 45 independent boundaries,
18 parent plus 10 independent primary-assertion source controls; strict 2 actual files
per Windows/Linux target. Immutable 585-file APPROVE and 484 unchanged legacy source/test files.
Two actual synthetic Wine process receipts retain independent launch/writer PIDs, exact tokens,
cwd/environment and unchanged inputs; not actual Wine/editor loading or saving.
Full local 4585/6/178; exact Windows/Ubuntu Check (4591 selected) plus both
Integration jobs, including existing real-Wiimm synthetic archive dispatch. Actual Check ZIPs
contain coverage.xml only; no game assets/fonts/screenshots. API-absence RED is not behavioral
proof; the rate-limited implementation worker supplied no implementation/approval.
The first review's registry-stat cause finding was reproduced through all three entrypoints,
fixed with explicit stat, and re-reviewed on this separate corrected snapshot. Rejected bytes
remain retained; the denied follow-up command was not retried.
The first corrected full gate failed an existing forced-build case while staging course.kmp
(Access is denied): 4584 passed/1 failed/6 skipped/178 deselected. One fresh case reproduced
it; fixed bounded case/file campaigns later passed with unchanged source, with and without
an observation wrapper. Original logs/project and the sole full-gate rerun are retained;
no failing syscall, handle owner, cause or repair established, and no security/test weakening.
Custom Wine placeholder/dispatch integration remains b2; saved-choice facade c3c, d/e/f/g,
b/c3/c/T07 and HC1 remain open. Documentation closeout needs its own full gate, exact Check
and actual-artifact/remote readback before final delivery.

###### [x] P5-T07c3b2 — Custom Wine placeholders and dispatch integration (commit `36953fa`)
Route explicit Linux Windows custom choices through b1's existing Wine/process owner.
Convert only file/directory/project substitution values using verified winepath, retain literal
user tokens and existing safe grammar, and keep c3a's native behavior and launch-only result.
**Acceptance:** full original b matrix, exact converted argv/cwd/environment, two independent
real synthetic-Wine requests/receipts, stale/malformed prerequisites and unsafe-text refusals
before dispatch, unchanged user bytes and built-in/native behavior. No saved-choice facade,
menu/UI or real Wine/editor-loading claim; c3c/d/e/f/HC1 remain open.

Delivered b2 only: optional explicit `wine_executable`/`wine_prefix` on `open_custom`; only a
canonical Linux `.exe` takes the Wine route and needs both values (no discovery). Referenced
file/dir/project values are converted once per value per request; literals, escaped braces,
empty specs/tokens and metacharacters are unchanged. Document/project/runtime checks run before
helpers and again before b1's complete-argv owner starts the editor. 769 focused and locked
Unicode fresh-install cases (125 new, including original b criteria), 38 independent boundary
cases (two real synthetic-Wine requests with a project folder separate from both document
folders), 25 parent plus 8 independent primary-assertion source controls; strict 7 actual files
per Windows/Linux target; immutable 590-file APPROVE. A first reviewer stopped on a provider
usage limit and supplied no verdict. The worker's process-proof helper read its receipt as soon
as the startup watch returned; a parent test-only fix polls the atomic receipt (Event-gated
RED/GREEN), with no production change. Full local 4710/6/178; exact Windows/Ubuntu Check (4716
selected) and both Integration jobs; actual Check ZIPs contain coverage.xml only. Synthetic
process/conversion evidence, not actual Wine/editor loading or saving. Parent b still needs its
own closure decision; c3c, c3/c/T07 and HC1 remain open.

###### [x] P5-T07c3c — Fresh saved-choice dispatch facade (commit `fd8b690`)
Load machine settings freshly for every explicit built-in versus custom choice; keep those
namespaces distinct even for equal ids, preserve built-in defaults/options/warnings and
use per-editor saved Wine prefix plus configured Wine. No silent fallback on damaged settings,
missing custom choices or stale paths. Leave worker/menu guards and controls to d/e/f.
**Acceptance:** changed settings affect the next launch, recognized corruption causes no
launch/writes, explicit choices select only their own namespace, native/Wine routes reach
existing owners, two real requests retain correct launch receipts and bytes. Re-run c3's
complete original criterion map across a/b/c before closing c3; c and T07 remain open.

###### [x] P5-T07c3c1 — Fresh saved-choice routing boundary (commit `3a9370d`)
Add an explicit built-in/custom choice and a settings-reading facade over the existing owners.
Load settings anew for each dispatch, retain exact namespaces for colliding ids, configured
executables/Wine/per-editor prefix and existing defaults/options/warnings. Never write settings
or fall back after recognized corruption, a missing custom choice or a stale configured path.
**Acceptance:** test-first fresh-setting/namespace/routing/refusal matrix, unchanged underlying
owners and settings bytes, exception/cause/interrupt identity and launch-only receipts. No GUI,
workers or new executor. Real-process saved-choice acceptance remains c3c2; c3c/c3 stay open.

Delivered c3c1 only: explicit namespaces and fresh settings route to existing native/Wine owners,
with unchanged receipts/errors/warnings and user settings. 876 focused/locked Unicode-install
cases (100 new), 47 independent routing boundaries, 15 routing + 2 diagnostic parent controls,
6 routing + 2 diagnostic independent controls; strict 9 actual files per Windows/Linux target.
Original immutable routing APPROVE plus exact assertion-delta approval; unchanged final 598-file
snapshot and diagnostic APPROVE (107 cases). Full local 4810/6/178; exact Check on both OSes
selected 4816 plus both Integration jobs. Both actual Check ZIPs contain coverage.xml only.
Initial local native-viewer policy block and later CLI connection timeout remain unexplained;
retained fake replay and fresh affected-file passes are nonreproduction, not a repair. The
one-line, test-first CLI status check improves diagnostic ordering only; no security-log read
ran or was retried. Failed classifier/equivalent-control attempts are retained, not counted.
Real-process saved-choice and original c3 criteria remain c3c2; b/c3c/c3/c/T07 and HC1 stay open.
No GUI, real Wine/editor loading or saving claim. Closeout requires its own full local gate,
exact hosted Check and actual artifact/clean-remote readback before final delivery.

###### [x] P5-T07c3c2 — Saved-choice process acceptance and combined dispatch review (commit `fd8b690`)
Drive the saved-choice facade through actual synthetic native/Wine helpers and detached
processes for two independent requests, including changed preferences and distinct project /
document folders. Map and rerun every original c3 criterion across a/b/c, including built-in
options/warnings, damaged settings, stale paths and unchanged bytes. Independently review the
combined evidence before deciding parent closures; real editor loading/save, d/e/f/HC1 stay open.
**Acceptance:** exact receipt argv/cwd/environment and separate launch/writer PIDs, original
criteria linked to executed tests, fresh installation, assertion controls and both-platform CI.
The criterion map is `docs/reference/EDITOR_DISPATCH_ACCEPTANCE.json`; every named test prefix
must match passing, non-skipped cases in the final combined run before a parent can close.

Delivered c3c2: 19 new synthetic-process acceptance cases over unchanged production; 895
combined and locked Unicode-install cases execute all 17 mapped original requirements.
Exact native/Wine helper/editor argv/cwd/prefix, two fresh settings requests, separate project
folders, independent launch/writer PIDs, typed post-success refusals/no runner entry and
unchanged input bytes are checked. Immutable 603-file APPROVE; 499 legacy source/test files
unchanged; 38 independent boundaries, 11 parent plus 7 distinct independent assertion controls,
strict 4 actual files per Windows/Linux target. Full local 4829/6/178; exact Check Windows
133041023051 (4820/15), Ubuntu 133041023437 (4821/14), both 4835 selected. Both actual Check
ZIPs contain coverage.xml only; unchanged product/test-only scope does not require Integration.
Two failed individual-log DNS retrievals were retained; the official run archive supplied
actual job totals without reruns. Initial policy refusals and the reviewer fixture-oracle
failure remain distinct retained evidence, not product/security repairs. The first closeout
gate passed 4828 and failed one native RiiStudio synthetic launch with an explicit Application
Control refusal; 6 skipped, 178 deselected. Three fresh unchanged affected-file processes
passed 4 cases each; original logs/freeze retained, no policy repair claimed. No security-log
read or policy change. Second closeout gate: 4827 passed / 2 failed / 6 skipped / 178
deselected; two existing CLI synthetic Blender launches explicitly refused by policy. Three
fresh unchanged combined CLI/diagnostic processes passed 9 cases each; retained failures and
second freeze are not a cause/repair claim. Only one final full attempt is scheduled after
those fixed probes. Combined original-criterion execution plus independent review establishes
only c3b/c3c/c3 dispatch closure; c/T07/d/e/f/g/HC1 remain open. Synthetic Wine is not actual
Wine/editor loading/save or desktop appearance. Separate closeout full gate, exact Check,
actual artifact inspection and clean remote readback are required before final delivery.

#### [x] P5-T07d — Joined editor preparation and application guards (closed by d3 map, commit `0206811`)
Prepare immutable available choices off the UI thread and re-read settings at dispatch.
Reuse the existing joined launch owner; preserve current-project/root/manifest identity,
read-only/busy/navigation/close protection and honest tool-aware result text.
**Acceptance:** worker-thread preparation/dispatch, fresh/damaged settings, stale and interrupted
startup/results, one owner, joined UI delivery and retained project locks on close timeout.
The preparation catalogue, joined-worker extension and application/result guards exceed one
small tested leaf. Keep every original criterion above; none closes from preparation alone.

##### [x] P5-T07d1 — Immutable editor-choice preparation boundary (commit `2efa2bd`)
Provide a blocking, read-only service that prepares immutable document-compatible built-in
and explicit custom choices from fresh machine settings. Preserve saved preference order,
namespace separation and exact sibling course.kcl eligibility; damaged settings fail closed.
Reuse existing catalogue/discovery contracts without launching tools or writing settings.
**Acceptance:** compatible/unsupported documents, preferred and colliding custom ids, fresh/
damaged settings, missing tools, exact collision eligibility and typed inspection failures;
independent review, source controls, fresh locked install and both-platform checks. This leaf
adds no menu, executor, application guard or claim of off-UI application dispatch.

Delivered d1: blocking read-only `gui/editor_launch.py` preparation service; 68 new / 772
combined and locked Unicode-install cases, seven all-primary assertion controls, strict
Windows/Linux typing and independent exact-code APPROVE (608-file snapshot). Full gate 4897
passed / 6 skipped / 178 deselected; exact Check Windows 133995303457 (4888/15) and Ubuntu
133995303062 (4889/14), both Integration jobs green, Check ZIPs coverage.xml only. A rare
existing Qt/GIL full-suite deadlock seen during d1 is TD-017, shelved to P13-T06 by the
owner. No menu, executor or application dispatch claim; d2/d3, d/c/T07 and HC1 stay open.

##### [x] P5-T07d2 — Joined editor preparation and dispatch ownership (commit `89b1190`)
Extend the existing launch owner for preparation and explicit saved-choice dispatch; no new
executor. Keep immutable request identity and exact receipts/errors/warnings, re-read settings
at dispatch and join before UI delivery. Reject stale preparation and preserve interruptions.
**Acceptance:** real joined worker preparation/dispatch, one owner across existing operations,
fresh/damaged settings, stale/queued results and uncertain native startup coverage.

Delivered d2: `LaunchController.prepare_editors`/`open_editor` on the existing joined
launch worker; dispatch re-reads settings via `open_saved`; only the latest delivered
preparation for the identical project/root/manifest and an offered choice authorises an
open. 18 new tests (real child, fresh/damaged settings, stale/queued, uncertain start),
15/15 assertion mutants, independent APPROVE after one revision. Full gate 4915 passed /
6 skipped / 178 deselected; exact Check Windows 134413060216 (4906/15) and Ubuntu
134413059754 (4907/14), ZIPs coverage.xml only. d3 must route editor results on
`editor_action` before `describe_launch` (else "Blender was started"). d, c, T07, HC1 open.

##### [x] P5-T07d3 — Application guards, result text and combined ownership acceptance (commit `0206811`)
Route current-project requests through the joined owner with memory-only eligibility and
captured project/root/manifest checks. Preserve read-only/busy/navigation/close protection
and tool-aware launch-only result wording; rerun all original d criteria together.
**Acceptance:** application service-to-worker flows, stale identity refusals, close-timeout
writer-lock retention, exact warnings/error wording and independently reviewed executable
original-criterion map. Only this combined proof may close d; menus remain e.

#### [x] P5-T07e — Mounted Open in… menus and missing-tool guidance (closed by e2 map, commit `16c27f2`)
Mount signal-only card/file actions using explicit supplied eligibility. Route requests through
T07d and offer a missing-editor dialog leading to the existing Tools page. Extract cohesive
card/menu code where existing files are near their size budgets; no duplicate executor.
Starting point (from d3): `Dashboard.editors` (`gui/dashboard_editors.py`) already offers
`prepare(document)`, `open(choice)` and the identity-checked `choices`; `views/dashboard.py`
is at 399/400 lines and `main_window.py` at 399, so extract before adding anything.
**Acceptance:** actual menu-to-worker flows, keyboard/disabled/stale/modal guards, visible
launch warnings/results, missing-tool navigation and no falsely offered Lorenzi action.
Card menus, the choice dialog and dispatch, plus missing-tool navigation through the main
window and visual acceptance, exceed one small tested leaf. Every criterion above stays with
the parent; neither child closes it alone.

##### [x] P5-T07e1 — Card Open in… action and editor-choice dialog (commit `bb5894a`)
Extract cohesive card-file and dashboard-assignment code to make room, then add a signal-only
"Open in…" card action for a checked, present single file. It prepares choices through d3's
presenter and offers them in a dialog: available editors open through the joined owner;
ineligible ones (Lorenzi without an exact sibling course.kcl) and missing ones are shown
disabled with their reason and hint. Read-only projects see choices but cannot open.
**Acceptance:** actual card-to-worker-to-dialog-to-launch flows on the joined owner, disabled
and stale/modal guards (project changed or work started while the dialog is open, a dialog
retired on rebind), keyboard choice and Escape, visible launch-only results and warnings, and
real preparation showing Lorenzi disabled without course.kcl and enabled with it. No new
executor; missing-tool navigation and visual evidence are e2.

##### [x] P5-T07e2 — Missing-tool guidance and Open in… acceptance (commit `16c27f2`)
Turn missing choices into a "Set up in Tools…" route to the existing Tools page (extracting
main-window code near its budget), and cover keyboard, minimum-width, enlarged-font and
light/dark local evidence. Map and rerun every e criterion across e1/e2 before closing e.
**Acceptance:** missing-tool dialog navigation with the window's busy/modal guards, the
mapped combined run, and inspected local screenshots (never uploaded).
Closure: `docs/reference/EDITOR_MENU_ACCEPTANCE.json` maps all ten P5-T07e criteria (e1 +
e2) to 45 targets (68 collected cases), every one passing and none skipped, and the exact
Check for `16c27f2` passed on Windows and Ubuntu, so P5-T07e is complete. P5-T07 stays open
(T07b, T07c, T07f, T07g). The before-offering course.kcl menu proof P5-T07b waited for now
exists (criterion e-no-false-lorenzi); b and c still close only through T07g's
original-criterion map.

#### [x] P5-T07f — Usable editor-preference and custom-tool controls (closed by f3 map, `27cc11d`)
Provide bounded controls for built-in defaults, custom argv templates and Wine prefixes during
T07; P5-T08 still owns the complete multipage Settings shell. Damaged settings cannot be
silently overwritten and changes must affect the next launch without restarting.
**Acceptance:** real UI save/reset/reopen, backups and unknown fields retained, error handling,
keyboard and minimum-width/enlarged-font light/dark local evidence.
Default-editor choices, custom-tool editing and Wine-prefix choices are three separate forms
over the same settings file, each with its own validation, worker and visual evidence; together
they exceed one small tested leaf. Every criterion above stays with the parent; it closes only
through f3's combined map.

##### [x] P5-T07f1 — Default-editor choices (Settings → Editors…) (commit `eef0b58`)
A Settings → Editors… window (made on first use, reread on reopen) lists each file kind with
more than one built-in editor and lets the user pick one as preferred or go back to the
default order. Reads and saves run on a worker; a damaged or newer settings file is shown and
nothing can be saved. Each save keeps a backup and every unknown field.
**Acceptance:** real window save/reset/reopen through the settings file, backup and unknown
fields (top-level and inside `editor_preferences`) retained, damaged file and save-failure
banners with controls off, busy state, keyboard reach, and the next Open in… on a card listing
the preferred editor first without restarting; minimum-width/enlarged-font light/dark local
screenshots inspected.

##### [x] P5-T07f2 — Custom editor programs (commits `4558734`, repair `7a07831`)
In the same window, add, edit and remove custom tools (name, program, argument template using
only `{file}`, `{dir}`, `{project}`), with the model's own validation errors shown before
anything is saved.
**Acceptance:** real save/edit/remove/reopen with backups and unknown record fields kept,
invalid name/program/template refused with the reason, damaged-file guard, keyboard and
visual evidence, and the next Open in… offering the saved custom tool without restarting.

##### [x] P5-T07f3 — Wine-prefix choices and f acceptance (commit `27cc11d`)
Per-editor Wine-prefix folder choice and clear for built-in and custom Windows editors, shown
on every platform but explained as Linux-only, then map and rerun every f criterion across
f1–f3 before closing f.
**Acceptance:** real choose/clear/reopen with backups and unknown fields kept, damaged-file
guard, the next Linux-path preparation (fake platform) using the saved prefix without
restarting, keyboard and visual evidence, and the combined executable f criterion map.

Closure: `docs/reference/EDITOR_SETTINGS_ACCEPTANCE.json` maps all eleven P5-T07f criteria
(f1-f3) to 58 test functions (90 collected cases, 88 matched, every one passing and none
skipped), and the exact Check for `27cc11d` passed on Windows and Ubuntu, so P5-T07f is
complete. P5-T07 stays open (T07b, T07c, T07g); T07c's custom-tool and Wine-prefix settings
now have their controls, but b and c still close only through T07g's original-criterion map.

#### [x] P5-T07g — Original Open in… acceptance and guide (commit `0acdf00`)
Re-run every original P5-T07 criterion across its leaves, including fake GUI tools on Windows
and Linux, two-file/two-launch argument order, all default targets/custom choices, exact
course.kcl eligibility, Tools guidance and configured next-launch behavior. Document launch-
only wording, HC1 manual-run requirement and any unverified native-desktop behavior.
**Acceptance:** executable original-criterion map, independent review, full gates and exact
hosted CI. Only then close P5-T07; no original acceptance is removed by this split.

Closure: `docs/reference/OPEN_IN_ACCEPTANCE.json` maps all eighteen original P5-T07, T07b,
T07c and T07g criteria to 91 test targets; one combined run of all five editor maps (1263
cases, none skipped) matched every target, and the exact Check for `0acdf00` passed on Windows
and Ubuntu. P5-T07b, P5-T07c and P5-T07 are complete. The user guide is
`docs/user/OPEN_IN.md`. Real editor loading/saving, real Wine loading and desktop appearance
stay unverified by automation and are HC1's manual run (P5-HC1 stays open).

### [x] P5-T08 — Settings dialog (closed by f map, `3d9690b`)
Pages: Tools (from P2-T07), Build (compression profiles, parallelism, `_d` variant default, auto-add),
Editors (Open-in mapping, custom tools), Appearance, Advanced (show commands, extra args, log
retention, dev mode).
**Acceptance:** settings persist; changing compression profile changes the next build's command.

Split 2026-11-23 (owner's choice: one Settings window with a page list on the left holding
all five pages; the existing Tools and Editors windows move into it). The original text and
acceptance above stay; P5-T08 closes only through P5-T08f's map.

#### [x] P5-T08a — One Settings window with a page list (commits `3f46b57`, repair `54e37e3`)
One `Settings` window: a page list on the left and the pages on the right, Tools and Editors
for now (Build, Appearance and Advanced join in b-e, in the order of the original text).
Settings → Settings… (standard Preferences shortcut) opens it at the last page shown;
Settings → Tools… and Settings → Editors… open it at that page, and a choice dialog's
"Set up … in Tools…" still selects that tool. A page is made the first time it is shown
(Tools starts its check then) and refreshed, as before, each time it is opened again. The
window keeps fitting an 800×600 screen at enlarged fonts and still refits on LayoutRequest.
**Acceptance:** every existing Tools and Editors test passes through the new window (helpers
updated, no assertion weakened); page list, keyboard and menu tests; visual tests of both
pages on a real 800×600 screen; mutation proof; review; full gate; exact Check.

#### [x] P5-T08b — Build page: the project's build settings (commits `01e326f`, repair `a6d7e85`)
Test and release compression, the `_d` copy and auto-add for the open project, saved to
the project file `ctstudio.toml` on a joined worker with the same stale-input checks as
Project details (unknown keys kept; comments are not kept, as on every save (ADR-020);
a backup per save; read-only and busy projects refused; no project: explained). The page
has explicit Save and Undo changes (one backup per save, not per click); closing the window
with unsaved changes asks Save / Discard / Cancel. Page order: Tools, Build, Editors.
**Acceptance:** settings persist across reopen; changing the test compression changes the
next test build's `wszst create` command (fake tool argv), and the release one likewise.

#### [x] P5-T08c — Build page: parallel steps on this computer (commit `02f849a`)
How many build steps may run at once (machine setting in `settings.json`, default
`min(4, cpu count)` as today), used by GUI builds and by `ctstudio build`.
**Acceptance:** setting persists; the next build's runner uses it (GUI and CLI); a damaged
or newer settings file is refused, never overwritten.

#### [x] P5-T08d — Appearance page (commit `7004c29`)
Colour scheme only (owner's choice, 2026-11-23): Follow system, Light or Dark. Text size
and window size/position memory are not part of this leaf.
**Acceptance:** the chosen settings persist and apply at the next start (and immediately
where Qt allows), with light/dark and enlarged-font evidence.

#### [x] P5-T08e — Advanced page (closed by e1-e3, `efa4add`)
Show tool commands in the build log, log-file retention and dev mode (the stall watchdog,
today `CTSTUDIO_DEV=1`). The open project's reserved `[build] extra_wszst_args` is shown
read-only and labelled as not used yet (owner's choice, 2026-11-23); P7-T06 wires it and
makes it editable.
**Acceptance:** each setting persists and takes effect (build log rows, old log files
removed beyond the retention, watchdog at the next start).

Split 2026-11-24 into three leaves, one setting each (each needs its own taking-effect
proof, and the build-log one changes core build code); the text above stays and closes
with e3.

##### [x] P5-T08e1 — Advanced page: tool commands in the build log (commit `fa93f6c`)
Settings → Advanced (page list: Tools, Build, Editors, Appearance, Advanced). A machine
setting in `settings.json` decides whether the dashboard's build log shows the tool command
rows (shown, as today, unless turned off); the build log file on disk always has them. Read
fresh for every GUI build. The open project's reserved `[build] extra_wszst_args` is shown
read-only, labelled as not used yet; no project: explained.
**Acceptance:** the setting persists; with it off the next GUI build's log shows no command
rows while the build log file still has them, and with it on they show; a damaged or newer
settings file is refused, never overwritten; the reserved arguments are shown as saved.

##### [x] P5-T08e2 — Advanced page: how many build logs are kept (commit `eea0bc0`)
A machine setting for how many `.ctstudio/logs/build-*.log` files each project keeps
(today a fixed 20), used by GUI builds and `ctstudio build`.
**Acceptance:** the setting persists; after the next build (GUI and CLI) only that many
build logs remain; a damaged settings file keeps the default.

##### [x] P5-T08e3 — Advanced page: developer mode (commit `efa4add`)
A machine setting that turns the stall watchdog on from the next start (today only
`CTSTUDIO_DEV=1`, which keeps working).
**Acceptance:** the setting persists; the next start runs the watchdog when it is on and
not when it is off (without `CTSTUDIO_DEV`).

#### [x] P5-T08f — Original Settings acceptance and guide (commit `3d9690b`)
Map every original P5-T08 criterion and each leaf's acceptance to executable tests, rerun
them together, and write `docs/user/SETTINGS.md` (tested against the code like the Open in…
guide). **Acceptance:** criterion map, review, full gate, exact Check; only then close P5-T08.

Closure: `docs/reference/SETTINGS_ACCEPTANCE.json` maps the original P5-T08 criteria (all five
pages, settings persist, the compression profile changes the next build's command, Advanced's
show commands, extra args, log retention and dev mode) and every leaf's acceptance (a-e3) plus
the guide: 14 requirements, 119 test targets. One combined run with
`EDITOR_SETTINGS_ACCEPTANCE.json` (42 files, 503 cases, none skipped) matched every target, and
the exact Check for `3d9690b` passed on Windows and Ubuntu, so P5-T08 is complete. The user
guide is `docs/user/SETTINGS.md`. Owner choices kept: Appearance is the colour scheme only, and
`extra_wszst_args` is shown read-only until P7-T06.

### [x] P5-T09 — GUI end-to-end test & screenshot review (closed by T09a + T09b, `fe528f9`)
pytest-qt: new project → assign fixture files (manual mode) → build with fakes → Ready statuses →
issue shown → open-in invoked. Save screenshots to `tests/artifacts/screens/`. If your model accepts
images, review the screenshots against the UI checklist in REVIEW_CHECKLIST.md; otherwise list them
for the human at HC1.
**Acceptance:** test green headless on Linux and Windows CI.

Split 2026-11-25 into two leaves (one flow is about 340 lines with screenshots and review).
"Ready statuses", as the owner decided on 2026-11-25: a part you assign shows "your own
file" (manual parts are never judged Ready), Objects shows "ready", and every other card's
status is pinned exactly. The parts CT Studio generates (course model, minimap, skybox,
post-effects) and Track info (no window sets an author yet) reach Ready in the phases that
add them, whose own end-to-end tests check it. The build uses the real stage, assemble and
validate steps on the fake Wiimm tools for the assigned parts (the full plan needs every
part manual, and the fakes cannot analyse or check an archive, so analyze/check replay the
recorded real output for the same committed course.kcl and course.kmp).

#### [x] P5-T09a — End-to-end flow: new project to issues (commit `98f2b9d`)
One pytest-qt test on the real main window: the New project wizard creates a project in a
test folder; Collision is assigned through Choose file… and Course data by a drop (manual
mode, committed fixture files); a test build runs on the fake tools; the statuses and the
issues panel show the new check. Light-theme screenshots `p5-t09-*.png`.
**Acceptance:** the flow test passes headless on Linux and Windows CI; after the build the
assigned parts show "your own file", Objects "ready" and the other cards their pinned
statuses; the issues panel shows the check's findings grouped by part.

#### [x] P5-T09b — End-to-end flow: Open in… and screenshot review (commit `fe528f9`)
The same flow continues: an editor added in Settings → Editors… (a harmless test program) is
started with Collision's file through Open in…; dark and enlarged-font screenshots; the
screenshots reviewed against REVIEW_CHECKLIST.md §5 and listed for HC1.
**Acceptance:** the program receives exactly the project's course.kcl and the dashboard says
it was started; review notes recorded; Linux and Windows CI green.
Already noted by the P5-T09a review for this one, from its pictures: the wizard summary
wraps the project folder straight after "C:"; the wizard says "Replaces: Luigi Circuit
(Mushroom Cup, track 1)" while the dashboard says "Replaces beginner_course.szs"; a card just
assigned shows both "using files/course.kmp" and "Now using files/course.kmp (a copy of
course.kmp)"; the first card's note disappears when a second card is assigned.

### [ ] P5-T10 — UX polish pass
Empty states, error dialogs with "Copy details", plain-language tooltips for every component, focus
order, window size/position persistence, high-DPI check, no text truncation at 1280×720.
Starts from the P5-T09b picture review (`docs/reviews/P5_T09_SCREENSHOTS.md`): card action
weight and the build buttons out of view at 1280×720, "Replaces" naming the file instead of
the track, long folder paths cut off when a folder name has no space or hyphen (wizard
summary, dashboard "Project folder", launch notice), the header's height at 150 %, the repeated "using …"/
"Now using …" lines, the assign note cleared by the next assignment, "Open in Blender"
disabled without a reason, and the Open in… dialog naming the file only in its title bar
and never the part.
**Acceptance:** checklist items ticked in the phase review doc.

Split 2026-11-25 into leaves (research against HEAD `a1fd1a1`: window size/position is
not remembered anywhere; there are no error dialogs and errors' details never reach the
GUI; empty states and focus order are mostly done). Leaves marked "owner question" wait for
the owner's answer (asked 2026-11-25, unanswered; options in STATUS Plan changes) and are
written to be confirmed before they start.

#### [x] P5-T10a — Plain words on the dashboard (commit `6cde29b`)
"Replaces" names the track (Luigi Circuit, Mushroom Cup) with the file in the tooltip;
"Open in Blender" says why it is off (no Blender file: choose one in Project details…;
read-only: why); the Open in… dialog names the part ("Open Collision (course.kcl) in…") in
its title and heading; tooltips for Refresh, Copy project folder and the two build buttons.
**Acceptance:** tests on each text and tooltip in each state, and every visible dashboard
button has a non-empty tooltip.

#### [x] P5-T10b — Build buttons always visible (owner decision D1) (commit `139595d`)
A build bar pinned to the bottom of the dashboard (Build test, Build release, Cancel and the
build's progress), outside the scrolling card area. **Acceptance:** at 1280×720 and 800×600,
normal and enlarged, the build buttons are inside the window without scrolling; shortcuts,
tooltips and enabled states unchanged.

#### [x] P5-T10c — Long paths never cut off (owner decision D2) (commit `4353e3a`)
Paths on one line, shortened in the middle (`C:\Users\…\course.kcl`), the full path on hover
and in Copy; the started notice names the file relative to the project. **Acceptance:** a
path of 300 characters with no break points stays inside its card at 800 px; tooltip and
Copy give the whole path.

#### [x] P5-T10d — Compact header (commit `551c854`, repair `115ab3f`)
The access line only for read-only projects, one row of header buttons, no stale "Statuses
checked." **Acceptance:** at 1280×720 with the enlarged font the first card starts within
about 40 % of the height (about 70 % today). After T10b and T10c.

#### [x] P5-T10e — Card notes and actions (owner decision D3) (commit `6262dd4`)
A card's note says only what is new ("using …" is not repeated as "Now using …") and stays
until that card changes; the duplicate "Copy path" button goes, one way to copy remains.
**Acceptance:** no card shows the same fact twice; a note survives other cards' changes and
clears when its own card changes; one copy action per card.

#### [ ] P5-T10f — Error details and unexpected errors (owner decision D4)
Inline error messages stay, with "Copy details" when the error has details (a
`CTStudioError`'s details reach the GUI); a dialog only for unexpected crashes (an exception
nothing handled), also with Copy details, and logged. **Acceptance:** a failing build and an
unreadable settings file offer Copy details with the details text; an unhandled exception
in a slot shows one dialog, is logged, and the app keeps running.

#### P5-T10g — Remember window size and position: moved to P13-T09 (owner decision D5)
Not for now; the owner wants to decide after hands-on testing.

#### [ ] P5-T10h — High-DPI evidence
Populated dashboard and Settings pictures at 1.5× and 2×. **Acceptance:** no clipped labels;
status icons drawn at least at the scale. Tests only unless something turns up.

#### [x] P5-T10i — Settings → Tools at wide fonts (TD-022 core) (commits `93ebd8c`, `1008740`)
Tools buttons in two rows, Tab leaves the Tools table, tooltips on shortened cells, and the
1280×720 / 150 % Tools pictures TD-007 asked for. **Acceptance:** a real Tab walk; Tools fits
800 px at 132 % stretch in Verdana. The widest-font sweep stays TD-022 → P13-T06.

#### [ ] P5-T10j — Close the UX pass
Rerun the §5 pictures (light/dark, 1280×720, 150 %) into `docs/reviews/P5_T10_UX.md`, which
P5-GATE's phase review links. **Acceptance:** every REVIEW_CHECKLIST §5 row is "Yes" or names
its later owner task.

### [ ] P5-GATE — Phase review
### [ ] P5-HC1 — Human checkpoint 1 (see HUMAN_CHECKPOINTS.md)
### [ ] P5-DEEPCLEAN — Deep Clean #1 (REVIEW_CHECKLIST.md)
