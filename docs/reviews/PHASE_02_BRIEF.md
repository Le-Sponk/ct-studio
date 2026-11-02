# Phase 2 review brief — tools: registry, discovery, process runner, doctor
**Reviewer:** verify independently; this is orientation, not evidence. Repository `C:\dev\ct-studio`.

## Goal and exit
The app can find, version and safely run every external tool on Windows and Linux. Exit:
`ctstudio doctor` shows a correct table using real tools in `.tools/`; integration CI runs on
both OSes. All P2-T01 … P2-T08f are ticked in `docs/phases/PHASE_02_tools_runner_doctor.md`.

`git diff --shortstat phase-01-done..HEAD`: 203 files, +70.7k (47.4k are JSON tool recordings
under `tests/fakes/recordings`). `src`: 35 files, +5.4k. New modules: `core/tools/{spec,registry,
discovery,versions,process,process_tree,staging,doctor,wiimm,wiimm_autoadd,wiimm_convert,
wiimm_kcl,riistudio,abmatt,abmatt_edit,blender,editors,wine,rszst_install,rszst_setup,
rszst_wine}.py`, `core/validation/{issues,wszst_check}.py`, `core/project/settings.py`,
`cli/{doctor,setup}.py`, `gui/{services.py,views/tools_page.py}`. Scripts: recorders, case
tables, `ci_network.py`, `wine_rszst.py`. CI: `.github/workflows/{integration,record-linux}.yml`.

## Checks to reproduce
On this Windows git-bash host, first `export PATH="$LOCALAPPDATA/Microsoft/WinGet/Links:$PATH"`.
- `uv run python scripts/check.py --all` (local pre-review: green, 1,191 passed)
- `uv run pytest -p no:cacheprovider -q -m "integration and not network and not slow and not realdata" tests -rs`
- `uv run ctstudio doctor` (real tools in `.tools/`; Windows host)
- CI evidence (no auth needed): `https://api.github.com/repos/Le-Sponk/ct-studio/commits/c4a596f/check-runs`
  — Check and Integration green on ubuntu-latest and windows-latest (Linux Integration 112
  passed / 17 listed skips; Windows similar). `tests/integration/expected_skips.toml` lists
  every allowed skip with a reason.
- Mutation spot-checks only in a scratch copy (`git worktree add` or copy), never the live tree.

## Known limits to challenge
- Linux real-tool runs are CI-only (ubuntu-latest) plus the user's Mint runs recorded in
  STATUS (P2-T05g2, P2-T06c, P2-T06e). Editor windows through Wine need a real desktop: skipped
  in CI, listed.
- Fakes replay Windows operation recordings on Linux by design (`fake_runtime.LINUX_REPLAYED`);
  `tests/unit/test_linux_ops.py` pins how Linux recordings differ.
- `test_launch_watch` timing has been loosened twice for slow Windows runners.
- Copyright: no game data in the repo; recordings come from synthetic fixtures only. Check
  that nothing under `tests/fakes/recordings` or `tests/fixtures` derives from a game disc.
- No human checkpoint at Phase 2 exit (HC1 follows Phase 5).
