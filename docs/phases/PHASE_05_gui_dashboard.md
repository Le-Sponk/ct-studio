# Phase 5 — GUI shell & dashboard (manual-mode MVP)

**Goal:** milestone M1 in the GUI — create a project, assign files, click Build, get an SZS, see
issues, open any file in the right tool.
**Exit:** pytest-qt end-to-end flow passes headless; screenshots reviewed; HC1 passed; Deep Clean #1.
UI style: clean, calm, native-feeling Qt; few colours (status colours only); generous spacing;
every control has a tooltip in plain language. Consistent spacing scale, one accent colour, no
decorative clutter. Status must never be conveyed by colour alone (icon + text too).

### [ ] P5-T01 — GUI services & threading
`gui/services.py`: holds current Project, ToolRegistry, BuildController (QObject running the core
runner on a dedicated worker thread, re-emitting core events as signals), StatusService (evaluates
status on a worker, debounced), WatcherBridge (P5-T06). Dev-mode UI stall watchdog (> 100 ms logs a
stack). Rule: views never call blocking core functions directly.
**Acceptance:** unit tests for signal marshalling with fakes; watchdog test that detects an injected
`time.sleep(0.2)` on the UI thread.

### [ ] P5-T02 — Welcome & new-project wizard
Welcome: New, Open, Recent (with missing-folder handling). Wizard pages: name + folder; source
(.blend optional, can be added later); slot picker (search by display name; default Luigi Circuit);
summary → create.
**Acceptance:** pytest-qt flow creates a project on disk; screenshot artifacts of each page.

### [ ] P5-T03 — Dashboard
Header: project name, slot selector, source file + "Open in Blender". Component cards (status icon +
colour + text, one-line summary, primary action, "Open in ▾", overflow: Reveal in file manager, Copy
path, Mode: Auto/Manual/Template, Settings…). Footer build bar: Build test SZS, Release build,
Cancel, progress, last result. Collapsible virtualised log panel with "Copy command" on command lines.
**Acceptance:** cards reflect status changes live during a fake build; keyboard navigation works;
screenshots in light and dark themes.

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
