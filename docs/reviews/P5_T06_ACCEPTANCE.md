# P5-T06 acceptance audit

This is an executable-evidence map, not a claim that every P5-T06 parent is complete.
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
| A06 switching/closing and obsolete events | `gui/test_watcher_bridge.py::test_news_from_a_replaced_or_stopped_watcher_is_dropped` is scripted; G03 remains open |
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
| A19 canonical relative/absolute provenance, foreign roots | `gui/test_dashboard_reconcile.py` successful relative/absolute and foreign-root cases; G02 remains open |
| A20 unsafe memory read-only, real lock retained, editable reopen | `gui/test_dashboard_reconcile.py::test_unsafe_publication_retains_lock_but_refuses_writes`; new read-fault case |
| A21 post-write rebind publishes or quarantines | `gui/test_dashboard_outside_rebind.py`; new both-action rebind cases |
| A22 stale modal/project/root/manifest/result/status rejection | `gui/test_dashboard_outside_controls.py`; `gui/test_dashboard_outside_context.py`; `gui/test_dashboard_reconcile.py` |
| A23 actual Tab/Space and viewport reachability | `gui/test_dashboard_outside_flow.py::test_real_dashboard_tab_path_reaches_and_activates_lock`; whole-window visual cases |
| A24 minimum/tall, wider enlarged fonts, light/dark real actions | `gui/test_dashboard_outside_visual.py` (16 cases); images inspected locally in P5-T06c2b2c1 |
| A25 guide/native words, uncertain-start wording and scope | `unit/test_outside_edit_guide.py`; [user guide](../user/PROJECT_NAVIGATION.md#keeping-or-discarding-an-outside-edit) |

## Remaining evidence gaps, not reproduced production defects

- G01 is the current P5-T06c2b2c2a slice: `gui/test_dashboard_outside_failures.py` starts
  with real watcher readiness and a real edit, then native Lock/confirmed Discard. Its 16
  cases cover creation failure, actual stale-manifest refusal, post-write error, independent
  recovery-read failure, same/replaced-memory post-write rebind and native acknowledgement
  uncertainty. Tests check exact disk/manual/backup bytes, joined UI delivery, error identities,
  retained real writer locks, write refusal and editable reopening. They were green-first;
  assertion-caught source controls, independent review and final gates establish their value.
- G02 remains open for P5-T06c2b2c2b: commit executable canonical-resolution faults armed
  only after real writes, relative/absolute roots, ordinary and interrupt failures, independent
  startup/action/recovery errors, worker-only resolution, no saved read after failed resolution,
  retained protection and editable reopen. Historical scratch probes are not committed tests.
- G03 remains open for P5-T06c2b2c2b: combine real watcher switch/close and old-worker
  termination/current-dashboard isolation with the existing deterministic scripted late-event
  tests. Do not relabel scripted watchers as real backend execution.

All P5-T06 parents remain open until G02/G03 and every original criterion pass final review
and exact CI. Keep & capture is expressly deferred to P7; automatic generators are not promised.
Local Windows offscreen font/palette proxies and hosted Linux runtime do not establish Linux
native desktop appearance. That documented, nonblocking appearance gap remains unverified.
Screenshots, fonts and game data remain local and are never part of uploaded evidence.
