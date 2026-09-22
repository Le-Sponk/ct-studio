# Phase 0 review — findings and triage

Reviewer: independent subagent, fresh context, 2026-09-22 (24 min, 48 tool calls).
Brief: `PHASE_00_BRIEF.md`. Baseline reproduced exactly (124 passed, 2 skipped, 1 deselected;
ruff clean; `git diff --check` clean).

The review was worth running: it found **two surviving mutations**, one of which invalidated a
documented claim I had written into four files, and one of which showed an entire spike's tests
were passing against a stale artefact. Both are fixed below.

---

## Must fix

### M1 — "a bad DOL header boots as an executable" was false · FIXED
`docs/DECISIONS.md` ADR-018, `docs/ARCHITECTURE.md` §9, `docs/dev/SPIKES.md` §S8,
`docs/phases/PHASE_00*`/`PHASE_11*`, `STATUS.md`, `spikes/s8_mutation_check.sh` mutation 5.

The reviewer zeroed the DOL entry point — the exact mutation the harness called "malformed
main.dol" — and Dolphin still logged `Booting from disc:`, exit 0. The mutation **survived**, so
the harness really reported 5/6 while three files claimed 6/6.

I reproduced it and then found the true cause by bisecting the two inputs:

| Input | Result |
|---|---|
| valid `sys/boot.bin` + DOL with **zeroed entry point** | `Booting from disc:` — mutation cannot be caught this way |
| **short `sys/boot.bin`** (0x10 bytes) + valid DOL | `Booting from executable:` — the real fallback |

So the fallback is real, but it is selected by `IsValidDirectoryBlob` reading `sys/boot.bin`, not
by the DOL header. The claim was directionally right and mechanically wrong, which is worse than
either — P11 would have validated the wrong artefact.

**Fixed:** mutation 5 is now "short sys/boot.bin" and is caught (**6/6, script exits 0**); added
`test_a_short_boot_bin_silently_downgrades_to_an_executable_boot` exercising the real failure;
corrected the claim in ADR-018, SPIKES §S8, PHASE_00, PHASE_11 and STATUS, each now naming
`sys/boot.bin` and recording that the DOL header does *not* select the path.

### M2 — nine S2 tests passed against a stale findings file · FIXED
`tests/integration/test_blender_export_contract.py:40-53`

The fixture ran `spikes/s2_blender.py`, ignored its return code, and asserted only that
`spikes/out/s2/s2_findings.json` existed — a gitignored file surviving from an earlier session.
The reviewer made the probe unrunnable (`raise SystemExit` at the top) and all 9 tests passed in
0.02 s. S2's entire evidence base was pinning a file on disk, not Blender's behaviour.

**Fixed:** the fixture now deletes the findings file first and asserts `returncode == 0` with the
captured output in the failure message. Audited every other test consuming `spikes/out/`:
`test_brres_backends.py` (S3b, 14 tests) had the identical trap and got the identical fix;
`test_material_preservation.py` and `test_minimap_paths.py` invoke tools per-test and were fine.

### M3 — `pytest.mark.timeout` was inert everywhere · FIXED
`pytest.ini`, six test files carrying the mark, five carrying none.

`pytest-timeout` was never installed (`find_spec` → `None`), so every run emitted
`PytestUnknownMarkWarning` and no timeout was enforced — while `TESTING_STRATEGY.md:24` claimed
every file had one. Five files, including the three that drive Wine, GUIs and an emulator that
never exits on success, carried no mark at all.

**Fixed:** added `--with pytest-timeout` to the documented run commands (it was already in
P1-T01's dev group); added marks to the five files that lacked them (900 s for the Wine/emulator
suites, 600 s for the rest); corrected TESTING_STRATEGY to state the plugin is required and that
the warning means nothing is protected. Verified the mark now actually fires: a 2 s timeout on a
30 s sleep fails in 2.01 s.

### M4 — RiiStudio's "single instance: no" was never probed · FIXED
`docs/dev/SPIKES.md` S7 table, `docs/reference/TOOLS.md` launch table.

`spikes/out/s7/s7_findings.json` has `second_instance_windows`/`single_instance` for BrawlCrate,
KMP Cloud and Lorenzi — the `riistudio` object has only `rszst_output`, `abmatt_output`, `note`.
The spike never called `probe_second_instance` for it. A cell in a table headed "verified by real
GUI launches" rested on a source read.

