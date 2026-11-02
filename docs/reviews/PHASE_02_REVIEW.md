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
- **Must fix 1** (bb8ef79): `process._popen` maps any other `OSError` to `ToolNotFound`
  ("… is not a program this system can run."); doctor reports `not working` with a fix;
  a failed check on the Tools page re-reads the saved paths, so Clear stays usable.
  Reproduced and re-verified on the real CLI; mutants 9/9; Windows and Linux CI green.
- **Should fix 1** (43547f4): `discovery.default_dev_root()` gives `.tools/` only for a source
  checkout (`pyproject.toml` beside `src/`); an installed CT Studio never searches it.
- **Should fix 2** (43547f4): Integration also runs on pushes touching `core/tools`,
  `core/errors.py`, `cli`, `tests/integration`, `tests/fakes`, `scripts/fixtures`; it ran on
  43547f4 (Linux 112 passed / 17 listed skips; `test_doctor_real` included).
- **Should fix 3** (43547f4): new `scripts/file_budget.py` is the gate's last step ("file
  length"); `test_doctor.py` split (helpers + `test_doctor_settings.py`), recording scrubbers
  moved to `scripts/record_normalize.py`, `test_dolphin_launch.py` trimmed to 400.
- **Should fix 4**: the Status cell reads "missing (required)" / "missing (optional)" (and
  likewise for not working / too old); colour now only adds to the words.
- **Should fix 5**: `_unusable_setting` uses the caller's `required` (bb8ef79); `_base` takes
  typed fields (`TypedDict` + `Unpack`), so its `type: ignore` is gone.
- **Should fix 6**: `tests/fakes/recordings/inputs_provenance.json` lists all 31 retained
  inputs with SHA-256 and origin (19 generated, 7 hand-written, 2 rebuilt, 3 tool output);
  a unit test fails on any unlisted or changed file and compares generated ones with
  `make_fixtures.py` output; `tests/integration/test_retained_inputs.py` rebuilds
  `map_model.brres` and `map_model_patched.brres` byte-for-byte with real ABMatt and wszst.
  The other three (`no_bones_model.brres`, `variant.kcl`, `objects.kmp`) have their exact
  origin recorded; their bytes depend on a temporary file name, so they are pinned, not rebuilt.
- **Should fix 7**: ARCHITECTURE.md discovery order and TOOLS.md's stale Linux sentence fixed.
- **Consider, Linux doctor**: discovery finds `.tools/riistudio-wine/bin/rszst`;
  `test_doctor_real` checks its 5.11.5 version when present (43547f4).
- **Consider, Wine prefix**: `riistudio.wine_root_of` checks the layout instead of a blind
  `parents[1]`.
- **Consider, logged**: TD-005 (Tools page close during a check, P5-T01), TD-006 (Action SHA
  pins, P13-T07), TD-007 (bigger screenshots, P5-T09), TD-008 (two C-grade scripts, Deep Clean #1).
- Mutation check of the Should fixes: 11/11 after one added test (a `pyproject.toml` without
  a `src` layout).
