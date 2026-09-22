# Testing strategy

Goal: the agent, not the human, finds almost all bugs. The human's time is reserved for things only
a human with the real game and real habits can judge (see HUMAN_CHECKPOINTS.md).

## 1. Layers and markers
| Layer | Location | Marker | Runs | Speed target |
|---|---|---|---|---|
| Unit (pure core logic) | `tests/unit/` | — | every `check.py` | whole suite < 20 s |
| Contract (fakes ↔ recorded real tool help/outputs) | `tests/contract/` | — | every `check.py` | < 5 s |
| GUI (pytest-qt, offscreen) | `tests/gui/` | `gui` | every `check.py` (CI both OS) | < 60 s |
| Integration (real tools from `.tools/`) | `tests/integration/` | `integration` | before commit when touching tools/pipelines; nightly CI | minutes |
| End-to-end (fixture `.blend` → SZS) | `tests/e2e/` | `slow`, `integration` | before phase gates; nightly CI | minutes |
| Real data (user's own tracks) | `tests/realdata/` | `realdata` | only when `local_fixtures/` exists | varies |
| Benchmarks | `tests/benchmarks/` | `benchmark` | phase gates, deep cleans | — |
| External-endpoint dependent | anywhere | `network` | nightly CI only, never `check.py` | varies |

A `network` test depends on something outside the repo being reachable. It must **skip with a
precise reason** naming the endpoint when that precondition fails, never fail and never pass
vacuously — an offline machine is not a broken build. `check.py` excludes the marker (P1-T02);
the nightly integration workflow is the only place it runs and must surface skip reasons rather
than report green (P1-T07). First instance: TD-001, RiiStudio's update check.

Every test file sets a timeout (`pytest-timeout`, default 30 s unit, 600 s integration).

## 2. Fake tools and recordings
- `tests/fakes/<tool>.py` implement only the CLI surface we use, log received argv to JSON, and
  produce minimal plausible outputs. They are launched through the *real* process runner, so the
  runner is exercised too.
- `tests/fakes/recordings/<tool>/<version>/` store captured real outputs (`--help`, `version`,
  `check` on good/bad inputs). Parsers are unit-tested against recordings.
- Contract tests fail if an adapter emits a flag absent from the recorded help of the pinned version,
  or if a parser can't handle a recording. Upgrading a tool = add a new recording folder, re-run.

## 3. Fixtures
- **Synthetic, generated, deterministic** (`scripts/fixtures/`): fixture `.blend` (course, KCL,
  skybox collections; opaque/cutout/translucent/grayscale textures), fixture KMP (via `wkmpt`),
  crafted bad variants (non-POT textures, unflagged KCL objects, out-of-range coordinates, missing
  materials, corrupt KCL/KMP bytes).
- **No golden binaries of tool outputs** (they change with tool versions). Assert structure instead:
  `wszst list` contents, parsed `check` issues, `inspect` results (formats, material settings),
  KCL/KMP reader stats.
- Generated fixtures are cached under `tests/fixtures/generated/` keyed by generator hash.

## 4. Real data (optional, local only)
The human may place their own track projects/SZS files in `local_fixtures/` (gitignored) with a
`local_fixtures/README.md` describing each. Tests marked `realdata` auto-skip when absent. The real
Wiimms auto-add build/use test also carries this marker and runs at HC1; synthetic fixture builds
must not require an auto-add library. Never upload game-derived inputs or auto-add contents to CI
or commit them.

## 5. GUI testing
- `QT_QPA_PLATFORM=offscreen`, pytest-qt `qtbot`, wait on signals (`qtbot.waitSignal`) — never sleep.
- Every GUI test that shows a new screen state saves a screenshot to `tests/artifacts/screens/`
  (`widget.grab().save(...)`), uploaded as a CI artefact. Screens are reviewed at gates (§5 of
  REVIEW_CHECKLIST) by the agent if it can view images, otherwise listed for the human at HCs.
- The dev watchdog is enabled in GUI tests; any UI stall > 100 ms fails the test (allowlist startup).
- GL/preview tests **cannot use `QT_QPA_PLATFORM=offscreen`** — it cannot create a GL context at all
  (`QOpenGLWidget is not supported on this platform`, verified in S6/P0-T09). Run them under
  `xvfb-run` with `QT_QPA_PLATFORM=xcb`, which gives GL 4.5 core on llvmpipe. Non-GL widget tests keep
  using offscreen. A standalone `moderngl.create_context(standalone=True, backend="egl")` also works
  and needs no X server, so use it for pure-render checks with no Qt widget involved. Linux runners
  need `libgl-dev` (the unversioned `libGL.so`) as well as the runtime library. Skip with a clear
  reason if GL is unavailable on a runner, but never on the Linux integration job.

## 6. CI matrix
- `ci.yml` (every push/PR): ubuntu-latest + windows-latest · `check.py` (unit, contract, gui).
- `integration.yml` (nightly + manual): both OSes · bootstrap tools (cached by version) · integration
  + e2e · uploads logs, screenshots, built SZS artefacts (synthetic only).
- `compat.yml` (weekly): Blender 4.5 LTS compatibility run of bridge tests.
- `release.yml` (tags): packaging + packaged smoke tests (P12).
Windows CI is how Windows is validated continuously — the human only does Windows spot checks at HC2
and HC4.

## 7. What each phase must add
- New adapter operation → recording + parser unit test + integration test.
- New node → unit test with fakes (params → args, caching behaviour) + integration test.
- New GUI page → pytest-qt flow + screenshots (light/dark).
- New parser → corrupt-input tests (P13 adds hypothesis fuzzing).
- New heavy operation → benchmark.

## 8. Flaky tests policy
A flaky test is a bug. Quarantine only with a task ID and a date; fix within the phase.
