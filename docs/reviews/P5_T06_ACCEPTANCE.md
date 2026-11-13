# P5-T06 acceptance audit

Final original-acceptance evidence map for P5-T06 (implementation `d610b26`).
Baseline: `3e87530`. The original 27-file watcher/action/presentation selection passed
453 cases locally; the new real-watcher failure matrix is a separate 16-case selection.
Final full gates and exact-commit Windows/Ubuntu CI remain release requirements.

## Original criteria and primary executable evidence

All paths below are relative to `tests/`; parametrized cases retain their original assertions.

| Criteria | Primary suites / behavior |
|---|---|
| A01 edit -> banner within 2 s -> native Lock copies/manual | `gui/test_dashboard_outside_flow.py::test_real_watcher_reaches_native_choices_and_preserves_exact_bytes` |
| A02 confirmed Discard backup and refreshed status | Same real flow; `gui/test_dashboard_outside_visual.py::test_populated_window_outside_edit_geometry_and_real_joined_outcome` |
| A03 Cancel/Enter/Escape/close preserve user data | `gui/test_dashboard_outside_flow.py`; `gui/test_outside_edit_banner.py` native confirmation cases |
| A04 atomic save and outside Blender/supplied paths | `unit/test_project_watcher.py::test_an_atomic_save_is_reported_under_the_files_own_name`; `unit/test_project_watcher_outside.py` |
| A05 ignore own state/build/git/editor backups, not stage | `unit/test_project_watcher.py::test_ignored_changes_are_never_reported`; `unit/test_project_watch.py` |
| A06 switching/closing and obsolete events | `gui/test_real_watch_lifecycle.py` real backend switch/native close; `gui/test_watcher_bridge.py::test_news_from_a_replaced_or_stopped_watcher_is_dropped` deterministic injected events; final G03 verification below |
| A07 watcher shutdown joins, retains lock on timeout | `unit/test_project_watcher.py::test_stop_ends_every_watcher_thread_quickly`; `gui/test_watcher_bridge.py` ownership cases |
| A08 watch failure/half-dead watcher and Refresh retry | `unit/test_project_watcher_faults.py`; `gui/test_dashboard_watch.py`; `gui/test_watcher_bridge.py` |
| A09 outside folder disconnect/reconnect | `unit/test_project_watcher.py::test_an_outside_folder_that_comes_back_is_reported_and_watched_again` |
| A10 debounce, build suppression and later refresh | `gui/test_watcher_bridge.py::test_a_change_asks_for_statuses_but_not_while_building`; status-service tests |
| A11 all generated parts, saved mode and backup protection | `unit/test_edited_lock.py`; `unit/test_edited_discard.py` |
| A12 read-only/not-edited/gone/manual/stale refusal, no changes | `unit/test_edited_refusals.py`; new native failure/refusal cases below |
| A13 copy/save/move/read faults preserve user work | `unit/test_edited_failures.py` |
| A14 mounted controls and explicit eligibility/direct bypass | `gui/test_component_card_outside.py`; `gui/test_dashboard_outside_controls.py` |
| A15 busy/build/edit/status/launch/navigation single ownership | `gui/test_reconcile_ownership.py`; whole-window actual working states in `gui/test_dashboard_outside_visual.py` |
| A16 off-UI actions, UI delivery after join, target-only outcome | `gui/test_reconcile_requests.py`; `gui/test_dashboard_outside_controls.py`; new failure matrix |
| A17 uncertain native startup is not cancellation/rollback | `gui/test_reconcile_startup.py`; new native-acknowledgement case |
| A18 actual saved bytes and independent action/read errors | `gui/test_reconcile_recovery.py`; new post-write/read-fault cases |
| A19 canonical relative/absolute provenance, foreign roots | `gui/test_dashboard_reconcile.py` successful relative/absolute and foreign-root cases; `gui/test_outside_canonical_failures.py` post-write fault matrix; final G02 verification below |
| A20 unsafe memory read-only, real lock retained, editable reopen | `gui/test_dashboard_reconcile.py::test_unsafe_publication_retains_lock_but_refuses_writes`; new read-fault case |
| A21 post-write rebind publishes or quarantines | `gui/test_dashboard_outside_rebind.py`; new both-action rebind cases |
| A22 stale modal/project/root/manifest/result/status rejection | `gui/test_dashboard_outside_controls.py`; `gui/test_dashboard_outside_context.py`; `gui/test_dashboard_reconcile.py` |
| A23 actual Tab/Space and viewport reachability | `gui/test_dashboard_outside_flow.py::test_real_dashboard_tab_path_reaches_and_activates_lock`; whole-window visual cases |
| A24 minimum/tall, wider enlarged fonts, light/dark real actions | `gui/test_dashboard_outside_visual.py` (16 cases); images inspected locally in P5-T06c2b2c1 |
| A25 guide/native words, uncertain-start wording and scope | `unit/test_outside_edit_guide.py`; [user guide](../user/PROJECT_NAVIGATION.md#keeping-or-discarding-an-outside-edit) |

## Final acceptance additions and release requirements

- G01 was completed by P5-T06c2b2c2a (`dac5481`, closeout `b631256`):
  `gui/test_dashboard_outside_failures.py` starts
  with real watcher readiness and a real edit, then native Lock/confirmed Discard. Its 16
  cases cover creation failure, actual stale-manifest refusal, post-write error, independent
  recovery-read failure, same/replaced-memory post-write rebind and native acknowledgement
  uncertainty. Tests check exact disk/manual/backup bytes, joined UI delivery, error identities,
  retained real writer locks, write refusal and editable reopening. They were green-first;
  assertion-caught source controls, independent review and final gates establish their value.
- G02's P5-T06c2b2c2b executable addition is
  `gui/test_outside_canonical_failures.py::test_postwrite_canonical_failure_keeps_errors_bytes_and_real_ownership`:
  relative/absolute roots x real Lock/confirmed Discard x PermissionError/RuntimeError/
  KeyboardInterrupt x no/action/native-start/both primary errors (48 cases). Resolution faults
  arm only after actual writes; errors retain identity, canonicalization stays on the worker,
  no saved reader runs after failed resolution, live memory stays unchanged, saved/manual/
  backup bytes survive, real writer protection is retained and editable reopen works. When
  startup and action both fail, the existing single primary-result slot preserves startup;
  the executed action's distinct error is separately recorded and identity-checked by the test.
- G03's additions in `gui/test_real_watch_lifecycle.py` exercise real watcher readiness,
  real old/current edits, actual AppServices.adopt, shutdown and MainWindow.close(). Exact
  retired/current Thread identities and real project lock contenders/reopens establish
  termination and ownership. Adoption stops asynchronously; the test explicitly joins the
  retired backend, while production shutdown/native close perform current-backend joins.
  Obsolete callbacks are explicitly injected, not backend events: their Qt delivery cannot
  escape bridge generation guards or change replacement/closed view state. Existing
  `gui/test_watcher_bridge.py` deterministic late-event cases remain part of the final suite.
  Neither strict Linux typing nor Windows execution establishes Linux backend runtime.

G02/G03 completed at `d610b26`: parent and independent review each passed all
519 mapped cases across 25 original criterion groups; 6/6 parent source
controls and three independent controls were assertion-caught with no errors. Strict Windows/
Linux each checked both final Python files; fresh locked Unicode installation passed all
50 new cases. Full gate 4046 passed / 6 existing skips / 176 deselected;
exact Check Windows 4037/15, Ubuntu 4038/14 (4052 selected).
Both actual CI artifacts contain coverage.xml only. No production change or acceptance waiver.
The documentation closeout requires its own exact CI and remote read-back before final delivery.
The prior closeout had unexplained Windows and Ubuntu full-suite timeouts before successful
unchanged reruns; these are not diagnosed or fixed. Diagnostic pytest --debug also interfered
with a nested gate output contract; removing that flag restored it without assertion changes.
Keep that distinction and the original time limits; a green rerun is not a claimed timeout cure.

All original P5-T06 criteria passed final review and exact implementation CI. The final leaf
and parent closure are reopened: required Ubuntu closeout Check at `03c8008` exposed an empty-
receipt race in the existing CLI fake-editor test. Repair `8e5d688` atomically publishes its
closed temporary receipt, with deterministic RED/GREEN and independent delta approval;
526 combined acceptance and 57 fresh-install cases passed, local gate 4047/6/176.
Ubuntu Check passed, but Windows job 131874581475 timed out at 1200 seconds. This is not
proof of a receipt-fix failure or a timeout cure. `scripts/check.py` now preserves partial
stdout/stderr on timeout and configures verbose case progress plus 60-second thread dumps.
Real blocked child and blocked pytest probes verify retained output and actual tracebacks;
original nested gate contracts and 1200-second limit remain unchanged. Independent review,
full local gate and exact diagnostic-commit CI are required; final leaf and parents remain
open with no criteria waived. Keep & capture is expressly deferred to P7; automatic generators are not promised.
Local Windows offscreen font/palette proxies and hosted Linux runtime do not establish Linux
native desktop appearance. That documented, nonblocking appearance gap remains unverified.
Screenshots, fonts and game data remain local and are never part of uploaded evidence.
