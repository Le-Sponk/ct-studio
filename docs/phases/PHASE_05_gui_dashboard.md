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

### [ ] P5-T07 — "Open in…" framework
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

#### [ ] P5-T07b — Built-in file dispatch and collision prerequisite
Extend existing adapters for .szs, preserve OS argv/Wine/warnings/one-file/new-process rules,
and enforce exact lowercase sibling course.kcl before offering Lorenzi. No process-liveness,
window-title or RiiStudio stdout claim of successful document loading.
**Acceptance:** fake tools on both OS branches, options after path, two files/two dispatches,
missing files/editors/prefixes and collision prerequisites leave user files unchanged.
Split below after native capability measurement and a >400-line combined estimate; every
original criterion remains required. P5-T07b stays open until both leaves are verified.

##### [ ] P5-T07b1 — Exact Lorenzi collision prerequisite
Refuse Lorenzi dispatch unless a regular sibling file is named literally course.kcl, including
on case-insensitive Windows filesystems. Inspect only the document's own folder, before editor
lookup, Wine or process launch; turn inspection errors into actionable typed errors. Preserve
existing eligible-editor, Unicode, Wine-prefix and argument-order regression assertions.
**Acceptance:** missing/wrong-case/directory/uninspectable sibling, no working-directory
fallback, independent documents and fresh dispatch checks, two eligible requests/two detached
launches, unchanged user bytes; independent review, assertion-caught controls, strict actual-
file Windows/Linux typing, fresh install, full gates and exact Check/Integration.
Menu eligibility and worker-thread preparation remain T07d/e, not completed by this adapter guard.

##### [ ] P5-T07b2 — Measured SZS dispatch
Enable BrawlCrate/RiiStudio .szs using their existing verified positional argv. Native Windows
capability is measured with synthetic data; Linux/Wine SZS document loading remains unmeasured.
**Acceptance:** both OS argv branches, options after path, one file/new process per request,
two requests/two real-runner dispatches, missing document/editor/prefix refusals and unchanged
bytes. Preserve launch-only receipts and Unicode warnings; never infer document loading from
process/window/stdout. Retain HC1 manual-run requirement and all parent acceptance.

#### [ ] P5-T07c — Custom-tool and Wine-prefix preferences and dispatch
Persist custom editors using existing CustomTool argv templates and machine-specific Wine
prefix choices. Validate damage, preserve unknown fields/backups, and execute only through
core adapters with argv tokens, never shell parsing or another process owner.
**Acceptance:** safe placeholders/Unicode argv, explicit custom choice, native/Wine routes,
malformed/stale preferences fail closed; independent launch receipts and separate processes.

#### [ ] P5-T07d — Joined editor preparation and application guards
Prepare immutable available choices off the UI thread and re-read settings at dispatch.
Reuse the existing joined launch owner; preserve current-project/root/manifest identity,
read-only/busy/navigation/close protection and honest tool-aware result text.
**Acceptance:** worker-thread preparation/dispatch, fresh/damaged settings, stale and interrupted
startup/results, one owner, joined UI delivery and retained project locks on close timeout.

#### [ ] P5-T07e — Mounted Open in… menus and missing-tool guidance
Mount signal-only card/file actions using explicit supplied eligibility. Route requests through
T07d and offer a missing-editor dialog leading to the existing Tools page. Extract cohesive
card/menu code where existing files are near their size budgets; no duplicate executor.
**Acceptance:** actual menu-to-worker flows, keyboard/disabled/stale/modal guards, visible
launch warnings/results, missing-tool navigation and no falsely offered Lorenzi action.

#### [ ] P5-T07f — Usable editor-preference and custom-tool controls
Provide bounded controls for built-in defaults, custom argv templates and Wine prefixes during
T07; P5-T08 still owns the complete multipage Settings shell. Damaged settings cannot be
silently overwritten and changes must affect the next launch without restarting.
**Acceptance:** real UI save/reset/reopen, backups and unknown fields retained, error handling,
keyboard and minimum-width/enlarged-font light/dark local evidence.

#### [ ] P5-T07g — Original Open in… acceptance and guide
Re-run every original P5-T07 criterion across its leaves, including fake GUI tools on Windows
and Linux, two-file/two-launch argument order, all default targets/custom choices, exact
course.kcl eligibility, Tools guidance and configured next-launch behavior. Document launch-
only wording, HC1 manual-run requirement and any unverified native-desktop behavior.
**Acceptance:** executable original-criterion map, independent review, full gates and exact
hosted CI. Only then close P5-T07; no original acceptance is removed by this split.

### [ ] P5-T08 — Settings dialog
Pages: Tools (from P2-T07), Build (compression profiles, parallelism, `_d` variant default, auto-add),
Editors (Open-in mapping, custom tools), Appearance, Advanced (show commands, extra args, log
retention, dev mode).
**Acceptance:** settings persist; changing compression profile changes the next build's command.

### [ ] P5-T09 — GUI end-to-end test & screenshot review
pytest-qt: new project → assign fixture files (manual mode) → build with fakes → Ready statuses →
issue shown → open-in invoked. Save screenshots to `tests/artifacts/screens/`. If your model accepts
images, review the screenshots against the UI checklist in REVIEW_CHECKLIST.md; otherwise list them
for the human at HC1.
**Acceptance:** test green headless on Linux and Windows CI.

### [ ] P5-T10 — UX polish pass
Empty states, error dialogs with "Copy details", plain-language tooltips for every component, focus
order, window size/position persistence, high-DPI check, no text truncation at 1280×720.
**Acceptance:** checklist items ticked in the phase review doc.

### [ ] P5-GATE — Phase review
### [ ] P5-HC1 — Human checkpoint 1 (see HUMAN_CHECKPOINTS.md)
### [ ] P5-DEEPCLEAN — Deep Clean #1 (REVIEW_CHECKLIST.md)