**Fixed:** the cell is marked `*[source only]*`, and ADR-017's bullet now says "no editor we could
probe is single-instance; RiiStudio is source-read only". Re-probing needs a Wine rebuild and is
P2-T08 work, not a gate blocker.

---

## Should fix

### S1 — wrong self-reported counts · FIXED
S8 was recorded as "11 integration tests, 6/6 mutations"; it is **13** and, before M1, **5/6**.
Re-collected every spike's count and checked all eight against STATUS: S1 11, S2 9, S3b 14, S4 10,
S5 8, S6 6, S7 9, S8 13 — the rest were already correct. STATUS and PHASE_00 updated.

### S2 — native-Windows rows over-claimed · FIXED
`docs/reference/TOOLS.md` launch table.
The table was headed "verified by real GUI launches" while its `Win` and `Linux/Win` rows had no
Windows measurement behind them — no Windows machine existed. Split the merged OS cells, marked
every native row `*[unverified — HC1]*`, and added a note under the table pointing at HC1 step 9
and P2-T08.

### S3 — unverified nogui-versus-GUI comparison · FIXED
Claimed the nogui binary "creates fewer subdirectories than the GUI". Only the nogui side was ever
measured. I tried to measure the GUI side: it creates *nothing* on a `--version` run, so the
comparison is not supported as stated. Reworded TOOLS.md and the test docstring to the measured
fact — `dolphin-emu-nogui` does not create `Config` at startup, so never probe for it — and
explicitly noted the GUI side was not measured.

### S4 — minimap fixture exercises 2 of 7 filter conditions · DEFERRED to P8-T03
The KCL drivable-surface filter removes 7 types; `wkclt flags` shows the fixture contains only
0x00, 0x03, 0x06, 0x0c, 0x10, so five conditions are unreachable and deleting `t == 0x1f` survives
(deleting `t == 0x0c`, a type present, is caught — the logic is sound, the fixture is thin).
Not a gate blocker: no assertion is wrong and the recipe is verified for the types that exist.
Logged as **TD-002** against P8-T03, which must extend the fixture generator to emit one triangle
of each filtered type and de-duplicate the filter script (currently copied between
`spikes/s5_minimap.py` and `tests/integration/test_minimap_paths.py`).

### S5 — ADR-017 flattens three grades of evidence · FIXED
Bullets 1-2 are test-backed; bullet 3 (RiiStudio's `File:` receipt) rests on a `network`-marked
test excluded from every default run; bullet 4 included the unprobed cell from M4. The *decision*
is conservative and right either way — reporting "launched" can never be wrong — so the Accepted
status stands, but each bullet is now graded inline and HC1 is named as the checkpoint.

---

## Consider — dispositions

- **`test_the_spike_script_is_runnable_and_self_describing` greps source instead of running it**
  (`test_editor_launch.py`, `test_preview_stack.py`). Fair hit: the name overpromises. Spikes are
  throwaway by AGENTS.md rule 3, so the value is low either way. **Logged as TD-003**, to be
  resolved when P2/P9 consume those spikes — rename to `..._still_parses` and use `ast.parse`.
- **`SETTLE = 14.0` sleeps are unprincipled.** Agreed in general; in practice these wait on Wine
  GUIs with no readiness signal, which is why they exist. Not worth churn now. **Noted in TD-003.**
- **HC0 questions duplicated between HUMAN_CHECKPOINTS.md and STATUS.** Accepted as intentional:
  the checkpoint file is the template, STATUS is the live instance with recommendations. Added a
  pointer line rather than deleting either.
- **TOOLS.md marker convention has four spellings.** Real inconsistency, cheap to fix later, and
  changing every marker now would bury the substantive edits above. **Logged as TD-004** for the
  P1 documentation pass.

---

## What changed as a result

Tests: 124 → 125 passing (+2 wine-skipped) excluding `network` (one new S8 test, plus the two stale-artefact
fixtures now failing loudly instead of passing silently).
`spikes/s8_mutation_check.sh`: genuinely 6/6, exits 0.
Docs corrected: ADR-017, ADR-018, ARCHITECTURE §9, SPIKES §S8, TOOLS (launch table + Dolphin +
RiiStudio), TESTING_STRATEGY, PHASE_00, PHASE_11, STATUS.
New tech debt: TD-002 (minimap fixture coverage), TD-003 (spike-script tests and sleeps),
TD-004 (TOOLS marker convention).
