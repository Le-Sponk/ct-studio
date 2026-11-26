# Phase 13 — Final optimisation & hardening (Deep Clean #3)

**Goal:** meet every budget in ARCHITECTURE §15 with evidence, and leave the codebase smaller and
simpler than it was at the start of the phase.
**Acceptance for every task here:** before/after measurements (or findings lists) recorded in
`docs/dev/BENCHMARKS.md` or `docs/reviews/DEEP_CLEAN_3.md`; `check.py` and integration CI green;
no behaviour change without a test proving it.

### [ ] P13-T01 — Profile the real workflow
pyinstrument on CLI builds of the fixture and (if available) a `realdata` track; py-spy on the GUI
during build + preview. Fix the top 5 hotspots; record before/after in BENCHMARKS.md.
### [ ] P13-T02 — Start-up time
`python -X importtime`; lazy-import numpy/Pillow/moderngl/watchfiles on first use; defer tool
discovery until after first paint; budget < 2 s packaged cold start.
### [ ] P13-T03 — Memory, threads, GL resources
Open/close project 20×, run 10 builds, toggle preview: RSS, thread count, GL object counts stable.
### [ ] P13-T04 — Code health sweep
vulture, radon/xenon, pylint duplicate-code, coverage gaps in core (< 85 % modules), remove speculative
abstractions and dead feature flags, merge duplicate helpers, delete stale docs.
### [ ] P13-T05 — Dependency & size audit
Remove unused dependencies; check licences; package size budget; exclude unused Qt plugins/translations.
### [ ] P13-T06 — Robustness
hypothesis-based fuzzing for KCL/KMP readers and TOML loading; kill-during-write tests for atomicity;
watcher + build race review; long-path tests on Windows. Includes TD-017 (rare full-suite Qt/GIL
deadlock during worker-thread garbage collection; see STATUS Tech debt): reproduce it first, then fix.
Also TD-018 (a confirmed intermittent ~5 s whole-process stall that makes 5 s idle waits miss in
about 1 of 3 full-suite runs; capture all thread stacks when a wait passes 4 s and compare with
TD-017 first). Also: the six `discard-*` cases of tests/gui/test_dashboard_outside_visual.py
never settle ("queued dashboard/banner geometry never settled") when the project sits under a
long folder path, as in reviewers' scratch copies (P5-T10d review); they pass in the checkout
and CI. Reproduce with a long basetemp, then make the wrapped outside-section text settle.
Also (P5-T10e review): the outside-edit banner's own note ("Locked as manual …") is cleared
by ComponentCard.bind's outside.clear() on every re-bind, so another card's change wipes it;
owner decision D3 asks a card's note to stay until that card changes. Keep the pending-request
reset on re-bind, but keep the finished outcome unless the card's own part changed.
Also (P5-T10f review): Copy details has no size cap. A tool's stderr tail keeps 50 lines of up
to 1,000,000 characters each, so one copy reached 5,000,228 characters; cap the copied text
(keep the head and tail). A build step failing with something other than a CTStudioError
becomes a BuildError without details, so no Copy details appear (the traceback is only in the
log); carry the traceback as details. The test for a failing crash dialog checks only the log
message: also assert the record carries its traceback (exc_info).
Also (P5-T10h review): a dashboard card beside a taller card (Minimap beside Skybox with its
outside-edit buttons) spreads its own lines over the row height, at 100 % too; top-align the
card's layout or end it with a stretch. The high-DPI tests use Qt's default PassThrough
rounding, and QT_SCALE_FACTOR is never rounded, so they would not notice a future
setHighDpiScaleFactorRoundingPolicy that turns 1.5× into 2×; add a check with the policy if
one is ever set.
### [ ] P13-T07 — Security review
Subprocess argument handling, manifest path traversal, hook script execution consent, download
verification, no secrets in logs/diagnostics.
### [ ] P13-T09 — Remember window size and position? (ask the owner again)
Asked before the release candidate (P13-T08). Owner decision D5 (2026-11-26) was "not for
now", to be asked again once the owner has used CT Studio hands-on. Ask first (remember in
settings.json, clamped onto the screen / in Qt's store / no); build only what is chosen,
with tests for an off-screen or vanished monitor.
### [ ] P13-T08 — Release candidate
Changelog, version bump, docs pass, final HC-lite smoke test request to the human.
### [ ] P13-DEEPCLEAN — Deep Clean #3 (extended checklist)
