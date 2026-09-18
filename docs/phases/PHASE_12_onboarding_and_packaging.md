# Phase 12 — Onboarding, packaging & installers

**Goal:** milestone M4 — a friend can install and use it.

### [ ] P12-T01 — First-run wizard
Steps: welcome → tools check (per tool: found/missing, official download link, "I installed it —
re-check", Browse…) → optional auto-download for tools whose licence and hosting allow it (Wiimms SZS
Tools, ABMatt), from official URLs, with checksum verification
when published and explicit consent → Blender detection + optional add-on install into the user's
Blender (opt-in, explained) → optional game files setup (P8-T04) → done.
**RiiStudio is never bundled** (ADR-004, human decision): show detection plus a link to
the official releases page and offer an **optional user-initiated** download from the
upstream URL. It must not go into the installer, and the app must stay fully usable
with ABMatt alone when the user declines. Asking the maintainer for an explicit LICENSE
so it *could* be bundled one day is a question for this phase, not a blocker.
**Acceptance:** pytest-qt flows with fakes; downloads mocked; no network in unit tests.

### [ ] P12-T02 — In-app help
Each card/page: "What is this?" popover with plain-language text and mkwiiki link; "What will this
run?" shows the exact commands for the next build step.
**Acceptance:** every component has help text (test enumerates registry).

### [ ] P12-T03 — Packaging
PyInstaller one-folder specs for Windows and Linux; exclude unused Qt modules (WebEngine, Quick/QML,
3D, Multimedia, etc. unless used); include `blender_bridge/`, the add-on submodule, licences,
`THIRD_PARTY_NOTICES.md`. **Do not ship RiiStudio/rszst in any artefact** (ADR-004).
Windows: zip + Inno Setup installer (per-user install, no admin). Linux:
AppImage (or tar.gz if AppImage proves fragile — document). Tag-triggered release workflow.
**Acceptance:** CI produces artefacts on tag; sizes recorded; `--offscreen-smoke` passes on packaged
builds in CI; cold-start time measured.

### [ ] P12-T04 — User documentation
`docs/user/`: quick start (10 minutes), Blender conventions (collections, `_F####` names, scale),
each component, textures & transparency guide, working with BrawlCrate/RiiStudio edits, KMP workflow,
testing in Dolphin, troubleshooting (port the add-on README's troubleshooting: sandboxed Blender,
tool detection, BrawlCrate OpenGL errors in VMs), FAQ.
**Acceptance:** reviewed against the UI (screenshots up to date).

### [ ] P12-GATE — Phase review
### [ ] P12-HC4 — Human checkpoint 4
