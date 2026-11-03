# Phase 4 review brief — build engine & SZS assembly
**Reviewer:** verify independently; this is orientation, not evidence. Repository `C:\dev\ct-studio`.

## Goal and exit
`ctstudio build` turns a project whose parts are in manual mode into a valid SZS, incrementally.
Exit: an integration test builds the fixture in manual mode, the `wszst check` result is stored
(`.ctstudio/issues.json`), and a second build skips every step in < 1 s. P4-T01 … P4-T08 ticked
in `docs/phases/PHASE_04_build_engine.md` (T03, T05, T07 split a/b: STATUS "Plan changes").

`git diff --shortstat phase-03-done..HEAD`: 72 files, +8.7k. `src` +2.35k: `core/build/{node,graph,
cache,runner,events,build_log,part_state,stage,assemble,objects,validate,project_build,event_json}.py`,
`core/tools/{wiimm,wiimm_objects}.py`, `core/validation/{issues,wszst_check}.py`, `cli/build.py`.
Docs: ARCHITECTURE (build section, §15), `docs/dev/CLI.md` (build + `--json-events` schema),
`docs/dev/BENCHMARKS.md` (P4-T08), TOOLS.md (wszst create/list/check/autoadd, wkmpt objects).

## Checks to reproduce
On this Windows git-bash host, first `export PATH="$LOCALAPPDATA/Microsoft/WinGet/Links:$PATH"`.
- `uv run python scripts/check.py --all` (local at 5831980: green, 2,011 passed).
- `uv run pytest -p no:cacheprovider -q -m "integration and not network and not slow and not realdata" tests/integration/test_build_assemble_real.py tests/integration/test_build_objects_real.py tests/integration/test_build_validate_real.py tests/integration/test_build_project_real.py tests/integration/test_cli_build_real.py -rs` (local: 10 passed; real Wiimm 2.42a in `.tools/`).
- `uv run pytest -p no:cacheprovider -q -s -m benchmark tests/benchmarks` (local: typical track
  0.67 s, no-change 45 ms in-process / ~0.5 s as a process, 1,000-input warm key 0.25 s).
- `uv run pytest -p no:cacheprovider -q -m realdata tests/realdata` (local only, user's own disc copy
  in git-ignored `local_fixtures/`; skips when absent): 5 passed.
- Try the CLI in a scratch folder outside the repo: `ctstudio new`, set parts to manual in
  `ctstudio.toml` (copy the committed synthetic `tests/fakes/recordings/wszst/2.42a/inputs/course.k*`;
  BRRES stand-ins must be zero-padded, see below), `ctstudio build`, again, `--json-events`,
  `--release`, `--only kcl`, `--force`, a wrong file, Ctrl+C.
- CI (no auth): `https://api.github.com/repos/Le-Sponk/ct-studio/commits/<sha>/check-runs`.
- Mutation spot-checks only in a scratch copy (`git worktree add`), never the live tree.

## Known limits to challenge
- Cache: size+mtime unchanged means unchanged (no hash). Output paths are not in the key.
- Only manual mode builds; auto parts stop the plan with "cannot make … in auto mode yet".
- wszst 2.42a crashes (Cygwin stack dump) packing BRRES with random bodies; the build reports
  the tool failure. Wine/rszst is not used for building yet (Linux uses native wszst).
- The auto-add library has no setting UI yet (user settings file only; Build page in P5).
- `--json-events` schema is checked by a small in-repo checker (no jsonschema dependency).
- Copyright: no game data in the repo; realdata tests read `local_fixtures/` and write to tmp only.
- Human checkpoint HC1 is at the end of Phase 5, not here.
