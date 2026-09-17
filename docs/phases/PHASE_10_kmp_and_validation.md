# Phase 10 — KMP workflow & validation hub

**Goal:** milestone M3 — the app tells the user exactly what KMP data is missing, opens the right
editor with the right files, picks up saves automatically, and presents every problem in one list.
**Read first:** MKW_DOMAIN.md (KMP), SPIKES.md §S7, TOOLS.md launch contracts.
**Exit:** fixture KMP checklist accurate; editor workflow verified at HC3.

### [ ] P10-T01 — KMP reader (read-only)
`core/formats/kmp.py`: header + section table; records for KTPT, ENPT/ENPH, ITPT/ITPH, CKPT/CKPH, GOBJ,
POTI, AREA, CAME, JGPT, CNPT, MSPT, STGI into numpy structured arrays / small dataclasses. Record
layouts taken from authoritative documentation (Wiimms KMP guide, mkwiiki KMP page) and
cross-validated against `wkmpt` text output — never from memory. Writes always go through external
tools.
**Acceptance:** integration cross-validation on the fixture KMP; fuzz-ish test (truncated/corrupt
files → `ParseError`, no crash).

### [ ] P10-T02 — KMP readiness rules
`core/validation/kmp_rules.py` — data-driven rules with severity, message, hint, wiki link:
start position present; checkpoints present with at least one lap counter; checkpoint groups linked;
respawn points present and referenced; enemy routes present; item routes present; stage info present
(lap count, etc.); opening/replay cameras present (warning); cannon triggers in KCL ⇒ cannon points in
KMP; coordinates within limits; objects referenced but no auto-add library (from P8). Do not
re-implement Wiimms' deep checks — include `wszst check` results alongside.
**Acceptance:** rule tests on crafted KMPs (built via `wkmpt` from text in test setup).

### [ ] P10-T03 — KMP card & page
Card: section counts + checklist summary ("4 of 7 required items done"). Page: checklist with
explanations, section table, overlay toggle.
**Acceptance:** pytest-qt with fixture; screenshots.

### [ ] P10-T04 — KMP overlay in preview
Layer: start position, checkpoint pairs (coloured by type, lap counter highlighted), enemy/item routes
as polylines with direction arrows, respawns, cannons, objects as markers, areas as boxes (toggle).
**Acceptance:** screenshot test; performance unaffected for typical KMP sizes.

### [ ] P10-T05 — Editor workspace & round-trip
"Edit KMP" prepares the editing location according to the launch contract (e.g. ensure `course.kcl`
sits next to `course.kmp` for Lorenzi's editor — use a workspace folder under `.ts/kmp_workspace/` with
the KCL copied and the KMP either edited in place in `files/` or copied back on save), launches the
preferred editor, shows an instruction panel, watches for saves, validates, updates status. If the
editor can't take a file argument: reveal the folder, copy the path to the clipboard, explain.
**Acceptance:** watcher round-trip test with a fake editor that rewrites the KMP; HC3 manual test.

### [ ] P10-T06 — Starter KMP
Generate a minimal valid KMP text for `wkmpt` (start position at a chosen or auto-suggested point —
e.g. a road triangle near the KCL's road centroid — facing a user-chosen direction; stage info
defaults) so beginners open the editor on a valid file. Clearly labelled "starter — add checkpoints,
routes, respawns, cameras". Never overwrite an existing KMP without backup + confirmation.
**Acceptance:** generated file passes `wkmpt` encode; `wszst check` output recorded for it.

### [ ] P10-T07 — Validation hub
Unified Issues view across nodes (wszst check, KCL checks, texture/material warnings, KMP rules, bridge
errors) with filters, severity counts in the header, "Copy report" (markdown), mapping from common
symptoms to the mkwiiki "Common Crash Causes" style hints where confidently applicable.
**Acceptance:** tests; no duplicate issues when two sources report the same problem (dedupe by code +
location).

### [ ] P10-GATE — Phase review
### [ ] P10-HC3 — Human checkpoint 3
