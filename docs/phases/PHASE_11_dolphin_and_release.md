# Phase 11 — Dolphin testing & release build

**Goal:** one click from change to racing; a clean release artefact for sharing the track.
**Read first:** SPIKES.md §S8 (and re-verify it — Dolphin changes often), MKW_DOMAIN.md (slots, legal).

### [ ] P11-T01 — Test setup wizard
Implement the S8-recommended method. Typical shape: user selects their own MKW disc image → the app
explains disk usage and asks consent → one-time extraction/preparation into the user data dir (via
`dolphin-tool` or Wiimms ISO Tools if S8 chose it) → verification. Store paths in user settings.
**Acceptance:** tests with fakes for every step; real run is `realdata` + HC3/HC4.

### [ ] P11-T02 — Build & launch
"Build & launch Dolphin": test build → install the SZS into the test setup for the project's slot
(backup/restore the original file in the test copy; never touch the user's original image) → launch
Dolphin detached with the right arguments → optionally close the previous Dolphin started by the app
(ask once, remember).
**Acceptance:** argument/path construction tests on both OSes; process handling tests with a fake
Dolphin.

### [ ] P11-T03 — Slot helper
Run `wszst slots` on the built SZS; show compatible slots in the slot picker (badge "compatible"/
"may not work"); warn when the chosen slot is flagged; short explanation + wiki link.
**Acceptance:** parser tests on recordings; UI test.

### [ ] P11-T04 — Release build
Release profile: best compression, `_d` variant, strict validation (errors block, warnings listed),
release checklist (all components Ready, KMP checklist complete or explicitly waived), output naming
template (default `{name} v{version} [{author}].szs` — confirm conventions against current mkwiiki
guidance), optional zip with a generated `README.txt` (credits, version, slot).
**Acceptance:** fixture release build test; checklist UI test.

### [ ] P11-GATE — Phase review
