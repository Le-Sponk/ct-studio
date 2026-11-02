# Phase 3 review brief — project model & component status
**Reviewer:** verify independently; this is orientation, not evidence. Repository `C:\dev\ct-studio`.

## Goal and exit
Projects can be created and opened, and every part of a track reports an accurate status fast.
Exit: `ctstudio new` + `ctstudio status [--json]` work on fixture projects; the status of a
typical project evaluates in < 300 ms (benchmark). P3-T01 … P3-T07 are ticked in
`docs/phases/PHASE_03_project_model.md` (P3-T05 was done before P3-T04: STATUS "Plan changes").

`git diff --shortstat phase-02-done..HEAD`: about 51 files, +7k. `src` +2.9k in: `core/project/
{manifest,manifest_io,toml_table,migrations,project,lock,slots}.py` + `slots.json`,
`core/components/{registry,state,status}.py`, `core/formats/magic.py`,
`core/tools/availability.py`, `cli/{__init__,new,status,open_file}.py`, `__main__.py`.
Script: `scripts/make_slot_catalogue.py` (+ recording `tests/fakes/recordings/wstrt/`).
Docs: `docs/user/PROJECT_FILE.md`, `docs/dev/CLI.md` (status JSON schema), ARCHITECTURE.

## Checks to reproduce
On this Windows git-bash host, first `export PATH="$LOCALAPPDATA/Microsoft/WinGet/Links:$PATH"`.
- `uv run python scripts/check.py --all` (local pre-review at a46b515: green, 1,670 passed).
- `uv run pytest -p no:cacheprovider -q -m "integration and not network and not slow and not realdata" tests/integration/test_cli_status_real.py tests/integration/test_magic_built.py -rs`
- `uv run pytest -p no:cacheprovider -q -s -m "slow and benchmark" tests/benchmarks/test_status_speed.py`
  (local: cold ~70 ms, warm ~11 ms for 20 parts / 25 x 1 MiB files).
- Try the CLI on a scratch folder outside the repo: `uv run ctstudio new <dir> --slot "moo moo meadows"`,
  `uv run ctstudio status <dir>`, `--json`, a misspelt `--slot`, `ctstudio open <file>.toml`.
  Do NOT run `ctstudio open` on a .blend/.brres/.kmp: it starts a real editor.
- CI (no auth): `https://api.github.com/repos/Le-Sponk/ct-studio/commits/<sha>/check-runs`.
- Mutation spot-checks only in a scratch copy (`git worktree add`), never the live tree.

## Known limits to challenge
- Manifest comments are lost on save (documented in PROJECT_FILE.md).
- Lock: `O_EXCL` + a second guard file for stale takeover; pid reuse after a crash can make a
  stale lock look alive (the user is told the pid and file to delete).
- Status hashes only files whose size/mtime changed since the last build record; a same-size,
  same-mtime edit is not seen (by design, for speed).
- The folder-replaced-by-a-file status case is only exercised on Linux CI.
- `ctstudio status` reads the manifest without the lock, so it can race a save (atomic replace).
- The slot catalogue's cup names are the one hand-typed list (checked against Tockdom).
- Copyright: no game data in the repo. The `wstrt` recording is tool text only (track names).
  The realdata test (`tests/realdata/test_magic_original_tracks.py`) reads the user's own disc
  extract under git-ignored `local_fixtures/` and is skipped when it is absent.
- No human checkpoint at Phase 3 exit.
