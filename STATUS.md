# STATUS

> The agent updates this file at the end of every session. The human reads it to see progress
> and to answer "Needs human" items. Keep entries short; link to files/commits for detail.

**Current phase:** 0 — Environment, toolchain & spikes
**Next task:** P0-T05 — Spike S2: headless Blender exports
**Name:** CT Studio · package/CLI `ctstudio` · project data `.ctstudio/` (ADR-015)
**Last green commit:** 1d44633 (ADR-016 evidence gate; `check.py` arrives in P1-T02)
**Last phase gate passed:** —

## In progress
<!-- Task ID, one-line plan, acceptance criteria restated, files expected to change -->
_none_

## Done (newest first)
<!-- `P0-T01` — short summary — commit abc1234 -->
- `P0-T04` — Spike S1 (Wiimms assemble & check): `spikes/s1_wszst.py` +
  [SPIKES.md §S1](docs/dev/SPIKES.md) + adapter command table in TOOLS.md.
  Found that `wszst check`'s exit code is not pass/fail and that `analyze --json`
  supersedes `slots`. 11 integration tests, 3/3 mutations caught. — commit COMMIT_HASH
- `P0-T03` — synthetic fixture track: `scripts/fixtures/` generates two `.blend` variants,
  7 PNGs and a valid `course.kmp` in 0.85 s (budget 60 s), deterministically. Proved with
  the real tools: add-on exported 5 KCL objects / 292 triangles, `wkclt flags` confirmed
  all five flag types. 38 unit tests, 3/3 mutations caught. — commit 1d44633
- `P0-T02` — `scripts/bootstrap_tools.py` + `scripts/tool_catalogue.py` install Wiimms
  2.42a, Blender 5.2.2 LTS and ABMatt 1.3.2 into `.tools/` with checksum verification.
  Fresh run 55 s, second run 0.35 s no-op; 22 unit tests, 3/3 mutations caught.
  [TOOLS.md](docs/reference/TOOLS.md) — commit cbbb5f4
- `P0-T01` — environment audit: Debian 13.4 x86_64 container, root apt works, all four
  download origins reachable, Mesa llvmpipe gives GL 4.5 core via surfaceless EGL and
  Xvfb, no Python 3.12 yet. [ENVIRONMENT.md](docs/dev/ENVIRONMENT.md) — commit b69cc17

## Plan changes
<!-- Date · what changed · why (evidence link) · affected ADR/phase files -->
- 2026-09-17: ADR-016 adds the pre-P1-T02 evidence gate because the mandatory script
  does not exist yet (real invocation exited 2). Evidence: ENVIRONMENT.md, quality gate
  section. Phase 0, WORKFLOW and AGENTS rule 6 now reference this bounded exception.
- 2026-09-17: human rewrote AGENTS rule 3 — `subprocess` is confined to
  `core/tools/process.py` inside `src/ctstudio/`, while `scripts/`, `spikes/` and
  `tests/` may spawn processes directly with argv lists, explicit timeouts and exit-code
  handling; never `shell=True`; spike code is never copied into `src/`. P0-T02 onward
  follows this. No ADR needed (it tightens the wording of an existing accepted rule).
- 2026-09-17: name settled as **CT Studio** (ADR-015 now Accepted). Docs renamed:
  package/CLI `trackstudio` → `ctstudio`, manifest `ctstudio.toml`, app folder
  `.ts/` → `.ctstudio/`, `TRACKSTUDIO_DEV` → `CTSTUDIO_DEV`, `TrackStudioError` →
  `CTStudioError`. Done before any code exists, so P1-T01 writes the new names directly.
- 2026-09-17: **Lorenzi's KMP Editor has no Linux build** — only a Windows `.exe` and a
  macOS arm64 zip, in every release back to v0.7.0 (GitHub releases API). P0-T02 planned
  to install it; it now isn't installed at all and P0-T10 must drive it through Wine like
  BrawlCrate. Affects P0-T02/P0-T10 and the Linux launch contract in TOOLS.md.
- 2026-09-17: bootstrap installs **3 tools, not 5**. uv itself is already present and
  Python 3.12 comes from `uv python install 3.12` (3.12.13, ~4 s), so neither needs a
  catalogue entry. Recorded in TOOLS.md; P0-T02 wording updated.
- 2026-09-18: fixture KMP is complete **except the `[CAME]` opening camera**, which needs
  the four-lines-per-camera layout; compiling therefore reports 2 expected camera warnings
  (asserted by the generator and a test, so a third warning fails the build). P0-T03 allowed
  this deferral; the note landed on **P10-T01**, not P10-T05, because P10-T05 is about
  editor round-trips while P10-T01 is where KMP sections are actually handled.
- 2026-09-18: added `pytest.ini` (marker registry from TESTING_STRATEGY §1) and extended
  `ruff.toml`, both pre-P1 stand-ins that P1-T01/P1-T02 fold into `pyproject.toml`.
- 2026-09-18 (S1): **`wszst check` exit codes are not a pass/fail signal** — valid track,
  warning-laden track and empty archive all exit 2 (`DIFFER`), but a corrupt file exits
  **0** while printing `ERROR #39`. The adapter must parse output and treat `ERROR #` as
  failure. Affects P2-T05 (`wiimm.py`) and P4-T06 (validate node); both updated.
- 2026-09-18 (S1): `check --sections` and `slots --sections` are rejected; **only
  `analyze` is machine-readable** (`--json`/`--sections`). `analyze --json` carries
  `slot_info`, `lap_count`, `n_ckpt0`, coordinate ranges and per-component SHA1s, so
  `slots()` is dropped from the P2-T05 adapter surface in favour of `analyze()`.
- 2026-09-18 (S1): `wszst create` never validates (it builds from an empty directory),
  and `--auto-add` is a **silent no-op** without a library. The app must guard both.

## Needs human — BLOCKING
<!-- Question · options · agent's recommendation · what is blocked -->
_none_

## Needs human — non-blocking
_none_

## Blocked tasks
<!-- Task ID · what was tried · what's needed -->
_none_

## Tech debt (each item has a task ID or "Deep Clean #N")
_none_

## Human checkpoint results
<!-- HC0..HC4: date · outcome · issues filed as task IDs -->
_none_
