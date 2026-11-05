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

### [ ] P5-T03 — Dashboard
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

#### [ ] P5-T03i — Dashboard launch ownership and controls
Wire Open in Blender and reveal-location actions through joined background work.
**Acceptance:** off-thread discovery/launching, current-project/lock ownership through completion,
busy/read-only rules, visible failures without clearing last-good cards, keyboard and screenshots.

#### [ ] P5-T03e — Build controls and live log
Build test/release, cancel, progress, last result and collapsible bounded/virtualised log with
command copying, using BuildController. **Acceptance:** fake-build events update cards and log
live; shortcuts, cancel/failure behavior and light/dark screenshots. TD-012 must be closed first.

Original combined scope:
Header: project name, slot selector, source file + "Open in Blender". Component cards (status icon +
colour + text, one-line summary, primary action, "Open in ▾", overflow: Reveal in file manager, Copy
path, Mode: Auto/Manual/Template, Settings…). Footer build bar: Build test SZS, Release build,
Cancel, progress, last result. Collapsible virtualised log panel with "Copy command" on command lines.
**Acceptance:** cards reflect status changes live during a fake build; keyboard navigation works;
screenshots in light and dark themes. Before the Build page uses the core runner, close TD-012:
prove a failed UI event callback cannot leave cached outputs with missing part-state records.

### [ ] P5-T04 — Manual file assignment
Drag & drop onto a card or "Choose file…". Validate type (magic). Copy into `files/` by default, or
"reference in place" option. Replacing an existing manual file backs up the old one.
**Acceptance:** tests: wrong type rejected with explanation; backup created; manifest updated.

### [ ] P5-T05 — Issues panel
Grouped by component and severity; hint text; wiki link; "Copy report". Clicking an issue focuses
the component card.
**Acceptance:** populated from recorded `wszst check` outputs in tests.

### [ ] P5-T06 — File watching & external-edit detection
WatcherBridge wraps core watcher (watchfiles thread) → debounced status refresh. When a generated
stage file changes externally → `EditedExternally` banner on the card with the three choices from
ARCHITECTURE §8 (the capture mechanism itself arrives in P7; here implement Lock-as-manual and
Discard-with-backup).
**Acceptance:** test modifies a generated file → banner appears within 2 s → Lock-as-manual copies to
`files/` and switches mode.

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
