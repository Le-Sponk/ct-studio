# Phase 2 review — tools: registry, discovery, process runner, doctor

**Gate:** P2-GATE · 2026-11-02 · fresh-context reviewer delegated from
`docs/reviews/PHASE_02_BRIEF.md` and `docs/process/REVIEW_CHECKLIST.md`, reviewing HEAD 78a65ca.
The reviewer did not change the tracked tree (mutations ran in a scratch worktree, removed);
the implementer triaged and fixed the findings.

## Reviewer's checks (re-run independently)
- `scripts/check.py --all`: 7/7 steps, 1,191 passed / 6 skipped. Integration (Windows, real
  tools): 113 passed / 14 skipped, every skip listed. `ctstudio doctor` matched `.tools/`.
- CI at c4a596f: Check and Integration green on ubuntu-latest and windows-latest.
- Mutation spot-check 7/7 caught: Job-object kill flag, pipe pump `or`→`and`, PATH vs standard
  folder order, ignored `force`, non-ASCII staging name, too-old comparison, unvalidated set path.
- Copyright: generated recording inputs are byte-identical to `make_fixtures.py` output; the
  retained inputs (small BRRES/KMP/KCL/OBJ) contain only synthetic strings. No disc-derived
  data, no user or runner paths, no token patterns.
- GUI screenshots (Tools page light/dark/damaged settings): readable, no truncation.

## Findings and disposition

### Must fix — resolved
1. A set path that is not a runnable program (WinError 193/216, Linux ENOEXEC) escaped
   `process._popen` as a raw `OSError`: `ctstudio doctor` crashed with a traceback and the
   Tools page showed the raw error with Clear disabled. See "Fixes" below.

### Should fix
1. `.tools/` developer fallback always on (`include_dev=True` everywhere; dev root derived
   from `__file__`). — see Fixes.
2. Integration CI did not run when adapter or integration code changed (path filter). — see Fixes.
3. Files over 400 lines: `tests/unit/test_doctor.py` (469), `scripts/record_tool_outputs.py`
   (401), `tests/integration/test_dolphin_launch.py` (401, P1); no gate step. — see Fixes.
4. Tools page tells required from optional by colour only. — see Fixes.
5. `doctor._unusable_setting` used the module `REQUIRED`, not the caller's `required`; an
   unexplained `# type: ignore[arg-type]` at `doctor.py:142`. — see Fixes.
6. Retained recording inputs have prose provenance only, nothing re-checkable. — see Fixes.
7. Docs drift: ARCHITECTURE.md discovery order; TOOLS.md "Linux real-tool output is not yet
   measured". — see Fixes.

### Consider — each logged or dismissed
- Linux doctor does not find the Wine rszst copy in `.tools/riistudio-wine/`; no doctor table
  in Integration CI. — see Fixes.
- Tools page `QThreadPool(self)` can block close for up to the probe timeout during a forced
  re-check. — see Fixes.
- `riistudio.py` finds the Wine prefix with `location.path.parents[1]`. — see Fixes.
- GitHub Actions pinned by tag, Node 20 deprecation warnings. — see Fixes.
- Screenshots only at 900×520 with a stub registry. — see Fixes.
- Two pre-existing scripts at complexity C (`bootstrap_tools.unpack`, `check.run_step`). — see Fixes.

## Fixes
_Filled in as each item is resolved, with the commit._
