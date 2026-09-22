# Phase 0 review brief — Environment, toolchain & spikes

**Reviewer: read this, then verify it yourself. Do not trust any claim here without running it.**

## Phase goal and exit criteria
Goal: prove every risky assumption behind CT Studio *before* writing application code, so Phase 1+
builds on measured facts rather than guesses. Exit: all P0 tasks ticked, every ADR either Accepted
with evidence or explicitly Provisional with a named checkpoint, TOOLS.md facts marked verified
against pinned versions, and HC0 questions ready for the human.

Phase 0 is **planning and spikes only**. There is no `src/`, no `scripts/check.py`, no
`pyproject.toml` — ADR-016 governs this: the gate arrives in P1-T02, and until then each task
records real commands, versions, exit codes and task-specific tests. Reviewing "why is there no
application code" is out of scope; reviewing "is the recorded evidence real and sufficient" is
exactly the job.

## Scope
`git diff --stat fa56cc8..HEAD` → 63 files, +8878/-184. 30 commits.
Tasks: P0-T01 environment audit, T02 toolchain bootstrap, T03 synthetic fixture track,
T04 S1 Wiimms assemble/check, T05 S2 headless Blender export, T06a/b S3 BRRES backend bake-off,
T07 S4 material-edit preservation, T08 S5 headless minimap, T09 S6 preview stack,
T10 S7 editor launch contracts, T11 S8 Dolphin launch routes, T12 (this wrap-up).

## What to check, in priority order
1. **Evidence completeness.** For every claim in `docs/reference/TOOLS.md` marked
   `[verified S<n>, run]`, is there a spike script, a findings JSON, or a test that actually
   produced it? Flag anything marked verified that is really desk research, and anything asserted
   in a phase file with no traceable source.
2. **Plan consistency.** Each spike's findings must reach the phase file that consumes them
   (S1→P4, S2→P6, S3→P7, S4→P7-T07, S5→P8-T03, S6→P9, S7→P2-T05/P5-T07, S8→P11). Flag evidence
   that is stranded in `docs/dev/SPIKES.md` and never turned into a constraint on a later task.
3. **Honest limits.** Phase 0 ran in a Linux container with no GPU, no Mario Kart Wii data and no
   Windows. Every conclusion that silently depends on one of those should be a named HC item
   instead. Flag over-claiming.
4. **Tests.** Run them. The spike tests are characterization tests over real tools; check they
   would actually fail if the tool's behaviour changed, and mutation-spot-check three of them.
5. **ADR statuses** (`docs/DECISIONS.md`) against what the spikes measured — especially ADR-004
   (+ minimap exception), ADR-008, ADR-012, ADR-017, ADR-018.

## Commands
```bash
cd /workspace/ct-studio
export PATH=/usr/games:$PATH                     # Debian puts dolphin-* here
uv run --with pytest --with pytest-timeout --with numpy --with pillow \
  --with moderngl --with PySide6 \
  python -m pytest -q -m "not network"           # full suite
uv run --with ruff ruff check spikes tests scripts
uv run --with ruff ruff format --check spikes tests scripts
bash spikes/s8_mutation_check.sh                 # 6/6 expected, ~4 min
```
Spike scripts are re-runnable: `uv run python spikes/s8_dolphin_launch.py`, etc. Outputs land in
`spikes/out/<id>/` (gitignored), as do `.tools/` downloads and the Wine prefixes in `/root`.

## Known limitations (do not re-report as findings; do challenge if wrong)
- No GPU: preview fps (~10 on llvmpipe) is a software floor, deferred to HC3, not a verdict.
- No MKW data: S8 uses a synthetic disc-shaped directory; "does the track load in-game" is HC3.
- No Windows/macOS: all four Windows editors were characterized under Wine; native behaviour is HC1.
- RiiStudio's project-wide licence is unconfirmed — it must not be bundled or called MIT.
- `AGENTS.md` line 49 is stale (offscreen GL) and is the human's file to edit; it is logged in STATUS.
- TD-001: RiiStudio's `File:` output needs its GitHub update check; the test is `network`-marked.
